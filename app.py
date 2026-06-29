import os
import re
import json
import time
import asyncio
import threading
from datetime import datetime
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import pyperclip

# Directorios de datos
DATA_DIR = "data"
EXTRACTIONS_DIR = os.path.join(DATA_DIR, "extractions")
CONSOLIDATED_DIR = os.path.join(DATA_DIR, "consolidated")
CONFIG_FILE = "config.json"

# Estado global
is_monitoring = True
active_provider: Optional[Dict[str, Any]] = None
previous_clipboard = ""
logs_buffer: List[Dict[str, Any]] = []
latest_log_index = 0

def add_log(msg_type: str, message: str, data: Any = None):
    global latest_log_index
    log_entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "type": msg_type, # 'info', 'success', 'warning', 'error'
        "message": message,
        "data": data
    }
    logs_buffer.append(log_entry)
    if len(logs_buffer) > 100:
        logs_buffer.pop(0)
    latest_log_index += 1

def load_config() -> Dict[str, Any]:
    global active_provider
    if not os.path.exists(CONFIG_FILE):
        config = {"active_provider_id": None, "providers": []}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Actualizar active_provider global
        providers = config.get("providers", [])
        active_id = config.get("active_provider_id")
        active_provider = next((p for p in providers if p["id"] == active_id), None)
        return config
    except Exception as e:
        add_log("error", f"Error cargando config.json: {str(e)}")
        return {"active_provider_id": None, "providers": []}

def save_config(config: Dict[str, Any]):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        add_log("error", f"Error guardando config.json: {str(e)}")

