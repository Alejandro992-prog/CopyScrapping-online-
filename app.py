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

def process_text(text: str, provider: Dict[str, Any]):
    regex_pattern = provider.get("regex")
    if not regex_pattern:
        return
        
    try:
        match = re.match(regex_pattern, text.strip())
        if match:
            data = match.groupdict()
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
    last_idx = 0
    
    for i, label in enumerate(sorted_labels):
        start = label.start
        end = label.end
        name = label.name
        
        # Segmento literal antes del label
        literal = raw_text[last_idx:start]
        escaped_literal = re.escape(literal)
        # Estandarizar espacios
        escaped_literal = escaped_literal.replace('\\ ', '\\s+')
        parts.append(escaped_literal)
        
        # Grupo de captura
        parts.append(f"(?P<{name}>.+?)")
        last_idx = end
        
    # Literal después del último label
    literal_end = raw_text[last_idx:]
    escaped_literal_end = re.escape(literal_end)
    escaped_literal_end = escaped_literal_end.replace('\\ ', '\\s+')
    parts.append(escaped_literal_end)
    
    pattern = "^" + "".join(parts) + "$"
    
    # Validar que haga match con el texto original
    try:
        match = re.match(pattern, raw_text.strip())
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
                "message": "La expresión regular se generó pero no coincide de forma exacta con el texto de muestra. Ajusta los límites."
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
