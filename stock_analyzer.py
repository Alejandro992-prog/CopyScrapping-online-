import os
import sys
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from difflib import SequenceMatcher

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    openpyxl = None
    Workbook = None

def get_base_data_dir() -> str:
    """Retorna la ruta absoluta hacia el directorio de datos."""
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.abspath(".")
    data_dir = os.path.join(base_path, "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def get_history_dir() -> str:
    history_dir = os.path.join(get_base_data_dir(), "stock", "history")
    os.makedirs(history_dir, exist_ok=True)
    return history_dir

def get_tariffs_dir() -> str:
    tariffs_dir = os.path.join(get_base_data_dir(), "tariffs")
    os.makedirs(tariffs_dir, exist_ok=True)
    return tariffs_dir

def save_tariff(
    provider_name: str,
    tariff_name: str,
    file_type: str,
    original_filename: str,
    items: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Guarda una tarifa de proveedor procesada en data/tariffs/."""
    tariffs_dir = get_tariffs_dir()
    now = datetime.now()
    clean_p = re.sub(r'[^a-zA-Z0-9]', '_', (provider_name or "proveedor").strip().lower())
    tariff_id = f"{clean_p}_{now.strftime('%Y%m%d_%H%M%S')}"
    
    tariff_data = {
        "id": tariff_id,
        "provider_name": provider_name.strip() if provider_name else "Proveedor",
        "tariff_name": tariff_name.strip() if tariff_name else f"Tarifa {now.strftime('%d/%m/%Y')}",
        "file_type": file_type.lower(),
        "original_filename": original_filename,
        "upload_date": now.strftime("%Y-%m-%d"),
        "created_at": now.isoformat(),
        "total_items": len(items),
        "items": items
    }
    filepath = os.path.join(tariffs_dir, f"tariff_{tariff_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(tariff_data, f, indent=2, ensure_ascii=False)
    return tariff_data

def get_tariffs_list() -> List[Dict[str, Any]]:
    """Devuelve la lista de todas las tarifas de proveedores registradas."""
    tariffs_dir = get_tariffs_dir()
    result = []
    for fname in os.listdir(tariffs_dir):
        if fname.startswith("tariff_") and fname.endswith(".json"):
            fpath = os.path.join(tariffs_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    result.append({
                        "id": d.get("id"),
                        "provider_name": d.get("provider_name"),
                        "tariff_name": d.get("tariff_name"),
                        "file_type": d.get("file_type"),
                        "original_filename": d.get("original_filename"),
                        "upload_date": d.get("upload_date"),
                        "total_items": d.get("total_items", 0)
                    })
            except Exception:
                continue
    result.sort(key=lambda x: x.get("upload_date", ""), reverse=True)
    return result

def load_tariff(tariff_id: str) -> Optional[Dict[str, Any]]:
    """Carga una tarifa de proveedor por su ID."""
    tariffs_dir = get_tariffs_dir()
    safe_id = str(tariff_id).replace("tariff_", "").strip()
    candidate = os.path.join(tariffs_dir, f"tariff_{safe_id}.json")
    if not os.path.exists(candidate):
        candidate = os.path.join(tariffs_dir, f"{tariff_id}.json")
    if not os.path.exists(candidate):
        return None
    try:
        with open(candidate, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def delete_tariff(tariff_id: str) -> bool:
    """Elimina una tarifa guardada."""
    tariffs_dir = get_tariffs_dir()
    safe_id = str(tariff_id).replace("tariff_", "").strip()
    candidate = os.path.join(tariffs_dir, f"tariff_{safe_id}.json")
    if os.path.exists(candidate):
        try:
            os.remove(candidate)
            return True
        except Exception:
            return False
    return False

def normalize_sku(sku: str) -> str:
    """Normaliza un SKU/Modelo eliminando espacios, guiones, barras y pasando a mayúsculas."""
    if not sku:
        return ""
    s = str(sku).upper().strip()
    s = re.sub(r'[\s\-/\._]', '', s)
    return s

def extract_base_model(sku: str) -> str:
    """
    Extrae el modelo base eliminando revisiones de fabricante (/01, /02), sufijos de país
    (-ES, -XPN, -IB) y acabados/colores industriales (-WH, -IX, -BK, etc.).
    """
    if not sku:
        return ""
    s = str(sku).upper().strip()
    # 1. Eliminar revisiones de fabricante ej. /01, /02, .01
    s = re.sub(r'[/\.]\d{1,2}$', '', s)
    # 2. Eliminar sufijos precedidos de separador (- _ / .)
    s = re.sub(r'[-_/\.](?:ES|XPN|SP|IB|EU|FR|IT|PT|WH|WHITE|BL|BLANCO|BK|BLACK|NEG|NEGRO|IX|INX|INOX|STEEL|ACERO|SL|SILVER|PLATA|GR|GREY|GRIS|W|B|X)$', '', s)
    # 3. Eliminar sufijos de color o mercado pegados tras números si la base resultante tiene al menos 4 caracteres
    m = re.search(r'^([A-Z0-9]{3,}[0-9])(?:ES|XPN|SP|IB|WH|WHITE|BL|BK|BLACK|IX|INX|INOX|W|B|X)$', s)
    if m:
        s = m.group(1)
    s = re.sub(r'[\s\-/\._]', '', s)
    return s

def extract_model_color(model: str, text: str = "") -> str:
    """
    Identifica el color o acabado de un electrodoméstico (INOX, BLANCO, NEGRO, TITANIO).
    Previene que variantes de distinto color (ej. MWF230-IX y MWF230-B) se crucen erróneamente.
    """
    combined = f"{model} {text}".upper()
    if any(k in combined for k in ["TITANIO", "TITANIUM", "GRAFITO", "GRAPHITE", "DARK INOX", "SILVER", "PLATA", "-SL", "-GR"]):
        return "TITANIO"
    if any(k in combined for k in ["-IX", "/IX", " INOX", "-INOX", "ACERO INOX", "STAINLESS", "ACERO"]) or model.upper().endswith(("IX", "INX", "X")):
        return "INOX"
    if any(k in combined for k in ["-WH", "-BL", "-WHITE", "WHITE", "BLANCO", "-B", "/B"]) or model.upper().endswith(("WH", "BL", "W")):
        return "BLANCO"
    if any(k in combined for k in ["-BK", "-NEG", "-BLACK", "NEGRO", "BLACK"]) or model.upper().endswith(("BK", "NB")):
        return "NEGRO"
    return ""

def normalize_ean_variants(ean_raw: str) -> List[str]:
    """Genera variantes comunes de EAN para evitar discrepancias por ceros a la izquierda o formatos 12/13/14 dígitos."""
    if not ean_raw:
        return []
    digits = re.sub(r'\D', '', str(ean_raw).strip())
    if len(digits) < 7:
        return []
    variants = {digits}
    if len(digits) == 12:
        variants.add("0" + digits)
    elif len(digits) == 13 and digits.startswith("0"):
        variants.add(digits[1:])
    elif len(digits) > 8:
        variants.add(digits.zfill(13))
    return list(variants)

def fuzzy_match_sku(
    norm_model: str, 
    candidates: Dict[str, Dict[str, Any]], 
    min_ratio: float = 0.85
) -> Optional[Tuple[Dict[str, Any], float, str]]:
    """
    Busca la mejor coincidencia difusa (fuzzy) para un modelo en el diccionario de candidatos.
    Aplica filtros de coherencia numérica para evitar emparejamientos erróneos entre distintas gamas.
    """
    if not norm_model or len(norm_model) < 4:
        return None
        
    nums1 = re.findall(r'\d{2,}', norm_model)
    best_cand_item = None
    best_score = 0.0
    best_cand_sku = ""
    
    # Ajustar ratio mínimo según longitud (códigos más cortos requieren mayor precisión)
    effective_min_ratio = 0.88 if len(norm_model) <= 6 else min_ratio

    for cand_sku, cand_item in candidates.items():
        if abs(len(cand_sku) - len(norm_model)) > 3:
            continue
            
        # Si ambos tienen secuencias numéricas de 2+ dígitos, deben coincidir o contenerse
        if nums1:
            nums2 = re.findall(r'\d{2,}', cand_sku)
            if nums2:
                n1, n2 = nums1[0], nums2[0]
                if n1 != n2 and n1 not in n2 and n2 not in n1:
                    continue

        ratio = SequenceMatcher(None, norm_model, cand_sku).ratio()
        if ratio >= effective_min_ratio and ratio > best_score:
            best_score = ratio
            best_cand_item = cand_item
            best_cand_sku = cand_sku

    if best_cand_item:
        return (best_cand_item, round(best_score, 2), best_cand_sku)
    return None

# Caché persistente de clasificación de modelos (evita re-consultar a Gemini o recalcular)
_appliance_cache = None

def get_appliance_cache_file() -> str:
    return os.path.join(get_base_data_dir(), "appliance_models_cache.json")

def load_appliance_cache() -> Dict[str, str]:
    """Carga el diccionario de modelos ya clasificados desde disco."""
    global _appliance_cache
    if _appliance_cache is not None:
        return _appliance_cache
    fpath = get_appliance_cache_file()
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                _appliance_cache = json.load(f)
                return _appliance_cache
        except Exception:
            _appliance_cache = {}
            return _appliance_cache
    _appliance_cache = {}
    return _appliance_cache

def update_appliance_cache(new_entries: Dict[str, str]):
    """Actualiza la caché persistente con nuevos modelos clasificados."""
    global _appliance_cache
    cache = load_appliance_cache()
    changed = False
    for k, v in new_entries.items():
        clean_k = normalize_sku(k)
        clean_v = str(v).strip()
        if clean_k and clean_v and clean_v != "Otros":
            if cache.get(clean_k) != clean_v:
                cache[clean_k] = clean_v
                changed = True
    if changed:
        _appliance_cache = cache
        fpath = get_appliance_cache_file()
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error persistiendo caché de electrodomésticos: {e}")

def decode_model_prefix(model: str, brand: str = "") -> Optional[str]:
    """
    Decodifica el tipo de aparato basándose en la nomenclatura estándar y prefijos de fabricantes
    (Infiniton, Beko, Balay/BSH, Teka, Cecotec, Candy, etc.). Gasto: 0 tokens, instantáneo.
    """
    if not model:
        return None
    m = normalize_sku(model)
    
    # 1. Lavado y Secado combinado
    if m.startswith(('WSD', 'LAVASECADORA', 'WASHERDRYER', 'HTV', 'WDU', 'WD')):
        return 'Lavadoras-Secadoras'
        
    # 2. Lavadoras
    if m.startswith(('TLW', 'WM', '3TS', '3TI', 'WAN', 'WAU', 'WTE', 'BM3WFU', 'B3WFU', 'TKD', 'WMT', 'EVO', 'CSS', 'RO', 'RP')):
        return 'Lavadoras'
        
    # 3. Secadoras
    if m.startswith(('SD', '3SB', 'WTN', 'WQG', 'B3T', 'DH7', 'DH8', 'DH9', 'DF7', 'DF8', 'CSOE', 'NDPE')):
        return 'Secadoras'
        
    # 4. Lavavajillas (distinguiendo 45cm y 60cm si es posible)
    if m.startswith(('DIW45', 'DW45', 'DFS', 'DIS', 'SPS', '3VN', 'CDPH', 'CDP45')):
        return 'Lavavajillas 45cm'
    if m.startswith(('DIW', 'DW', '3VS', '3VT', 'SMS', 'SMV', 'BDEN', 'DFN', 'DIN', 'DFI', 'CDPN', 'CDIN', 'HIA')):
        return 'Lavavajillas 60cm'
        
    # 5. Frigoríficos y Congeladores
    if m.startswith(('SBS', 'FRD', 'AMCB', 'GNE', 'KAD', 'FD', 'HCR')):
        return 'Frigos americanos'
    if m.startswith(('FGC', '3KFE', '3KFC', 'KGN', 'KGF', 'RCNE', 'RCNT', 'B5RCNE', 'B3RCNE', 'NFL', 'NFE', 'RBF', 'CCE', 'HBE')):
        return 'Frigo Combi'
    if m.startswith(('CLR', 'CL', 'KSW', '3FCE', 'SVE')):
        return 'Frigo 1 puerta'
    if m.startswith(('CVF', 'CV', 'GSN', '3GIE', 'GF', 'HCE')):
        return 'Congelador Vertical'
    if m.startswith(('FCH', 'CH', 'HSMCONG', 'CF', 'OF')):
        return 'Congelador Horizontal'
    if m.startswith(('FG2', 'FGD', 'FG', 'RDNT', 'KD', 'CTE')):
        return 'Frigo 2 puertas'
        
    # 6. Cocción, Hornos y Microondas
    if m.startswith(('HOR', 'HSM', '3HB', 'HBA', 'HBJ', 'BBIE', 'BBIM', 'BIE', 'HLC', 'HLB', 'HBE', 'FCP', 'FIDC')):
        return 'Hornos'
    if m.startswith(('IMW', 'MW', '3CG', '3CP', 'MGB', 'BMO', 'MIC', 'CMI')):
        return 'Microondas'
    if m.startswith(('INPT', 'IND', 'BIN', '3EB', 'PIE', 'PUJ', 'HII', 'IBC', 'IZC', 'CI', 'CTP')):
        return 'Inducción'
    if m.startswith(('VIT', '3ET', 'HIC', 'TZ', 'TB', 'CH', 'EVT')):
        return 'Vitrocerámica'
    if m.startswith(('GGP', 'GAS', 'GG', '3ETG', 'HIZG', 'HIA', 'CG', 'GPC')):
        return 'Placa de Gas'
    if m.startswith(('CC9', 'CC', 'CG9', 'CGE')):
        return 'Cocinas'
        
    # 7. Extracción
    if m.startswith(('CMPTRAL', 'CMPT', 'CMPP', 'CMPG', 'CMPB', 'CMP', '3BC', '3BD', 'DWK', 'HCA', 'BHCA', 'CTB', 'GFH', 'CNL', 'TL', 'DBB', '76AGX', '78GLN', 'HHW')):
        return 'Campana'
        
    # 8. Climatización, Agua y Vinotecas
    if m.startswith(('CAS', 'SPLIT', 'AC', 'INV')):
        return 'Aire Acondicionado'
    if m.startswith(('WCL', 'WFL', 'CWC', 'DIV')):
        return 'Vinotecas'
    if m.startswith(('CAB3HV', 'HV', 'HWR', 'GWA', 'GWB', 'GWN', 'TS', 'TRE')):
        return 'Termos y Calentadores'
    if m.startswith(('DHM', 'DEHUM')):
        return 'Deshumidificadores'
    if m.startswith(('AP2', 'AP3', 'AIRPUR')):
        return 'Purificadores de Aire'
    if m.startswith(('GRILL',)):
        return 'Microondas'
        
    return None

def classify_appliance_type(text: str, model: str = "") -> str:
    """
    Identifica el tipo de aparato (categoría canónica).
    Flujo de alta eficiencia:
    1. Caché local persistente (0 tokens).
    2. Reglas por texto descriptivo.
    3. Decodificador de prefijos de fabricante (0 tokens).
    4. Diccionario de sinónimos.
    """
    if not text and not model:
        return "Otros"
        
    # 1. Comprobar primero en la caché persistente de modelos
    if model:
        norm_m = normalize_sku(model)
        cache = load_appliance_cache()
        if norm_m in cache:
            return cache[norm_m]

    combined = f"{text} {model}".lower()
    
    # 2. Caso especial combinado
    if ("lavadora" in combined and "secadora" in combined) or any(s in combined for s in ["lavasecadora", "lavasecadoras", "washer dryer", "washer-dryer", "lava-secadora"]):
        return "Lavadoras-Secadoras"
    
    # 3. Lavavajillas
    if any(s in combined for s in ["lavavajillas 45", "lavaplatos 45", "45 cm", "45cm", "estrecho"]) and any(s in combined for s in ["lavavajillas", "lavaplatos", "dishwasher"]):
        return "Lavavajillas 45cm"
    if any(s in combined for s in ["lavavajillas", "lavaplatos", "dishwasher", "lavavasos"]):
        return "Lavavajillas 60cm"
        
    # 4. Frigoríficos
    if any(s in combined for s in ["americano", "americanos", "side by side", "side-by-side", "multipuerta", "french door", "4 puertas"]):
        return "Frigos americanos"
    if any(s in combined for s in ["combi", "combis", "combinado"]):
        return "Frigo Combi"
    if any(s in combined for s in ["1 puerta", "una puerta", "monopuerta", "cooler", "table top", "tabletop", "congelador vertical", "congeladores verticales"]):
        return "Frigo 1 puerta"
    if any(s in combined for s in ["2 puertas", "dos puertas", "2 ptas", "dos-puertas"]):
        return "Frigo 2 puertas"
    if any(s in combined for s in ["integrable", "integrables", "encastrable", "panelable"]) and any(s in combined for s in ["frigo", "frigorifico", "frigorífico", "nevera"]):
        return "Frigos integrables"
    if any(s in combined for s in ["congelador horizontal", "arcon", "arcón", "chest freezer"]):
        return "Congelador Horizontal"
    if any(s in combined for s in ["frigorifico", "frigorífico", "frigo", "refrigerador", "congelador", "freezer", "nevera"]):
        return "Frigoríficos"
        
    # 5. Lavado y secado
    if any(s in combined for s in ["lavadora", "washer", "lavarropa", "carga frontal", "carga superior"]):
        return "Lavadoras"
    if any(s in combined for s in ["secadora", "dryer", "bomba de calor", "heat pump"]):
        return "Secadoras"
        
    # 6. Cocción y extracción
    if any(s in combined for s in ["induccion", "inducción", "flex induction", "flexinduccion"]):
        return "Inducción"
    if any(s in combined for s in ["vitroceramica", "vitrocerámica", "radiante", "hilight"]):
        return "Vitrocerámica"
    if any(s in combined for s in ["placa gas", "cristal gas", "butano", "gas natural", "encimera gas"]) or (any(s in combined for s in ["placa", "encimera"]) and "gas" in combined):
        return "Placa de Gas"
    if any(s in combined for s in ["vitro", "placa", "encimera"]):
        return "Vitrocerámicas"
    if any(s in combined for s in ["horno", "oven", "pirolitico", "pirolítico", "multifuncion", "multifunción"]):
        return "Hornos"
    if any(s in combined for s in ["microondas", "microwave"]):
        return "Microondas"
    if any(s in combined for s in ["campana", "extractor", "decorativa", "grupo filtrante"]):
        return "Campana"
    if any(s in combined for s in ["televisor", "television", "televisión", "smart tv", "tv", "qled", "oled"]):
        return "Televisor"
    if any(s in combined for s in ["termo", "calentador", "acumulador agua"]):
        return "Termos y Calentadores"
    if any(s in combined for s in ["aire acondicionado", "climatizador", "split"]):
        return "Aire Acondicionado"
    if any(s in combined for s in ["vinoteca", "cava de vino", "vinera"]):
        return "Vinotecas"
    if any(s in combined for s in ["deshumidificador"]):
        return "Deshumidificadores"
        
    # 7. Decodificación precisa por prefijo/código de modelo del fabricante
    if model:
        decoded = decode_model_prefix(model)
        if decoded:
            return decoded
            
    # 8. Fallback a data/dictionary.json si existe
    try:
        dict_path = os.path.join(get_base_data_dir(), "dictionary.json")
        if os.path.exists(dict_path):
            with open(dict_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                cats = d.get("categorias", {})
                for cat_k, cat_v in cats.items():
                    syns = cat_v.get("sinonimos", [])
                    if any(syn in combined for syn in syns):
                        return cat_k
    except Exception:
        pass
        
    return "Otros"

def extract_appliance_features(text: str, model: str = "") -> str:
    """Extrae características técnicas clave (capacidad, revoluciones, zonas, tecnología, color/acabado) de texto y modelo."""
    if not text and not model:
        return ""
    combined_raw = f"{text} {model}".strip()
    features = []
    
    # 1. Capacidad en kg (Lavadoras / Secadoras)
    m_kg = re.search(r'\b(\d+(?:[\.,]\d+)?)\s*(?:kg|kilos|kilogramos)\b', combined_raw, re.IGNORECASE)
    if not m_kg and model:
        m_kg_code = re.search(r'(?:WM|TLW|SD|WSD)[-_]?(\d{1,2})(?:\d{2})?', model.upper())
        if m_kg_code and int(m_kg_code.group(1)) in range(5, 16):
            m_kg = m_kg_code
    if m_kg:
        features.append(f"{m_kg.group(1)} kg")
        
    # 2. Revoluciones (rpm)
    m_rpm = re.search(r'\b(\d{3,4})\s*(?:rpm|r\.p\.m\.|rev)\b', combined_raw, re.IGNORECASE)
    if not m_rpm and model:
        m_rpm_code = re.search(r'(?:WM|WSD)[-_]?\d{1,2}(\d{2})\b', model.upper())
        if m_rpm_code:
            digits = m_rpm_code.group(1)
            if digits in ["10", "12", "14", "16"]:
                features.append(f"{digits}00 rpm")
    elif m_rpm:
        features.append(f"{m_rpm.group(1)} rpm")
        
    # 3. Capacidad en litros (Frigoríficos / Hornos / Microondas / Termos / Deshumidificadores)
    m_l = re.search(r'\b(\d{2,3})\s*(?:l|litros|lts)\b', combined_raw, re.IGNORECASE)
    if not m_l and model:
        m_l_code = re.search(r'[-_](\d{2,3})[lL]\b|HV(\d{2,3})T|[-_](\d{2,3})[A-Z]?$', model.upper())
        if m_l_code:
            found_l = m_l_code.group(1) or m_l_code.group(2) or m_l_code.group(3)
            if found_l and 10 <= int(found_l) <= 650:
                features.append(f"{found_l} L")
    elif m_l:
        features.append(f"{m_l.group(1)} L")
        
    # 4. Servicios / cubiertos (Lavavajillas)
    m_serv = re.search(r'\b(\d{1,2})\s*(?:cubiertos|servicios)\b', combined_raw, re.IGNORECASE)
    if m_serv:
        features.append(f"{m_serv.group(1)} cubiertos")
        
    # 5. Zonas de cocción (Placas)
    m_zonas = re.search(r'\b([2-5])\s*(?:zonas|fuegos)\b', combined_raw, re.IGNORECASE)
    if m_zonas:
        features.append(f"{m_zonas.group(1)} zonas")
        
    # 6. Altura/Medida en cm (Frigoríficos / Lavavajillas)
    m_cm = re.search(r'\b(1[4-9]\d|20\d)\s*(?:cm)?\b', combined_raw)
    if not m_cm and model:
        m_cm_code = re.search(r'(?:FGC|FG|CL|CV)[-_]?(\d{3})\b', model.upper())
        if m_cm_code and 140 <= int(m_cm_code.group(1)) <= 205:
            features.append(f"{m_cm_code.group(1)} cm")
    elif m_cm and any(k in combined_raw.lower() for k in ["frigo", "combi", "nevera", "congelador", "fgc"]):
        features.append(f"{m_cm.group(1)} cm")
        
    # Medida lavavajillas en modelo
    if "45" in model and any(k in model.upper() for k in ["DIW45", "DW45", "DFS", "3VN"]):
        features.append("45 cm")
    elif any(k in model.upper() for k in ["DIW60", "DW60", "3VS", "DFN"]):
        features.append("60 cm")
        
    # 7. Tecnología relevante
    t_lower = combined_raw.lower()
    if "no frost" in t_lower or "total no frost" in t_lower:
        features.append("No Frost")
    elif "low frost" in t_lower:
        features.append("Low Frost")
    if "bomba de calor" in t_lower or "heat pump" in t_lower:
        features.append("Bomba de calor")
    if "pirolitico" in t_lower or "pirolítico" in t_lower or "pirólisis" in t_lower:
        features.append("Pirolítico")
    if "inverter" in t_lower:
        features.append("Inverter")
        
    # 8. Acabado / Color
    if re.search(r'\b(?:inox|acero|acero inoxidable)\b', t_lower) or model.upper().endswith(('X', 'IX', 'INX')):
        features.append("Inox")
    elif re.search(r'\b(?:blanco|white)\b', t_lower) or model.upper().endswith(('W', 'WH', 'BL')):
        features.append("Blanco")
    elif re.search(r'\b(?:negro|black|cristal negro)\b', t_lower) or model.upper().endswith(('B', 'BK', 'NB')):
        features.append("Negro")
        
    # Eliminar duplicados manteniendo orden
    seen = set()
    unique_feats = []
    for f in features:
        if f.lower() not in seen:
            seen.add(f.lower())
            unique_feats.append(f)
            
    return " • ".join(unique_feats)


def parse_excel_tariff(filepath: str, default_provider: str = "") -> List[Dict[str, Any]]:
    """Extrae productos y precios desde un archivo Excel o CSV de tarifa de proveedor con detección inteligente de cabecera y columnas."""
    if pd is None:
        return []
    try:
        kw_list = ['modelo', 'model', 'sku', 'referencia', 'código', 'codigo', 'ref', 'articulo', 'artículo', 'descripción', 'descripcion', 'producto', 'precio', 'pvp', 'coste', 'neto', 'cesión', 'cesion', 'tarifa', 'marca']
        if filepath.endswith(".csv"):
            df_raw = pd.read_csv(filepath, header=None, nrows=20, encoding='utf-8-sig')
            best_idx = 0
            max_kw = 0
            for idx, row in df_raw.iterrows():
                row_strs = [str(v).strip().lower() for v in row.values if pd.notna(v)]
                matches = sum(1 for v in row_strs if any(k in v for k in kw_list))
                if matches > max_kw:
                    max_kw = matches
                    best_idx = idx
            df = pd.read_csv(filepath, header=best_idx if max_kw >= 2 else 0, encoding='utf-8-sig')
        else:
            with pd.ExcelFile(filepath) as xl:
                target_sheet = xl.sheet_names[0]
                for s in xl.sheet_names:
                    slow = s.lower()
                    if any(k in slow for k in ['tarifa', 'precios', 'general', 'catalogo', 'articulos', 'productos']):
                        target_sheet = s
                        break
                
                df_raw = xl.parse(target_sheet, header=None, nrows=25)
                best_idx = 0
                max_kw = 0
                for idx, row in df_raw.iterrows():
                    row_strs = [str(v).strip().lower() for v in row.values if pd.notna(v)]
                    matches = sum(1 for v in row_strs if any(k in v for k in kw_list))
                    if matches > max_kw:
                        max_kw = matches
                        best_idx = idx
                
                df = xl.parse(target_sheet, header=best_idx if max_kw >= 2 else 0)
    except Exception as e:
        print(f"Error leyendo archivo Excel de tarifa: {e}")
        return []

    cols = [str(c).strip() for c in df.columns if pd.notna(c) and not str(c).startswith("Unnamed:")]
    col_map = {}
    
    # 1. Identificar columnas específicas con prioridad clara
    for c in df.columns:
        clow = str(c).strip().lower()
        if 'unnamed:' in clow:
            continue
        if not col_map.get("brand") and any(k in clow for k in ["marca", "brand", "fabricante"]):
            col_map["brand"] = c
        elif not col_map.get("model") and any(k in clow for k in ["modelo", "model"]):
            col_map["model"] = c
        elif not col_map.get("sku") and any(k in clow for k in ["sku", "referencia", "código", "codigo", "ref."]):
            col_map["sku"] = c
        elif not col_map.get("ean") and any(k in clow for k in ["ean", "gtin", "barras"]):
            col_map["ean"] = c
        elif not col_map.get("product") and any(k in clow for k in ["descripcion", "descripción", "producto", "articulo", "artículo", "concepto", "nombre"]):
            col_map["product"] = c

    # 2. Si no encontró 'model' específico, usar 'sku' o 'referencia' (nunca la marca)
    if not col_map.get("model") and col_map.get("sku"):
        col_map["model"] = col_map["sku"]

    # 3. Detectar precio con orden de preferencia estricto
    for c in df.columns:
        clow = str(c).strip().lower()
        if 'unnamed:' in clow or any(bad in clow for bad in ['ecotasa', 'descuento', 'oferta', '%', 'unidades', 'pedido', 'minima']):
            continue
        if any(k in clow for k in ["neto factura", "neto con promo", "precio neto", "neto"]):
            col_map["price"] = c
            break

    if not col_map.get("price"):
        for c in df.columns:
            clow = str(c).strip().lower()
            if 'unnamed:' in clow or any(bad in clow for bad in ['ecotasa', 'descuento', 'oferta', '%', 'unidades', 'pedido', 'minima']):
                continue
            if any(k in clow for k in ["cesión", "cesion", "pvpr", "pvp", "tarifa", "coste", "precio"]):
                col_map["price"] = c
                break

    # Fallback si no encontró modelo: buscar entre columnas que no sean marca ni precio
    if not col_map.get("model") and len(cols) > 0:
        non_brand_cols = [
            c for c in cols 
            if (not col_map.get("brand") or c != col_map["brand"]) 
            and (not col_map.get("price") or c != col_map["price"])
            and not any(bad in str(c).lower() for bad in ["marca", "brand", "fabricante", "precio", "pvp", "coste"])
        ]
        if non_brand_cols:
            col_map["model"] = non_brand_cols[0]

    items = []
    brand_default_norm = (default_provider or "").strip().upper()

    for _, row in df.iterrows():
        r = row.to_dict()
        model_val = str(r.get(col_map.get("model", ""), "")).strip() if col_map.get("model") else ""
        product_val = str(r.get(col_map.get("product", ""), "")).strip() if col_map.get("product") else ""
        brand_val = str(r.get(col_map.get("brand", ""), "")).strip() if col_map.get("brand") else default_provider
        ean_val = str(r.get(col_map.get("ean", ""), "")).strip() if col_map.get("ean") else ""
        raw_price = r.get(col_map.get("price", ""), 0) if col_map.get("price") else 0
        
        # Descartar cabeceras repetidas en medio de los datos
        if model_val.upper() in ["NAN", "NONE", "", "MARCA", "BRAND", "MODELO", "MODEL", "SKU", "REFERENCIA", "CODIGO", "CÓDIGO"]:
            model_val = ""
        if product_val.upper() in ["NAN", "NONE", "", "DESCRIPCIÓN", "DESCRIPCION", "PRODUCTO", "ARTICULO", "ARTÍCULO"]:
            product_val = ""
            
        # Si el modelo coincide exactamente con la marca (ej. 'BEKO'), comprobar si hay otra columna con el modelo real
        if (brand_val and model_val.upper() == brand_val.upper()) or (brand_default_norm and model_val.upper() == brand_default_norm):
            sku_cand = str(r.get(col_map.get("sku", ""), "")).strip() if col_map.get("sku") else ""
            if sku_cand and sku_cand.upper() != brand_val.upper() and sku_cand.upper() != brand_default_norm and sku_cand not in ["nan", "None"]:
                model_val = sku_cand
            else:
                # Si no hay SKU diferente a la marca, no podemos usar el nombre de la marca como modelo
                continue

        if not model_val and not product_val:
            continue
            
        price_val = 0.0
        if isinstance(raw_price, (int, float)):
            price_val = float(raw_price) if pd.notna(raw_price) else 0.0
        else:
            p_str = str(raw_price).replace("€", "").replace("EUR", "").strip()
            if '.' in p_str and ',' in p_str:
                p_str = p_str.replace('.', '').replace(',', '.')
            elif ',' in p_str:
                p_str = p_str.replace(',', '.')
            try:
                price_val = float(re.sub(r'[^\d\.]', '', p_str))
            except Exception:
                price_val = 0.0

        if price_val > 50000:
            price_val = price_val / 100.0 if price_val < 5000000 else 0.0

        final_brand = brand_val or default_provider
        final_product = product_val or f"{final_brand} {model_val}"
        
        cat_val = classify_appliance_type(final_product + " " + model_val, model_val)
        feat_val = extract_appliance_features(final_product)

        items.append({
            "model": model_val or product_val[:25],
            "product": final_product,
            "ean": ean_val if ean_val not in ["nan", "None"] else "",
            "price": round(price_val, 2),
            "brand": final_brand,
            "category": cat_val,
            "attributes": feat_val
        })
    return items

def parse_pdf_tariff(filepath: str, default_provider: str = "", api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Extrae productos y precios desde un PDF de tarifa enviado por el proveedor."""
    import pypdf
    items = []
    raw_text = ""
    try:
        with open(filepath, "rb") as f_pdf:
            reader = pypdf.PdfReader(f_pdf)
            for page in reader.pages:
                t = page.extract_text() or ""
                raw_text += t + "\n"
                for line in t.split("\n"):
                    line_str = line.strip()
                    if not line_str or len(line_str) < 5:
                        continue
                    price_match = re.search(r'(\b\d{1,4}(?:[\.,]\d{2})\b)\s*(?:€|EUR)?', line_str)
                    model_match = re.search(r'\b(?=[A-Z0-9/-]*[0-9])(?=[A-Z0-9/-]*[A-Z])[A-Z0-9/-]{4,25}\b', line_str)
                    if price_match and model_match:
                        model_str = model_match.group(0)
                        p_raw = price_match.group(1)
                        if '.' in p_raw and ',' in p_raw:
                            p_raw = p_raw.replace('.', '').replace(',', '.')
                        elif ',' in p_raw:
                            p_raw = p_raw.replace(',', '.')
                        try:
                            p_val = float(p_raw)
                        except Exception:
                            p_val = 0.0
                        desc_str = line_str.replace(model_str, "").replace(price_match.group(0), "").strip()
                        if not desc_str:
                            desc_str = f"{default_provider} {model_str}"
                        cat_val = classify_appliance_type(desc_str + " " + model_str, model_str)
                        feat_val = extract_appliance_features(desc_str)
                        items.append({
                            "model": model_str,
                            "product": desc_str,
                            "price": round(p_val, 2),
                            "brand": default_provider,
                            "category": cat_val,
                            "attributes": feat_val
                        })
    except Exception as e:
        print(f"Error parseando PDF de tarifa: {e}")

    # Si con regex se extrajeron pocos datos y hay clave de Gemini, invocar extracción estructurada
    if len(items) < 3 and api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            prompt = f"""Extrae todos los modelos y precios de coste de esta tarifa del proveedor '{default_provider}'.
Devuelve ÚNICAMENTE un JSON válido con la lista:
[
  {{"model": "CODIGO_MODELO", "product": "DESCRIPCION", "price": 299.00}}
]
Texto del PDF:
{raw_text[:12000]}
"""
            candidate_models = ["gemini-3.6-flash", "gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
            resp = None
            for m in candidate_models:
                try:
                    resp = client.models.generate_content(
                        model=m,
                        contents=prompt
                    )
                    if resp and resp.text:
                        break
                except Exception:
                    continue

            resp_text = resp.text if resp else ""
            clean_json = re.sub(r'^```json\s*|^```\s*|```$', '', resp_text.strip(), flags=re.MULTILINE)
            gemini_items = json.loads(clean_json)
            if isinstance(gemini_items, list) and len(gemini_items) > 0:
                items = []
                for it in gemini_items:
                    m = str(it.get("model", "")).strip()
                    p = str(it.get("product", "")).strip()
                    pr = float(it.get("price", 0.0))
                    if m:
                        cat_val = classify_appliance_type(p + " " + m, m)
                        feat_val = extract_appliance_features(p)
                        items.append({
                            "model": m,
                            "product": p,
                            "price": round(pr, 2),
                            "brand": default_provider,
                            "category": cat_val,
                            "attributes": feat_val
                        })
        except Exception as e_gem:
            print(f"Gemini fallback en PDF de tarifa: {e_gem}")

    return items

def extract_date_from_text(text: str) -> Optional[str]:
    """Extrae una fecha (YYYY-MM-DD) desde el texto de cabecera o metadatos de un PDF/informe."""
    if not text:
        return None
    
    # Patrones comunes en informes ERP españoles:
    # 1. "Fecha: 15/09/2026", "a fecha 15-09-2026", "15.09.2026"
    m = re.search(r'(?:fecha|existencias\s*a|informe\s*al?|inventario\s*al?)\s*[:\s]*(\d{1,2})[/\.-](\d{1,2})[/\.-](\d{2,4})', text, re.IGNORECASE)
    if m:
        d, mth, y = m.group(1), m.group(2), m.group(3)
        if len(y) == 2:
            y = "20" + y
        try:
            dt = datetime(int(y), int(mth), int(d))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    # 2. Fecha genérica tipo DD/MM/YYYY
    m2 = re.search(r'\b(\d{1,2})[/\.-](\d{1,2})[/\.-](20\d{2})\b', text)
    if m2:
        d, mth, y = m2.group(1), m2.group(2), m2.group(3)
        try:
            dt = datetime(int(y), int(mth), int(d))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    return None

def save_stock_snapshot(items: List[Dict[str, Any]], filename: str, detected_date: Optional[str] = None) -> Dict[str, Any]:
    """Guarda un snapshot de inventario en la memoria histórica con timestamp y metadatos."""
    history_dir = get_history_dir()
    now = datetime.now()
    snapshot_id = now.strftime("%Y%m%d_%H%M%S")
    
    doc_date = detected_date or now.strftime("%Y-%m-%d")
    date_source = "document" if detected_date else "upload_time"
    
    # Calcular marcas y KPIs básicos del snapshot
    brands_count = {}
    total_units = 0
    for it in items:
        b = str(it.get("brand") or "Otras").strip()
        brands_count[b] = brands_count.get(b, 0) + 1
        stock_val = 0
        try:
            stock_val = int(it.get("stock", 0))
        except (ValueError, TypeError):
            try:
                stock_val = int(float(it.get("stock", 0)))
            except Exception:
                pass
        total_units += max(0, stock_val)

    snapshot_data = {
        "id": snapshot_id,
        "filename": filename,
        "date": doc_date,
        "date_source": date_source,
        "created_at": now.isoformat(),
        "total_references": len(items),
        "total_units": total_units,
        "brands_count": brands_count,
        "items": items
    }
    
    filepath = os.path.join(history_dir, f"snapshot_{snapshot_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2, ensure_ascii=False)
        
    return snapshot_data

def get_stock_snapshots_list() -> List[Dict[str, Any]]:
    """Devuelve la lista de snapshots de inventario registrados, ordenados del más reciente al más antiguo."""
    history_dir = get_history_dir()
    snapshots = []
    
    for fname in os.listdir(history_dir):
        if fname.startswith("snapshot_") and fname.endswith(".json"):
            fpath = os.path.join(history_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Excluir la lista completa de items para aligerar la respuesta de la lista
                    snapshots.append({
                        "id": data.get("id"),
                        "filename": data.get("filename"),
                        "date": data.get("date"),
                        "date_source": data.get("date_source"),
                        "created_at": data.get("created_at"),
                        "total_references": data.get("total_references", 0),
                        "total_units": data.get("total_units", 0),
                        "brands_summary": list(data.get("brands_count", {}).keys())[:8]
                    })
            except Exception:
                continue

    snapshots.sort(key=lambda x: (x.get("date", ""), x.get("created_at", "")), reverse=True)
    return snapshots

def load_snapshot(snapshot_id: str) -> Optional[Dict[str, Any]]:
    """Carga un snapshot completo por su ID."""
    history_dir = get_history_dir()
    filepath = os.path.join(history_dir, f"snapshot_{snapshot_id}.json")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def load_provider_tariff_items(provider_filename_or_id: str) -> List[Dict[str, Any]]:
    """Carga los artículos de una tarifa de proveedor desde data/tariffs/ o data/extractions/ enriqueciendo categoría y atributos."""
    def _enrich_tariff_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for it in raw_items:
            prod = str(it.get("product") or "")
            mod = str(it.get("model") or "")
            if not it.get("category") or it.get("category") in ["N/D", "Otros", ""]:
                cat = classify_appliance_type(prod + " " + mod, mod)
                if cat != "Otros" or not it.get("category"):
                    it["category"] = cat
            if not it.get("attributes"):
                it["attributes"] = extract_appliance_features(prod, mod)
        return raw_items

    # 1. Comprobar si es un ID de tarifa guardada en data/tariffs/
    tariff_obj = load_tariff(provider_filename_or_id)
    if tariff_obj and "items" in tariff_obj:
        return _enrich_tariff_items(tariff_obj["items"])

    # 2. Comprobar en data/tariffs/ por coincidencia de nombre
    tariffs_dir = get_tariffs_dir()
    for fname in os.listdir(tariffs_dir):
        if fname.endswith(".json") and provider_filename_or_id in fname:
            t = load_tariff(fname.replace("tariff_", "").replace(".json", ""))
            if t and "items" in t:
                return _enrich_tariff_items(t["items"])

    # 3. Fallback a data/extractions/ para compatibilidad con archivos previos
    extractions_dir = os.path.join(get_base_data_dir(), "extractions")
    target_path = os.path.join(extractions_dir, provider_filename_or_id)
    if not os.path.exists(target_path):
        for candidate in [f"{provider_filename_or_id}.xlsx", f"{provider_filename_or_id}.csv"]:
            p = os.path.join(extractions_dir, candidate)
            if os.path.exists(p):
                target_path = p
                break
                
    if not os.path.exists(target_path) or pd is None:
        return []
        
    try:
        if target_path.endswith(".xlsx") or target_path.endswith(".xls"):
            df = pd.read_excel(target_path)
        else:
            df = pd.read_csv(target_path)
            
        items = []
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            model = str(row_dict.get("model") or row_dict.get("modelo") or row_dict.get("sku") or "").strip()
            product = str(row_dict.get("product") or row_dict.get("producto") or row_dict.get("descripcion") or "").strip()
            raw_price = row_dict.get("price") or row_dict.get("precio") or row_dict.get("precio_sin_iva") or row_dict.get("PVP") or 0
            
            price_val = 0.0
            if isinstance(raw_price, (int, float)):
                price_val = float(raw_price)
            else:
                p_str = str(raw_price).replace("€", "").replace("EUR", "").strip()
                if '.' in p_str and ',' in p_str:
                    p_str = p_str.replace('.', '').replace(',', '.')
                elif ',' in p_str:
                    p_str = p_str.replace(',', '.')
                try:
                    price_val = float(re.sub(r'[^\d\.]', '', p_str))
                except Exception:
                    price_val = 0.0
                    
            if model or product:
                items.append({
                    "model": model,
                    "product": product,
                    "price": price_val,
                    "attributes": str(row_dict.get("attributes") or row_dict.get("atributos_tecnicos") or ""),
                    "raw_row": row_dict
                })
        return _enrich_tariff_items(items)
    except Exception as e:
        print(f"Error cargando tarifa {provider_filename_or_id}: {e}")
        return []

def compare_stock_vs_tariff(
    stock_items: List[Dict[str, Any]],
    tariff_items: List[Dict[str, Any]],
    brand_filter: Optional[str] = None,
    category_filter: Optional[str] = None,
    low_stock_threshold: int = 2
) -> Dict[str, Any]:
    """Cruza la tarifa de un proveedor contra el stock de almacén con filtros opcionales de marca y aparato."""
    norm_brand_filter = brand_filter.strip().upper() if brand_filter and brand_filter.strip().upper() != "TODAS" else None
    norm_cat_filter = category_filter.strip().lower() if category_filter and category_filter.strip() else None
    
    def matches_appliance(text: str) -> bool:
        if not norm_cat_filter:
            return True
        t_clean = text.lower().replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
        f_clean = norm_cat_filter.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
        return f_clean in t_clean

    # 1. Crear índices de búsqueda rápida en stock de almacén
    stock_by_sku: Dict[str, Dict[str, Any]] = {}
    stock_by_ean: Dict[str, Dict[str, Any]] = {}
    stock_by_base_model: Dict[str, Dict[str, Any]] = {}
    stock_by_desc: List[Dict[str, Any]] = []
    
    for item in stock_items:
        b = str(item.get("brand", "")).strip().upper()
        if norm_brand_filter and norm_brand_filter not in b:
            continue
        if norm_cat_filter:
            item_text = f"{item.get('category', '')} {item.get('description', '')} {item.get('sku', '')}"
            if not matches_appliance(item_text):
                continue
            
        sku_clean = normalize_sku(item.get("sku") or item.get("model") or "")
        ean_clean = normalize_sku(item.get("ean", ""))
        
        if sku_clean:
            stock_by_sku[sku_clean] = item
            base_m = extract_base_model(sku_clean)
            if base_m:
                s_col = extract_model_color(item.get("sku") or item.get("model") or "", item.get("description") or "")
                if s_col:
                    stock_by_base_model[(base_m, s_col)] = item
                if base_m not in stock_by_base_model:
                    stock_by_base_model[base_m] = item
                
        if ean_clean and ean_clean != "ND":
            for e_var in normalize_ean_variants(ean_clean):
                stock_by_ean[e_var] = item
            
        stock_by_desc.append(item)

    matched_stock_skus = set()
    
    tariff_view = [] # Vista unificada completa de la tarifa con el estado de existencias
    shortages = []   # Roturas totales (0 uds o ausentes en almacén) -> Pedir
    low_stock = []   # Stock crítico (1 a threshold uds) -> Reponer
    in_stock = []    # Stock saludable (> threshold uds) -> Cubierto
    
    total_order_cost = 0.0

    matching_stats = {
        "exact_ean": 0,
        "exact_sku": 0,
        "base_model": 0,
        "substr_variant": 0,
        "fuzzy": 0,
        "desc_pattern": 0,
        "unmatched": 0,
        "total_matched": 0,
        "match_rate_pct": 0.0
    }

    # 2. Evaluar cada producto de la tarifa del proveedor con el motor de matching jerárquico
    for t_item in tariff_items:
        model = t_item.get("model", "")
        product = t_item.get("product", "")
        price = float(t_item.get("price", 0.0))
        brand = t_item.get("brand", "")
        brand_upper = brand.strip().upper() if brand else ""
        
        # Filtro de marca en la tarifa si está especificado
        if norm_brand_filter:
            text_to_check = f"{model} {product} {brand}".upper()
            if norm_brand_filter not in text_to_check:
                continue

        # Filtro de aparato/categoría en la tarifa si está especificado
        if norm_cat_filter:
            t_text = f"{model} {product} {t_item.get('category', '')}"
            if not matches_appliance(t_text):
                continue

        norm_model = normalize_sku(model)
        base_model = extract_base_model(model)
        tariff_ean_vars = normalize_ean_variants(t_item.get("ean", ""))
        
        matched = None
        match_type = None
        match_confidence = 0.0
        match_label = "No localizado en almacén"
        matched_warehouse_sku = ""

        # Nivel 1. Match directo por código EAN (100% Confianza)
        if tariff_ean_vars:
            for e_var in tariff_ean_vars:
                if e_var in stock_by_ean:
                    matched = stock_by_ean[e_var]
                    match_type = "EAN"
                    match_confidence = 1.0
                    match_label = "Match exacto por EAN"
                    matched_warehouse_sku = matched.get("sku") or matched.get("model") or ""
                    break

        # Nivel 2. Match directo por Modelo / SKU (100% Confianza)
        if not matched and norm_model and norm_model != brand_upper:
            if norm_model in stock_by_sku:
                matched = stock_by_sku[norm_model]
                match_type = "SKU"
                match_confidence = 1.0
                match_label = "Match exacto por SKU"
                matched_warehouse_sku = matched.get("sku") or matched.get("model") or ""

        # Nivel 3. Match por Modelo Base (respetando estrictamente el color) (95% Confianza)
        if not matched and base_model and base_model != brand_upper:
            t_col = extract_model_color(model, product)
            if t_col and (base_model, t_col) in stock_by_base_model:
                matched = stock_by_base_model[(base_model, t_col)]
                match_type = "BASE"
                match_confidence = 0.95
                match_label = f"Match modelo base ({base_model} - {t_col.title()})"
                matched_warehouse_sku = matched.get("sku") or matched.get("model") or ""
            elif not t_col and base_model in stock_by_base_model:
                matched = stock_by_base_model[base_model]
                match_type = "BASE"
                match_confidence = 0.95
                match_label = f"Match modelo base ({base_model})"
                matched_warehouse_sku = matched.get("sku") or matched.get("model") or ""

        # Nivel 4. Match por variante de subcadena o prefijo (90% Confianza)
        if not matched and norm_model and len(norm_model) >= 5 and norm_model != brand_upper:
            for s_sku, s_item in stock_by_sku.items():
                if len(s_sku) >= 5 and (norm_model in s_sku or s_sku in norm_model):
                    if abs(len(norm_model) - len(s_sku)) <= 3:
                        matched = s_item
                        match_type = "SUBSTR"
                        match_confidence = 0.90
                        match_label = "Variante de modelo / sufijo"
                        matched_warehouse_sku = s_item.get("sku") or s_item.get("model") or s_sku
                        break

        # Nivel 5. Matching Difuso Inteligente (Fuzzy Levenshtein) (85%-95% Confianza)
        if not matched and norm_model and len(norm_model) >= 4 and norm_model != brand_upper:
            fuzzy_res = fuzzy_match_sku(norm_model, stock_by_sku, min_ratio=0.85)
            if fuzzy_res:
                cand_item, score, cand_sku = fuzzy_res
                matched = cand_item
                match_type = "FUZZY"
                match_confidence = score
                match_label = f"Match difuso ({int(score * 100)}%)"
                matched_warehouse_sku = cand_item.get("sku") or cand_item.get("model") or cand_sku

        # Nivel 6. Búsqueda en descripción de stock con límites de palabra (80% Confianza)
        if not matched and norm_model and len(norm_model) >= 5 and norm_model != brand_upper:
            generic_words = {"BLANCO", "NEGRO", "ACERO", "CRISTAL", "LAVADORA", "FRIGORIFICO", "HORNO", "PLACA", "CAMPANA", "INTEGRABLE", "OFERTA", "NUEVO", "COMBI"}
            if norm_model not in generic_words:
                pattern = r'(?<![A-Z0-9])' + re.escape(norm_model) + r'(?![A-Z0-9])'
                for s_item in stock_by_desc:
                    s_desc = str(s_item.get("description") or s_item.get("product") or "").upper()
                    s_desc_norm = normalize_sku(s_desc)
                    if re.search(pattern, s_desc_norm):
                        matched = s_item
                        match_type = "DESC"
                        match_confidence = 0.80
                        match_label = "Localizado en descripción"
                        matched_warehouse_sku = s_item.get("sku") or s_item.get("model") or ""
                        break

        # Verificación estricta de color: un modelo Inox NUNCA puede emparejarse con uno Blanco
        if matched and match_type != "EAN":
            t_color = extract_model_color(model, product)
            s_color = extract_model_color(matched.get("sku") or matched.get("model") or "", matched.get("description") or "")
            if t_color and s_color and t_color != s_color:
                # Conflicto de color detectado: abortar emparejamiento erróneo
                matched = None
                match_type = None
                match_confidence = 0.0
                match_label = "No localizado en almacén"
                matched_warehouse_sku = ""

        # Registrar estadísticas de cruce
        if match_type == "EAN":
            matching_stats["exact_ean"] += 1
            matching_stats["total_matched"] += 1
        elif match_type == "SKU":
            matching_stats["exact_sku"] += 1
            matching_stats["total_matched"] += 1
        elif match_type == "BASE":
            matching_stats["base_model"] += 1
            matching_stats["total_matched"] += 1
        elif match_type == "SUBSTR":
            matching_stats["substr_variant"] += 1
            matching_stats["total_matched"] += 1
        elif match_type == "FUZZY":
            matching_stats["fuzzy"] += 1
            matching_stats["total_matched"] += 1
        elif match_type == "DESC":
            matching_stats["desc_pattern"] += 1
            matching_stats["total_matched"] += 1
        else:
            matching_stats["unmatched"] += 1

        current_qty = 0
        stock_sku = model
        
        # Priorizar categorización de la tarifa, luego de stock, luego inferir
        resolved_category = (
            t_item.get("category") or 
            (matched.get("category") if matched and matched.get("category") not in ["N/D", "Otros", ""] else "") or 
            classify_appliance_type(product + " " + model, model)
        )
        resolved_attributes = (
            t_item.get("attributes") or 
            (matched.get("capacity") if matched else "") or 
            extract_appliance_features(product, model)
        )
        description = product
        
        if matched:
            matched_stock_skus.add(normalize_sku(matched.get("sku") or matched.get("model") or ""))
            try:
                current_qty = int(matched.get("stock", 0))
            except Exception:
                try:
                    current_qty = int(float(matched.get("stock", 0)))
                except Exception:
                    current_qty = 0
            description = matched.get("description") or product
            stock_sku = matched.get("sku") or model

        entry = {
            "model": model,
            "sku": stock_sku,
            "product": description,
            "category": resolved_category,
            "stock": current_qty,
            "supplier_price": price,
            "attributes": resolved_attributes,
            "matched_in_warehouse": matched is not None,
            "match_type": match_type,
            "match_confidence": match_confidence,
            "match_label": match_label,
            "matched_warehouse_sku": matched_warehouse_sku
        }

        if current_qty == 0:
            suggested_reorder = max(1, low_stock_threshold * 2)
            entry["status"] = "ROTURA"
            entry["status_label"] = "🔴 Pedir (0 uds)"
            entry["action"] = "PEDIR"
            entry["suggested_reorder"] = suggested_reorder
            entry["reorder_cost"] = round(suggested_reorder * price, 2)
            total_order_cost += entry["reorder_cost"]
            shortages.append(entry)
        elif current_qty <= low_stock_threshold:
            suggested_reorder = max(1, (low_stock_threshold * 2) - current_qty)
            entry["status"] = "BAJO"
            entry["status_label"] = f"🟡 Reponer ({current_qty} uds)"
            entry["action"] = "REPONER"
            entry["suggested_reorder"] = suggested_reorder
            entry["reorder_cost"] = round(suggested_reorder * price, 2)
            total_order_cost += entry["reorder_cost"]
            low_stock.append(entry)
        else:
            entry["status"] = "OK"
            entry["status_label"] = f"🟢 Cubierto ({current_qty} uds)"
            entry["action"] = "CUBIERTO"
            entry["suggested_reorder"] = 0
            entry["reorder_cost"] = 0.0
            in_stock.append(entry)

        tariff_view.append(entry)

    # 3. Detectar referencias del almacén que no están en la tarifa (posible descatalogado o excedente)
    surplus_items = []
    for s_item in stock_by_desc:
        sku_norm = normalize_sku(s_item.get("sku", ""))
        if sku_norm and sku_norm not in matched_stock_skus:
            surplus_items.append({
                "sku": s_item.get("sku"),
                "description": s_item.get("description"),
                "category": s_item.get("category"),
                "stock": s_item.get("stock", 0),
                "cost": s_item.get("cost", 0.0)
            })

    # Calcular porcentaje global de emparejamiento
    total_t_items = max(1, len(tariff_view))
    matching_stats["match_rate_pct"] = round((matching_stats["total_matched"] / total_t_items) * 100, 1)

    return {
        "brand": brand_filter or "Todas",
        "low_stock_threshold": low_stock_threshold,
        "kpis": {
            "total_tariff_items": len(tariff_view),
            "shortages_count": len(shortages),
            "low_stock_count": len(low_stock),
            "in_stock_count": len(in_stock),
            "surplus_count": len(surplus_items),
            "total_estimated_reorder_cost": round(total_order_cost, 2),
            "total_items_to_order": len(shortages) + len(low_stock)
        },
        "matching_stats": matching_stats,
        "tariff_view": tariff_view,
        "shortages": shortages,
        "low_stock": low_stock,
        "in_stock": in_stock,
        "surplus": surplus_items[:50]
    }

def calculate_stock_delta(
    snapshot_old: Dict[str, Any],
    snapshot_new: Dict[str, Any],
    brand_filter: Optional[str] = None
) -> Dict[str, Any]:
    """Calcula la variación de inventario entre dos snapshots, días transcurridos y ventas estimadas."""
    date_str_old = snapshot_old.get("date") or "2026-01-01"
    date_str_new = snapshot_new.get("date") or "2026-01-01"
    
    try:
        dt_old = datetime.strptime(date_str_old, "%Y-%m-%d")
        dt_new = datetime.strptime(date_str_new, "%Y-%m-%d")
        days_diff = max(1, (dt_new - dt_old).days)
    except Exception:
        days_diff = 1

    norm_brand = brand_filter.strip().upper() if brand_filter and brand_filter.strip().upper() != "TODAS" else None
    
    old_items_map: Dict[str, Dict[str, Any]] = {}
    for it in snapshot_old.get("items", []):
        b = str(it.get("brand", "")).strip().upper()
        if norm_brand and norm_brand not in b:
            continue
        s_norm = normalize_sku(it.get("sku", ""))
        if s_norm:
            old_items_map[s_norm] = it

    new_items_map: Dict[str, Dict[str, Any]] = {}
    for it in snapshot_new.get("items", []):
        b = str(it.get("brand", "")).strip().upper()
        if norm_brand and norm_brand not in b:
            continue
        s_norm = normalize_sku(it.get("sku", ""))
        if s_norm:
            new_items_map[s_norm] = it

    all_skus = set(old_items_map.keys()).union(set(new_items_map.keys()))
    
    sold_items = []
    restocked_items = []
    unchanged_items = []
    total_units_sold = 0

    for sku_norm in all_skus:
        old_item = old_items_map.get(sku_norm)
        new_item = new_items_map.get(sku_norm)
        
        stock_old = int(old_item.get("stock", 0)) if old_item else 0
        stock_new = int(new_item.get("stock", 0)) if new_item else 0
        
        sku_display = (new_item or old_item).get("sku", sku_norm)
        desc_display = (new_item or old_item).get("description", "")
        brand_display = (new_item or old_item).get("brand", "")
        cost_display = (new_item or old_item).get("cost", 0.0)
        
        delta = stock_old - stock_new  # Positivo indica unidades consumidas/vendidas
        
        item_row = {
            "sku": sku_display,
            "brand": brand_display,
            "description": desc_display,
            "cost": cost_display,
            "stock_old": stock_old,
            "stock_new": stock_new,
            "delta_units": delta
        }
        
        if delta > 0:
            units_sold = delta
            total_units_sold += units_sold
            rate_per_day = round(units_sold / days_diff, 2)
            days_to_stockout = round(stock_new / rate_per_day, 1) if rate_per_day > 0 and stock_new > 0 else 0
            
            item_row["units_sold"] = units_sold
            item_row["sales_rate_per_day"] = rate_per_day
            item_row["days_to_stockout"] = days_to_stockout
            item_row["is_critical_burn"] = (days_to_stockout > 0 and days_to_stockout <= 5) or (stock_new == 0)
            sold_items.append(item_row)
        elif delta < 0:
            item_row["units_received"] = abs(delta)
            restocked_items.append(item_row)
        else:
            unchanged_items.append(item_row)

    # Ordenar productos más vendidos por unidades
    sold_items.sort(key=lambda x: x.get("units_sold", 0), reverse=True)

    return {
        "period": {
            "date_old": date_str_old,
            "date_new": date_str_new,
            "days_elapsed": days_diff
        },
        "brand": brand_filter or "Todas",
        "kpis": {
            "total_units_sold": total_units_sold,
            "products_with_sales": len(sold_items),
            "restocked_products": len(restocked_items),
            "unchanged_products": len(unchanged_items),
            "average_sales_per_day": round(total_units_sold / days_diff, 2)
        },
        "top_sold": sold_items[:25],
        "all_sold": sold_items,
        "restocked": restocked_items,
        "critical_alerts": [it for it in sold_items if it.get("is_critical_burn")]
    }

def generate_gemini_sales_report(
    delta_result: Dict[str, Any],
    shortages_result: Dict[str, Any],
    api_key: str,
    custom_model: str = "gemini-3.6-flash"
) -> str:
    """Invoca la API de Gemini para redactar un informe ejecutivo comercial y propuesta de compra."""
    if not api_key:
        return "⚠️ No se ha configurado la API Key de Gemini en el sistema."

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception as e:
        return f"⚠️ Error al inicializar el cliente de Gemini: {str(e)}"

    period = delta_result.get("period", {})
    brand = delta_result.get("brand", "Todas")
    kpis_sales = delta_result.get("kpis", {})
    top_sold = delta_result.get("top_sold", [])[:10]
    critical_alerts = delta_result.get("critical_alerts", [])[:8]
    
    kpis_shortages = shortages_result.get("kpis", {})
    shortages_sample = shortages_result.get("shortages", [])[:10]
    low_stock_sample = shortages_result.get("low_stock", [])[:8]

    prompt = f"""
Actúa como un Director de Compras y Estrategia Comercial de alto nivel para una cadena de tiendas de electrodomésticos y retail.
Tu objetivo es analizar los datos de existencias y redactar un INFORME EJECUTIVO DE ROTURAS, VENTAS Y PROPUESTA DE COMPRA claro, profesional y persuasivo en formato Markdown.

DATOS DEL PERIODO:
- Marca analizada: {brand}
- Fechas del análisis: Del {period.get('date_old', 'N/D')} al {period.get('date_new', 'N/D')} (Han transcurrido {period.get('days_elapsed', 1)} días).
- Ventas estimadas del periodo: {kpis_sales.get('total_units_sold', 0)} unidades totales vendidas ({kpis_sales.get('average_sales_per_day', 0)} uds/día).
- Productos con rotación/ventas: {kpis_sales.get('products_with_sales', 0)} referencias.

TOP PRODUCTOS MÁS VENDIDOS:
{json.dumps(top_sold, ensure_ascii=False, indent=2)}

ALERTAS CRÍTICAS DE ROTURA INMINENTE (Se agotarán en pocos días o ya están a 0):
{json.dumps(critical_alerts, ensure_ascii=False, indent=2)}

ESTADO FRENTE A LA TARIFA DEL PROVEEDOR:
- Total referencias evaluadas en tarifa: {kpis_shortages.get('total_tariff_items', 0)}
- Faltas totales / rotura (0 unidades): {kpis_shortages.get('shortages_count', 0)}
- Stock bajo / crítico: {kpis_shortages.get('low_stock_count', 0)}
- Presupuesto estimado de reposición sugerida: {kpis_shortages.get('total_estimated_reorder_cost', 0)} €

MUESTRA DE PRODUCTOS EN FALTA:
{json.dumps(shortages_sample, ensure_ascii=False, indent=2)}

MUESTRA DE STOCK BAJO:
{json.dumps(low_stock_sample, ensure_ascii=False, indent=2)}

ESTRUCTURA OBLIGATORIA DEL INFORME:
1. 📊 **Diagnóstico Ejecutivo**: Resumen conciso de ventas y días transcurridos.
2. 🔥 **Rendimiento de Ventas (Top Rotación)**: Menciona los modelos estrella y su velocidad de venta diaria.
3. ⚠️ **Alertas de Desabastecimiento Inminente**: Indica claramente qué productos van a romper stock y en cuántos días si no se pide hoy.
4. 🛒 **Propuesta Concreta de Pedido al Proveedor**: Lista priorizada de modelos a pedir, unidades recomendadas e inversión estimada.
5. 💡 **Recomendación Estratégica**: Consejo comercial final para el responsable de tienda.

Usa un tono riguroso, directo, con viñetas elegantes y cifras destacadas en negrita.
"""

    candidate_models = [
        custom_model,
        "gemini-3.6-flash",
        "gemini-3.8-flash",
        "gemini-flash-latest",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite"
    ]
    
    seen = set()
    models_to_try = []
    deprecated = {"gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"}
    for m in candidate_models:
        if m and m not in seen and m not in deprecated:
            seen.add(m)
            models_to_try.append(m)

    last_error = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            if response and response.text:
                return response.text
        except Exception as e:
            last_error = e
            continue

    return f"Error al generar informe con Gemini: {str(last_error)}"

def export_audit_to_excel(shortages_result: Dict[str, Any], delta_result: Optional[Dict[str, Any]] = None) -> Workbook:
    """Genera un archivo Excel profesional con las hojas de Faltas, Stock Bajo y Ventas."""
    if Workbook is None:
        raise RuntimeError("openpyxl no está disponible en el entorno.")

    wb = Workbook()
    
    # ── Paleta de Colores ──
    C_HEADER = "1E293B"       # Slate oscuro
    C_SHORTAGE = "FEE2E2"     # Rojo suave
    C_SHORTAGE_TXT = "991B1B"
    C_LOW = "FEF3C7"          # Amarillo suave
    C_LOW_TXT = "92400E"
    C_OK = "DCFCE7"           # Verde suave
    C_OK_TXT = "166534"
    C_WHITE = "FFFFFF"
    C_BORDER = "E2E8F0"
    
    thin_border = Border(
        left=Side(style='thin', color=C_BORDER),
        right=Side(style='thin', color=C_BORDER),
        top=Side(style='thin', color=C_BORDER),
        bottom=Side(style='thin', color=C_BORDER)
    )

    # ─────────────────────────────────────────────────────────────────────────
    # HOJA 1: PEDIDO SUGERIDO Y FALTAS
    # ─────────────────────────────────────────────────────────────────────────
    ws1 = wb.active
    ws1.title = "Faltas y Pedido"
    
    headers1 = ["Modelo Tarifa", "SKU Almacén", "Tipo Cruce", "Descripción", "Categoría", "Stock Actual", "Pedido Sugerido", "Coste Tarifa (€)", "Total Línea (€)"]
    ws1.append(["AUDITORÍA DE FALTAS Y PROPUESTA DE PEDIDO"])
    ws1.merge_cells("A1:I1")
    title_cell = ws1["A1"]
    title_cell.font = Font(size=14, bold=True, color=C_WHITE)
    title_cell.fill = PatternFill(start_color="DC2626", end_color="DC2626", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[1].height = 32

    ws1.append(headers1)
    ws1.row_dimensions[2].height = 24
    for col_idx in range(1, len(headers1) + 1):
        c = ws1.cell(row=2, column=col_idx)
        c.font = Font(bold=True, color=C_WHITE)
        c.fill = PatternFill(start_color=C_HEADER, end_color=C_HEADER, fill_type="solid")
        c.alignment = Alignment(horizontal="center", vertical="center")

    row_num = 3
    for it in shortages_result.get("shortages", []):
        ws1.append([
            it.get("model", ""),
            it.get("matched_warehouse_sku") or it.get("sku") or "N/D",
            it.get("match_label", "No localizado"),
            it.get("product", ""),
            it.get("category", ""),
            it.get("stock", 0),
            it.get("suggested_reorder", 1),
            it.get("supplier_price", 0.0),
            it.get("reorder_cost", 0.0)
        ])
        ws1.row_dimensions[row_num].height = 20
        for c_idx in range(1, 10):
            cell = ws1.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            if c_idx == 6: # Stock actual
                cell.fill = PatternFill(start_color=C_SHORTAGE, end_color=C_SHORTAGE, fill_type="solid")
                cell.font = Font(color=C_SHORTAGE_TXT, bold=True)
                cell.alignment = Alignment(horizontal="center")
            elif c_idx in [7, 8, 9]:
                cell.alignment = Alignment(horizontal="right")
                if c_idx in [8, 9]:
                    cell.number_format = '#,##0.00 €'
        row_num += 1

    # ─────────────────────────────────────────────────────────────────────────
    # HOJA 2: STOCK BAJO (ALERTA)
    # ─────────────────────────────────────────────────────────────────────────
    ws2 = wb.create_sheet(title="Stock Bajo")
    ws2.append(["ALERTAS DE STOCK BAJO (REPOSICIÓN INMINENTE)"])
    ws2.merge_cells("A1:I1")
    t2 = ws2["A1"]
    t2.font = Font(size=14, bold=True, color=C_WHITE)
    t2.fill = PatternFill(start_color="D97706", end_color="D97706", fill_type="solid")
    t2.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 32

    ws2.append(headers1)
    ws2.row_dimensions[2].height = 24
    for col_idx in range(1, len(headers1) + 1):
        c = ws2.cell(row=2, column=col_idx)
        c.font = Font(bold=True, color=C_WHITE)
        c.fill = PatternFill(start_color=C_HEADER, end_color=C_HEADER, fill_type="solid")
        c.alignment = Alignment(horizontal="center", vertical="center")

    row_num2 = 3
    for it in shortages_result.get("low_stock", []):
        ws2.append([
            it.get("model", ""),
            it.get("matched_warehouse_sku") or it.get("sku") or "N/D",
            it.get("match_label", "No localizado"),
            it.get("product", ""),
            it.get("category", ""),
            it.get("stock", 0),
            it.get("suggested_reorder", 1),
            it.get("supplier_price", 0.0),
            it.get("reorder_cost", 0.0)
        ])
        ws2.row_dimensions[row_num2].height = 20
        for c_idx in range(1, 10):
            cell = ws2.cell(row=row_num2, column=c_idx)
            cell.border = thin_border
            if c_idx == 6:
                cell.fill = PatternFill(start_color=C_LOW, end_color=C_LOW, fill_type="solid")
                cell.font = Font(color=C_LOW_TXT, bold=True)
                cell.alignment = Alignment(horizontal="center")
            elif c_idx in [7, 8, 9]:
                cell.alignment = Alignment(horizontal="right")
                if c_idx in [8, 9]:
                    cell.number_format = '#,##0.00 €'
        row_num2 += 1

    # ─────────────────────────────────────────────────────────────────────────
    # HOJA 3: ANÁLISIS DE VENTAS Y DELTA (SI ESTÁ DISPONIBLE)
    # ─────────────────────────────────────────────────────────────────────────
    if delta_result:
        ws3 = wb.create_sheet(title="Evolución y Ventas")
        headers3 = ["Modelo / SKU", "Marca", "Descripción", "Stock Anterior", "Stock Actual", "Uds Vendidas", "Ritmo (Uds/Día)", "Días Hasta Rotura"]
        period = delta_result.get("period", {})
        ws3.append([f"ANÁLISIS DE VENTAS ({period.get('date_old')} a {period.get('date_new')} - {period.get('days_elapsed')} días)"])
        ws3.merge_cells("A1:H1")
        t3 = ws3["A1"]
        t3.font = Font(size=14, bold=True, color=C_WHITE)
        t3.fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
        t3.alignment = Alignment(horizontal="center", vertical="center")
        ws3.row_dimensions[1].height = 32

        ws3.append(headers3)
        ws3.row_dimensions[2].height = 24
        for col_idx in range(1, len(headers3) + 1):
            c = ws3.cell(row=2, column=col_idx)
            c.font = Font(bold=True, color=C_WHITE)
            c.fill = PatternFill(start_color=C_HEADER, end_color=C_HEADER, fill_type="solid")
            c.alignment = Alignment(horizontal="center", vertical="center")

        row_num3 = 3
        for it in delta_result.get("all_sold", []):
            ws3.append([
                it.get("sku", ""),
                it.get("brand", ""),
                it.get("description", ""),
                it.get("stock_old", 0),
                it.get("stock_new", 0),
                it.get("units_sold", 0),
                it.get("sales_rate_per_day", 0.0),
                it.get("days_to_stockout", 0)
            ])
            ws3.row_dimensions[row_num3].height = 20
            for c_idx in range(1, 9):
                cell = ws3.cell(row=row_num3, column=c_idx)
                cell.border = thin_border
                if c_idx in [4, 5, 6, 7, 8]:
                    cell.alignment = Alignment(horizontal="right")
                if c_idx == 6: # Unidades vendidas
                    cell.font = Font(bold=True, color="1E3A8A")
                if c_idx == 8 and it.get("is_critical_burn"):
                    cell.fill = PatternFill(start_color=C_SHORTAGE, end_color=C_SHORTAGE, fill_type="solid")
                    cell.font = Font(color=C_SHORTAGE_TXT, bold=True)
            row_num3 += 1

    # Auto-ajustar ancho de columnas en todas las hojas
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    return wb