def clean_price(price_str: str) -> float:
    if not price_str:
        return 0.0
    # Eliminar símbolos de moneda y espacios
    cleaned = re.sub(r'[^\d,.-]', '', price_str)
    # Estandarizar separador de decimales a punto
    if ',' in cleaned and '.' in cleaned:
        # e.g., 1.250,50 o 1,250.50
        if cleaned.find('.') < cleaned.find(','):
            cleaned = cleaned.replace('.', '').replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    elif ',' in cleaned:
        # Si la coma funciona como decimal (muy típico en España, ej: 349,00)
        parts = cleaned.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            cleaned = cleaned.replace(',', '.')
        else:
            cleaned = cleaned.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def extract_products_adaptively(text: str) -> List[Dict[str, Any]]:
    results = []
    
    # 1. Encontrar todos los modelos posibles en el texto.
    # Exigimos que tengan al menos una letra y al menos un número, y mayúsculas/números/guiones (de 5 a 15 caracteres)
    # Ejemplo: 3TS3107BD, 3TS382B, WUU28T6XES, etc.
    model_pattern = r'\b(?=[A-Z0-9-]*[0-9])(?=[A-Z0-9-]*[A-Z])[A-Z0-9-]{5,15}\b'
    
    # Atributos comunes como capacidad (kg) y velocidad (rpm)
    attr_pattern = r'\b\d+\s*(?:kg|KG|Kg|rpm|RPM)\b'
    
    # Precios
    price_pattern = r'\b\d+(?:[\.,]\d+)?\s*€'
    
    # Procesar línea por línea
    lines = text.split('\n')
    spec_lines = []
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue
            
        # Descartamos líneas que terminan en puntos suspensivos ("...") o que son de ruido obvio
        if line_stripped.endswith('...') or re.search(r'\.\.\.\s*\d*$', line_stripped):
            continue
        if any(keyword in line_stripped.lower() for keyword in ['recíbelo entre', 'entrega garantizada', 'programas de lavado', 'tipo de instalación']):
            continue
            
        # Buscar modelos (sin re.IGNORECASE para evitar que coincidan palabras en minúsculas)
        models_in_line = re.findall(model_pattern, line_stripped)
        
        # Filtrar modelos falsos que son unidades de medida (ej: 1400RPM, 10KG)
        models_in_line = [m for m in models_in_line if not re.match(r'^\d+(?:KG|RPM|W|V|HZ|DB)$', m, re.IGNORECASE)]
        
        has_attrs = re.search(attr_pattern, line_stripped, re.IGNORECASE) is not None
        has_keywords = any(kw in line_stripped.lower() for kw in ['lavadora', 'carga frontal', 'balay', 'secadora', 'lavavajillas', 'electro'])
        
        # Si tiene modelo y atributos/palabras clave, la consideramos línea de especificación principal
        if models_in_line and (has_attrs or has_keywords):
            spec_lines.append({
                'index': i,
                'line': line_stripped,
                'model': models_in_line[0],
                'models': models_in_line
            })
            
    # Si no hay líneas de especificación con atributos, buscamos cualquier línea con un modelo válido
    if not spec_lines:
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped.endswith('...') or re.search(r'\.\.\.\s*\d*$', line_stripped):
                continue
            if any(keyword in line_stripped.lower() for keyword in ['recíbelo entre', 'entrega garantizada', 'programas de lavado', 'tipo de instalación']):
                continue
            models_in_line = re.findall(model_pattern, line_stripped)
            models_in_line = [m for m in models_in_line if not re.match(r'^\d+(?:KG|RPM|W|V|HZ|DB)$', m, re.IGNORECASE)]
            if models_in_line:
                spec_lines.append({
                    'index': i,
                    'line': line_stripped,
                    'model': models_in_line[0],
                    'models': models_in_line
                })
                
    if not spec_lines:
        return []
        
    # 2. Para cada línea de especificación, delimitamos su bloque y extraemos los datos
    for idx, spec in enumerate(spec_lines):
        start_line_idx = spec['index']
        end_line_idx = spec_lines[idx+1]['index'] if idx + 1 < len(spec_lines) else len(lines)
        
        # El bloque de texto para este producto específico (hasta el inicio del siguiente producto)
        product_block = "\n".join(lines[start_line_idx:end_line_idx])
        
        spec_line = spec['line']
        model = spec['model']
        
        # Extraer Atributos Técnicos de la línea de especificación.
        attr_match = re.search(r'\b\d+\s*(?:kg|KG|Kg)\b', spec_line, re.IGNORECASE)
        if attr_match:
            attributes = spec_line[attr_match.start():].strip()
        else:
            attr_match_rpm = re.search(r'\b\d+\s*(?:rpm|RPM)\b', spec_line, re.IGNORECASE)
            if attr_match_rpm:
                attributes = spec_line[attr_match_rpm.start():].strip()
            else:
                model_pos = spec_line.find(model)
                if model_pos != -1:
                    attributes = spec_line[model_pos + len(model):].strip()
                else:
                    attributes = ""
                    
        # Limpiar atributos
        attributes = re.sub(r'\s+', ' ', attributes).strip()
        
        # Extraer Precio: primer precio en el bloque
        price_match = re.search(price_pattern, product_block)
        price = price_match.group(0) if price_match else "No disponible"
        
        # Limpiar precio de los atributos si se coló al final de la línea de especificación
        if price != "No disponible" and attributes:
            attributes_clean = attributes.replace(price, "").strip()
            # Eliminar guiones, comas o espacios finales sobrantes
            attributes = re.sub(r'\s+[-–,]\s*$', '', attributes_clean).strip()
            
        # Extraer Producto: es la línea de especificación menos el modelo y los atributos
        product = spec_line
        if attributes:
            # Quitamos los atributos originales de la línea
            product = product.replace(spec_line[attr_match.start():] if attr_match else attributes, '')
            
        product_parts = product.split(model)
        product_clean = " ".join([part.strip() for part in product_parts if part.strip()])
        
        product_clean = re.sub(r'\s+', ' ', product_clean).strip()
        product_clean = product_clean.strip(',').strip('-').strip()
        
        results.append({
            'product': product_clean,
            'model': model,
            'attributes': attributes,
            'price': price
        })
        
    return results

def process_text(text: str, provider: Dict[str, Any]):
    regex_pattern = provider.get("regex")
    if not regex_pattern:
        return
        
    try:
        # Limpiar anclajes antiguos
        pattern = regex_pattern
        if pattern.startswith("^"):
            pattern = pattern[1:]
        if pattern.endswith("$"):
            pattern = pattern[:-1]
            
        matches = list(re.finditer(pattern, text))
        extracted_data_list = []
        
        if matches:
            for match in matches:
                extracted_data_list.append(match.groupdict())
        elif text.strip():
            # Fallback inteligente: si no hay coincidencias con la regex principal,
            # intentamos el extractor adaptativo para capturar de forma robusta la información.
            add_log("info", "Regex exacta sin coincidencias. Iniciando extracción adaptativa inteligente...")
            adaptive_matches = extract_products_adaptively(text)
            if adaptive_matches:
                expected_fields = provider.get("fields", [])
                for item in adaptive_matches:
                    data = {}
                    for field in expected_fields:
                        if field in ["product", "producto"]:
                            data[field] = item["product"]
                        elif field in ["model", "modelo"]:
                            data[field] = item["model"]
                        elif field in ["attributes", "atributos"]:
                            data[field] = item["attributes"]
                        elif field in ["price", "precio"]:
                            data[field] = item["price"]
                        else:
                            data[field] = ""
                            
                    if not data:
                        data = item
                    extracted_data_list.append(data)
        
        if extracted_data_list:
            added_count = 0
            for data in extracted_data_list:
                # Agregar timestamp
                data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Nombre de archivo de salida
                filepath = provider.get("output_file")
                if not filepath:
                    filepath = os.path.join(EXTRACTIONS_DIR, f"{provider['id']}.csv")
                    
                file_format = provider.get("file_format", "csv")
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                df_new = pd.DataFrame([data])
                
                # Guardar en base al formato
                if file_format == "xlsx":
                    if os.path.exists(filepath):
                        try:
                            df_existing = pd.read_excel(filepath)
                            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                        except Exception:
                            df_combined = df_new
                    else:
                        df_combined = df_new
                    df_combined.to_excel(filepath, index=False)
                else:
                    # CSV
                    if os.path.exists(filepath):
                        try:
                            df_existing = pd.read_csv(filepath, encoding='utf-8-sig')
                            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
                        except Exception:
                            df_combined = df_new
                    else:
                        df_combined = df_new
                    df_combined.to_csv(filepath, index=False, encoding='utf-8-sig')
                    
                product_name = data.get("product") or data.get("producto") or list(data.values())[0]
                add_log("success", f"Capturado y guardado: {product_name}", data)
                added_count += 1
                
            if added_count > 1:
                add_log("success", f"Se han procesado y guardado {added_count} productos del portapapeles.")
        else:
            # Ignorar de forma pasiva, pero registrar en el log informativo local
            add_log("info", f"Texto copiado ignorado (no coincide con la plantilla de '{provider['name']}')")
    except Exception as e:
        add_log("error", f"Error en el análisis del portapapeles: {str(e)}")

def clipboard_listener():
    global previous_clipboard
    # Inicializar
    try:
        previous_clipboard = pyperclip.paste()
    except Exception:
        previous_clipboard = ""
        
    add_log("info", "Servicio de escucha de portapapeles activo.")
    
    while is_monitoring:
        if active_provider:
            try:
                current_text = pyperclip.paste()
                if current_text and current_text != previous_clipboard:
                    previous_clipboard = current_text
                    process_text(current_text, active_provider)
            except Exception:
                # Capturar posibles fallos cuando el OS bloquea el portapapeles temporalmente
                pass
        time.sleep(0.5)

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    global is_monitoring
    is_monitoring = True
    os.makedirs(EXTRACTIONS_DIR, exist_ok=True)
    os.makedirs(CONSOLIDATED_DIR, exist_ok=True)
    
    # Cargar configuración inicial
    load_config()
    
    # Iniciar hilo de escucha
    listener_thread = threading.Thread(target=clipboard_listener, daemon=True)
    listener_thread.start()
    
    yield
    
    is_monitoring = False

app = FastAPI(
    title="Garde Clipboard Parser",
    description="Local background app to parse clipboard data",
    lifespan=app_lifespan
)

# Servir estáticos
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Modelos Pydantic
class LabelModel(BaseModel):
    name: str
    start: int
    end: int

class RegexGenerateRequest(BaseModel):
    raw_text: str
    labels: List[LabelModel]

class ProviderModel(BaseModel):
    id: str
    name: str
    regex: str
    fields: List[str]
    output_file: str
    file_format: str
    sample_text: str
    labels: List[LabelModel]

class SelectProviderRequest(BaseModel):
    provider_id: Optional[str] = None

class MergeRequest(BaseModel):
    files: List[str]
    merge_key: str
    output_filename: str

# Rutas API
@app.get("/")
async def get_index():
    index_path = os.path.join("static", "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Dashboard no encontrado. Por favor, crea static/index.html</h1>")

@app.get("/api/status")
async def get_status():
    global active_provider, is_monitoring
    return {
        "is_monitoring": is_monitoring,
        "active_provider": active_provider,
        "has_active_provider": active_provider is not None
    }

@app.post("/api/status/toggle")
async def toggle_status():
    global is_monitoring
    is_monitoring = not is_monitoring
    state = "activado" if is_monitoring else "desactivado"
    add_log("info", f"Monitoreo de portapapeles {state} por el usuario.")
    return {"is_monitoring": is_monitoring}

@app.get("/api/providers")
async def get_providers():
    config = load_config()
    return config

@app.post("/api/providers")
async def save_provider(provider: ProviderModel):
    config = load_config()
    providers = config.get("providers", [])
    
    # Buscar si ya existe y reemplazarlo, o añadirlo
    idx = next((i for i, p in enumerate(providers) if p["id"] == provider.id), -1)
    
    provider_dict = provider.model_dump()
    
    if idx >= 0:
        providers[idx] = provider_dict
        add_log("info", f"Plantilla de proveedor '{provider.name}' actualizada.")
    else:
        providers.append(provider_dict)
        add_log("info", f"Nueva plantilla de proveedor '{provider.name}' creada.")
        
    config["providers"] = providers
    save_config(config)
    load_config() # Recargar global
    return {"status": "success", "provider": provider_dict}

@app.delete("/api/providers/{provider_id}")
async def delete_provider(provider_id: str):
    config = load_config()
    providers = config.get("providers", [])
    
    filtered_providers = [p for p in providers if p["id"] != provider_id]
    if len(filtered_providers) == len(providers):
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        
    config["providers"] = filtered_providers
    if config.get("active_provider_id") == provider_id:
        config["active_provider_id"] = None
        
    save_config(config)
    load_config()
    add_log("info", f"Proveedor '{provider_id}' eliminado.")
    return {"status": "success"}

@app.post("/api/providers/select")
async def select_provider(req: SelectProviderRequest):
    global active_provider
    config = load_config()
    providers = config.get("providers", [])
    
    if req.provider_id is None:
        config["active_provider_id"] = None
        active_provider = None
        add_log("info", "Monitoreo desactivado: Ningún proveedor seleccionado.")
    else:
        # Verificar que existe
        prov = next((p for p in providers if p["id"] == req.provider_id), None)
        if not prov:
            raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        config["active_provider_id"] = req.provider_id
        active_provider = prov
        add_log("info", f"Proveedor seleccionado para captura: '{prov['name']}'.")
        
    save_config(config)
    return {"status": "success", "active_provider": active_provider}

@app.get("/api/providers/{provider_id}/data")
async def get_provider_data(provider_id: str):
    config = load_config()
    providers = config.get("providers", [])
    provider = next((p for p in providers if p["id"] == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        
    filepath = provider.get("output_file")
    if not filepath or not os.path.exists(filepath):
        return {"columns": provider.get("fields", []) + ["timestamp"], "records": []}
        
    try:
        file_format = provider.get("file_format", "csv")
        if file_format == "xlsx":
            df = pd.read_excel(filepath)
        else:
            df = pd.read_csv(filepath, encoding='utf-8-sig')
            
        df = df.replace({pd.NA: None, float('nan'): None})
        records = df.to_dict(orient="records")
        columns = list(df.columns)
        return {"columns": columns, "records": records}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo archivo de datos: {str(e)}")

@app.post("/api/regex/generate")
async def generate_regex_pattern(req: RegexGenerateRequest):
    # Validar que tengamos al menos una etiqueta
    if not req.labels:
        raise HTTPException(status_code=400, detail="Debe proporcionar al menos una etiqueta para generar la expresión regular")
        
    raw_text = req.raw_text
    sorted_labels = sorted(req.labels, key=lambda x: x.start)
    
    parts = []
    
    # Función para determinar el patrón genérico de una etiqueta basada en su nombre o valor
    def get_generic_pattern(label_name: str, label_val: str) -> str:
        name_lower = label_name.lower()
        val_clean = label_val.strip()
        
        # Si es un precio: contiene dígitos y opcionalmente símbolos de moneda
        if "precio" in name_lower or "price" in name_lower or (re.search(r'\d', val_clean) and any(c in val_clean for c in ['€', '$', 'EUR', 'eur', 'Eur'])):
            return r"\d+(?:[.,]\d+)?\s*(?:€|EUR|eur|usd|\$|EUR)?"
            
        # Si es un modelo/SKU: es alfanumérico y tiene cierta estructura
        if "modelo" in name_lower or "sku" in name_lower or (re.match(r'^[A-Za-z0-9-]+$', val_clean) and any(c.isdigit() for c in val_clean) and any(c.isalpha() for c in val_clean)):
            return r"\b[A-Za-z0-9-]{3,25}\b"
            
        # Si es producto/marca o atributos:
        if "producto" in name_lower or "product" in name_lower or "marca" in name_lower or "brand" in name_lower:
            return r"[^\n]+?"
            
        if "atributo" in name_lower or "attr" in name_lower or "spec" in name_lower:
            return r"[^\n]+?"
            
        # Fallback por defecto: capturar caracteres sin saltos de línea de forma perezosa
        return r"[^\n]+?"
        
    # Construir la expresión regular iterando sobre las etiquetas y los textos intermedios
    last_idx = 0
    for i, label in enumerate(sorted_labels):
        start = label.start
        end = label.end
        name = label.name
        val = raw_text[start:end]
        
        literal_between = raw_text[last_idx:start]
        
        if i > 0:
            # Comprobar si la etiqueta anterior o la actual es un precio, o si el literal intermedio tiene saltos de línea
            prev_label = sorted_labels[i-1]
            prev_name = prev_label.name.lower()
            
            is_prev_price = "precio" in prev_name or "price" in prev_name
            is_curr_price = "precio" in name.lower() or "price" in name.lower()
            
            if is_prev_price or is_curr_price or "\n" in literal_between:
                # Transición multilínea flexible
                parts.append(r"[\s\S]*?")
            else:
                # Transición en la misma línea
                parts.append(r"[^\n]*?")
        elif last_idx < start:
            # Para el inicio del texto, si hay texto antes del primer grupo
            if "\n" in literal_between:
                parts.append(r"[\s\S]*?")
            else:
                parts.append(r"[^\n]*?")
                
        # Añadir el grupo de captura genérico
        group_pattern = get_generic_pattern(name, val)
        parts.append(f"(?P<{name}>{group_pattern})")
        last_idx = end
        
    # Al final, si hay texto sobrante
    if last_idx < len(raw_text):
        literal_after = raw_text[last_idx:]
        if "\n" in literal_after:
            parts.append(r"[\s\S]*?")
        else:
            parts.append(r"[^\n]*?")
            
    pattern = "".join(parts)
    
    # Validar usando re.search en el texto de muestra (sin anclajes strictly "^" y "$")
    try:
        match = re.search(pattern, raw_text)
        if match:
            extracted = match.groupdict()
            return {
                "status": "success",
                "regex": pattern,
                "extracted": extracted
            }
        else:
            return {
                "status": "warning",
                "regex": pattern,
                "message": "La expresión regular se generó pero no coincide con el texto de muestra. Por favor revisa los límites."
            }
    except Exception as e:
        return {
            "status": "error",
            "regex": pattern,
            "message": f"Error compilando la expresión regular: {str(e)}"
        }

@app.get("/api/extractions/files")
async def get_extraction_files():
    if not os.path.exists(EXTRACTIONS_DIR):
        return []
    files = []
    for f in os.listdir(EXTRACTIONS_DIR):
        if f.endswith('.csv') or f.endswith('.xlsx'):
            path = os.path.join(EXTRACTIONS_DIR, f)
            stat = os.stat(path)
            files.append({
                "filename": f,
                "size": stat.st_size,
                "last_modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    return files

@app.post("/api/extractions/merge")
async def merge_extractions(req: MergeRequest):
    if not req.files:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos un archivo")
        
    dfs = []
    
    for filename in req.files:
        filepath = os.path.join(EXTRACTIONS_DIR, filename)
        if not os.path.exists(filepath):
            continue
            
        # Leer archivo
        if filepath.endswith('.xlsx'):
            df = pd.read_excel(filepath)
        else:
            df = pd.read_csv(filepath, encoding='utf-8-sig')
            
        if df.empty:
            continue
            
        # Buscar columna de clave (Key)
        key_col = None
        for col in df.columns:
            if col.lower() == req.merge_key.lower():
                key_col = col
                break
        if not key_col:
            for col in df.columns:
                if req.merge_key.lower() in col.lower():
                    key_col = col
                    break
        if not key_col:
            key_col = df.columns[0] # Fallback a primera columna
            
        # Buscar columna de precio
        price_col = None
        for col in df.columns:
            if 'price' in col.lower() or 'precio' in col.lower():
                price_col = col
                break
                
        # Limpieza de clave
        df['_merge_key_clean'] = df[key_col].astype(str).str.strip().str.lower()
        
        # Limpieza de precio
        if price_col:
            df['_price_clean'] = df[price_col].apply(lambda x: clean_price(str(x)) if pd.notnull(x) else 0.0)
        else:
            df['_price_clean'] = 0.0
            
        # Desduplicar y tomar el último
        df_clean = df.dropna(subset=['_merge_key_clean']).drop_duplicates(subset=['_merge_key_clean'], keep='last')
        
        provider_name = filename.replace('.csv', '').replace('.xlsx', '').replace('_', ' ').title()
        
        df_clean = df_clean.rename(columns={
            key_col: 'Producto / Modelo',
            '_price_clean': f'Precio {provider_name} (€)'
        })
        
        dfs.append((provider_name, df_clean[['_merge_key_clean', 'Producto / Modelo', f'Precio {provider_name} (€)']]))
        
    if not dfs:
        raise HTTPException(status_code=400, detail="No se encontraron datos procesables en los archivos seleccionados")
        
    # Obtener todas las claves únicas
    keys_dict = {}
    for _, df in dfs:
        for _, row in df.iterrows():
            keys_dict[row['_merge_key_clean']] = row['Producto / Modelo']
            
    merged_df = pd.DataFrame(list(keys_dict.items()), columns=['_merge_key_clean', 'Producto / Modelo'])
    
    price_cols = []
    for provider_name, df in dfs:
        col_name = f'Precio {provider_name} (€)'
        merged_df = pd.merge(merged_df, df[['_merge_key_clean', col_name]], on='_merge_key_clean', how='left')
        price_cols.append(col_name)
        
    merged_df = merged_df.drop(columns=['_merge_key_clean'])
    
    # Calcular diferencia / oportunidad
    def calculate_opportunity(row):
        prices = {}
        for col in price_cols:
            val = row[col]
            if pd.notnull(val) and val > 0:
                prices[col] = val
                
        if len(prices) == 0:
            return "Sin precios cargados"
        if len(prices) == 1:
            prov = list(prices.keys())[0].replace('Precio ', '').replace(' (€)', '')
            return f"Solo disponible en {prov}"
            
        sorted_prices = sorted(prices.items(), key=lambda x: x[1])
        cheapest_provider, cheapest_price = sorted_prices[0]
        second_provider, second_price = sorted_prices[1]
        
        cheapest_name = cheapest_provider.replace('Precio ', '').replace(' (€)', '')
        
        if cheapest_price == second_price:
            second_name = second_provider.replace('Precio ', '').replace(' (€)', '')
            return f"{cheapest_name} empata con {second_name}"
            
        diff_pct = ((cheapest_price - second_price) / second_price) * 100
        return f"{cheapest_name} es {diff_pct:.1f}% más barato"
        
    merged_df['Diferencia / Oportunidad'] = merged_df.apply(calculate_opportunity, axis=1)
    
    # Guardar fusión consolidada
    out_filename = req.output_filename
    if not out_filename.endswith('.xlsx') and not out_filename.endswith('.csv'):
        out_filename += ".xlsx"
        
    out_filepath = os.path.join(CONSOLIDATED_DIR, out_filename)
    
    if out_filepath.endswith('.xlsx'):
        merged_df.to_excel(out_filepath, index=False)
    else:
        merged_df.to_csv(out_filepath, index=False, encoding='utf-8-sig')
        
    # Reemplazar NaN por None para JSON serialización limpia
    merged_df = merged_df.replace({pd.NA: None, float('nan'): None})
    records = merged_df.to_dict(orient='records')
    
    add_log("success", f"Consolidación exitosa guardada en: {out_filename}")
    return {
        "status": "success",
        "file": out_filename,
        "columns": list(merged_df.columns),
        "data": records
    }

@app.get("/api/extractions/download/{provider_id}")
async def download_provider_extraction(provider_id: str):
    from fastapi.responses import FileResponse
    config = load_config()
    providers = config.get("providers", [])
    provider = next((p for p in providers if p["id"] == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado")
        
    filepath = provider.get("output_file")
    if not filepath:
        filepath = os.path.join(EXTRACTIONS_DIR, f"{provider_id}.csv")
        
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Archivo de extracción no encontrado para este proveedor")
        
    filename = os.path.basename(filepath)
    return FileResponse(filepath, media_type="application/octet-stream", filename=filename)

@app.get("/api/consolidated/download/{filename}")
async def download_consolidated(filename: str):
    from fastapi.responses import FileResponse
    filepath = os.path.join(CONSOLIDATED_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    return FileResponse(filepath, media_type="application/octet-stream", filename=filename)

@app.get("/api/stream")
async def sse_stream():
    async def event_generator():
        last_sent_idx = latest_log_index
        # Envío inicial del búfer de logs
        yield f"data: {json.dumps({'type': 'init', 'logs': logs_buffer}, ensure_ascii=False)}\n\n"
        while True:
            await asyncio.sleep(0.5)
            if last_sent_idx < latest_log_index:
                diff = latest_log_index - last_sent_idx
                start_pos = max(0, len(logs_buffer) - diff)
                new_logs = logs_buffer[start_pos:]
                for log in new_logs:
                    yield f"data: {json.dumps({'type': 'log', 'log': log}, ensure_ascii=False)}\n\n"
                last_sent_idx = latest_log_index
            else:
                yield f"data: {json.dumps({'type': 'ping'}, ensure_ascii=False)}\n\n"
                
    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
