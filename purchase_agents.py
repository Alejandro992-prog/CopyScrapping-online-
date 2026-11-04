import os
import io
import re
import uuid
import json
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import stock_analyzer

logger = logging.getLogger("garde_app.purchase_agents")

# Almacenamiento en memoria de sesiones de trabajo de los Agentes (con limpieza automática FIFO)
_TARIFF_SESSIONS: Dict[str, Dict[str, Any]] = {}
_STOCK_SESSIONS: Dict[str, Dict[str, Any]] = {}
_LAST_CROSS_RESULT: Dict[str, Any] = {}
_MAX_SESSIONS = 15


def _now_time() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _trim_sessions(store: Dict[str, Any]):
    while len(store) > _MAX_SESSIONS:
        oldest_key = next(iter(store))
        store.pop(oldest_key, None)


def is_valid_sku(val: Any) -> bool:
    """Verifica si un string tiene características de código de modelo o SKU principal."""
    if val is None:
        return False
    s = str(val).strip()
    if len(s) < 2 or len(s) > 40:
        return False
    if " " in s and len(s.split()) > 2:
        return False
    if not re.search(r'\d', s):
        return False
    if re.match(r'^\d{1,4}[-/\.]\d{1,2}[-/\.]\d{2,4}$', s):
        return False
    return True


def clean_price_value(val: Any) -> Optional[float]:
    """Convierte cualquier representación de precio (europea o anglosajona) a float."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if pd.isna(val):
            return None
        v = float(val)
        return round(v, 2) if v > 0 else None

    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "n/d", "n/a", "-", "consultar", "s/c"):
        return None

    # Limpiar símbolos de moneda y espacios
    s = re.sub(r'[€$£\s\xa0EURUSD]', '', s, flags=re.IGNORECASE).strip()
    s = s.strip('()[]*+')
    if not s:
        return None

    m = re.search(r'(\d[\d.,]*)', s)
    if not m:
        return None
    num_str = m.group(1)

    if ',' in num_str and '.' in num_str:
        if num_str.rfind(',') > num_str.rfind('.'):
            num_str = num_str.replace('.', '').replace(',', '.')
        else:
            num_str = num_str.replace(',', '')
    elif ',' in num_str:
        parts = num_str.split(',')
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1:
            # Ej: 1,250 -> 1250 si parece separador de miles, pero en España suele ser decimal
            num_str = num_str.replace(',', '.')
        else:
            num_str = num_str.replace(',', '.')
    elif '.' in num_str:
        parts = num_str.split('.')
        if len(parts) > 2:
            num_str = num_str.replace('.', '')
        elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) >= 1:
            # Ej: 1.250 en formato europeo -> 1250
            try:
                if float(parts[0]) < 20:
                    num_str = num_str.replace('.', '')
            except Exception:
                pass

    try:
        res = float(num_str)
        return round(res, 2) if 0.01 <= res <= 99999.0 else None
    except ValueError:
        return None


def _get_sheet_names(file_bytes: bytes, filename: str) -> List[str]:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".csv":
        return ["Datos CSV"]
    try:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        return list(xls.sheet_names)
    except Exception:
        return ["Hoja 1"]


def _load_sheet_dataframe(file_bytes: bytes, filename: str, sheet_name: Optional[str] = None) -> pd.DataFrame:
    ext = os.path.splitext(filename.lower())[1]
    if ext == ".csv":
        for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1252"]:
            for sep in [";", ",", "\t", "|"]:
                try:
                    candidate = pd.read_csv(
                        io.BytesIO(file_bytes),
                        encoding=enc,
                        sep=sep,
                        header=None,
                        dtype=str,
                        on_bad_lines="skip"
                    )
                    if candidate is not None and candidate.shape[1] >= 2 and len(candidate) >= 1:
                        candidate = candidate.dropna(how="all").reset_index(drop=True)
                        candidate = candidate.dropna(axis=1, how="all")
                        candidate.columns = list(range(candidate.shape[1]))
                        return candidate
                except Exception:
                    continue
        candidate = pd.read_csv(io.BytesIO(file_bytes), header=None, dtype=str, on_bad_lines="skip")
        candidate = candidate.dropna(how="all").reset_index(drop=True)
        candidate = candidate.dropna(axis=1, how="all")
        candidate.columns = list(range(candidate.shape[1]))
        return candidate

    # Excel (.xlsx / .xls): leer ÚNICAMENTE la hoja requerida
    target = sheet_name or 0
    df_sheet = pd.read_excel(io.BytesIO(file_bytes), sheet_name=target, header=None, dtype=str)
    df_sheet = df_sheet.dropna(how="all").reset_index(drop=True)
    df_sheet = df_sheet.dropna(axis=1, how="all")
    df_sheet.columns = list(range(df_sheet.shape[1]))
    return df_sheet


def _detect_header_and_columns(df: pd.DataFrame, forced_header_row: Optional[int] = None) -> Dict[str, Any]:
    """
    El Agente de Tarifas inspecciona las primeras filas de la hoja para detectar:
    - Qué fila actúa como cabecera de la tabla.
    - Qué rol probable tiene cada columna (model, price, description, brand, other).
    """
    if df is None or df.empty:
        return {
            "header_row": 0,
            "columns": [],
            "suggested_mapping": {"model_col": 0, "price_col": 1, "desc_col": -1, "brand_col": -1}
        }

    max_scan = min(25, len(df))
    best_row = 0
    best_score = -1

    model_keywords = ["modelo", "model", "ref", "referencia", "codigo", "código", "sku", "cod.", "artículo", "articulo", "ean"]
    price_keywords = ["precio", "pvp", "neto", "coste", "costo", "tarifa", "importe", "eur", "€", "sin iva", "con iva", "p.v.p", "pca", "pr."]
    desc_keywords = ["descripcion", "descripción", "producto", "detalle", "concepto", "denominacion", "denominación", "aparato", "nombre", "caracteristicas"]
    brand_keywords = ["marca", "brand", "fabricante"]

    if forced_header_row is not None and 0 <= forced_header_row < len(df):
        best_row = forced_header_row
    else:
        for r_idx in range(max_scan):
            row_vals = [str(v).strip().lower() for v in df.iloc[r_idx].values if pd.notna(v) and str(v).strip() != ""]
            if len(row_vals) < 2:
                continue
            score = 0
            for cell in row_vals:
                if any(k in cell for k in model_keywords):
                    score += 5
                if any(k in cell for k in price_keywords):
                    score += 5
                if any(k in cell for k in desc_keywords):
                    score += 4
                if any(k in cell for k in brand_keywords):
                    score += 3
                # Penalizar si la celda parece un número puro o precio de datos
                if re.match(r'^\d+([.,]\d+)?$', cell):
                    score -= 1
            if score > best_score:
                best_score = score
                best_row = r_idx

    # Construir nombres de columna a partir de best_row
    num_cols = df.shape[1]
    raw_headers = df.iloc[best_row].values if best_row < len(df) else []
    data_df = df.iloc[best_row + 1:].reset_index(drop=True) if best_row + 1 < len(df) else df.copy()

    columns_info = []
    model_candidates: List[Tuple[int, int]] = []
    price_candidates: List[Tuple[int, int]] = []
    desc_candidates: List[Tuple[int, int]] = []
    brand_candidates: List[Tuple[int, int]] = []

    for c_idx in range(num_cols):
        raw_h = str(raw_headers[c_idx]).strip() if c_idx < len(raw_headers) and pd.notna(raw_headers[c_idx]) else ""
        if not raw_h or raw_h.lower() == "nan":
            col_name = f"Columna {get_column_letter(c_idx + 1)}"
        else:
            col_name = raw_h

        # Muestreo ultrarrápido sobre las primeras 60 filas (evita procesar decenas de miles de filas innecesariamente)
        sample_slice = data_df.iloc[:60, c_idx].dropna().astype(str).str.strip()
        col_series = sample_slice[~sample_slice.str.lower().isin(["", "nan", "none", "null"])]
        sample_values = col_series.head(4).tolist()
        sample_40 = col_series.head(25).tolist()
        n_samples = len(sample_40)

        price_hits = 0
        sku_hits = 0
        desc_hits = 0

        for val in sample_40:
            p_val = clean_price_value(val)
            # Evitar confundir EANs (8-13 dígitos enteros) con precios
            digits_only = re.sub(r'\D', '', val)
            is_ean = len(digits_only) >= 8 and (',' not in val and '.' not in val)
            if p_val is not None and not is_ean and 5.0 <= p_val <= 15000.0:
                price_hits += 1
            if is_valid_sku(val):
                sku_hits += 1
            if len(val) >= 15 and " " in val:
                desc_hits += 1

        h_lower = col_name.lower()
        m_score = 0
        p_score = 0
        d_score = 0
        b_score = 0

        if any(k in h_lower for k in model_keywords):
            m_score += 50
        if any(k in h_lower for k in price_keywords):
            p_score += 50
        if any(k in h_lower for k in desc_keywords):
            d_score += 50
        if any(k in h_lower for k in brand_keywords):
            b_score += 50

        if n_samples > 0:
            m_score += int((sku_hits / n_samples) * 45)
            p_score += int((price_hits / n_samples) * 45)
            d_score += int((desc_hits / n_samples) * 45)

        inferred_role = "other"
        max_role_score = max(m_score, p_score, d_score, b_score)
        if max_role_score >= 25:
            if p_score == max_role_score:
                inferred_role = "price"
            elif m_score == max_role_score:
                inferred_role = "model"
            elif d_score == max_role_score:
                inferred_role = "description"
            elif b_score == max_role_score:
                inferred_role = "brand"

        model_candidates.append((c_idx, m_score))
        price_candidates.append((c_idx, p_score))
        desc_candidates.append((c_idx, d_score))
        brand_candidates.append((c_idx, b_score))

        columns_info.append({
            "index": c_idx,
            "letter": get_column_letter(c_idx + 1),
            "name": col_name,
            "sample_values": sample_values[:4],
            "inferred_role": inferred_role,
            "scores": {"model": m_score, "price": p_score, "description": d_score}
        })

    model_candidates.sort(key=lambda x: x[1], reverse=True)
    price_candidates.sort(key=lambda x: x[1], reverse=True)
    desc_candidates.sort(key=lambda x: x[1], reverse=True)
    brand_candidates.sort(key=lambda x: x[1], reverse=True)

    suggested_model = model_candidates[0][0] if model_candidates else 0
    # Asegurar que price_col no sea la misma columna que model_col
    suggested_price = next((c for c, _ in price_candidates if c != suggested_model), (1 if num_cols > 1 else 0))
    suggested_desc = next(
        (c for c, s in desc_candidates if c not in (suggested_model, suggested_price) and s >= 15),
        -1
    )
    suggested_brand = next(
        (c for c, s in brand_candidates if c not in (suggested_model, suggested_price, suggested_desc) and s >= 25),
        -1
    )

    return {
        "header_row": best_row,
        "columns": columns_info,
        "suggested_mapping": {
            "model_col": suggested_model,
            "price_col": suggested_price,
            "desc_col": suggested_desc,
            "brand_col": suggested_brand
        }
    }


def create_tariff_preview_session(
    file_bytes: bytes,
    filename: str,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    existing_session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Módulo 1 (Agente de Tarifas):
    Carga o reutiliza el archivo Excel/CSV, genera la vista previa tabular y propone
    las columnas para que el usuario haga clic en la columna de Precio (y Modelo/Descripción).
    """
    if existing_session_id and existing_session_id in _TARIFF_SESSIONS:
        sess = _TARIFF_SESSIONS[existing_session_id]
        if not file_bytes and "file_bytes" in sess:
            file_bytes = sess["file_bytes"]
            filename = sess["filename"]
        sheet_names = sess.get("sheet_names") or _get_sheet_names(file_bytes, filename)
        session_id = existing_session_id
    else:
        sheet_names = _get_sheet_names(file_bytes, filename)
        if not sheet_names:
            raise ValueError("No se pudieron detectar hojas de datos en el archivo subido.")
        session_id = str(uuid.uuid4())[:12]

    # Elegir hoja activa (si no se especifica, elegir la primera o la indicada)
    active_sheet = sheet_name if (sheet_name and sheet_name in sheet_names) else sheet_names[0]
    df = _load_sheet_dataframe(file_bytes, filename, active_sheet)

    detection = _detect_header_and_columns(df, forced_header_row=header_row)
    h_row = detection["header_row"]
    columns = detection["columns"]
    mapping = detection["suggested_mapping"]

    # Construir filas de vista previa (hasta 25 filas después de la cabecera)
    data_df = df.iloc[h_row + 1:].reset_index(drop=True) if h_row + 1 < len(df) else df.copy()
    preview_rows = []
    for _, row in data_df.head(25).iterrows():
        row_cells = []
        for c_idx in range(df.shape[1]):
            val = row.iloc[c_idx] if c_idx < len(row) else ""
            if pd.isna(val) or str(val).strip().lower() in ("nan", "none"):
                row_cells.append("")
            else:
                row_cells.append(str(val).strip())
        if any(cell != "" for cell in row_cells):
            preview_rows.append(row_cells)

    _TARIFF_SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": filename,
        "file_bytes": file_bytes,
        "sheet_names": sheet_names,
        "active_sheet": active_sheet,
        "current_df": df,
        "header_row": h_row,
        "columns": columns,
        "mapping": mapping,
        "extracted_items": [],
        "created_at": _now_time()
    }
    _trim_sessions(_TARIFF_SESSIONS)

    model_col_name = columns[mapping["model_col"]]["name"] if 0 <= mapping["model_col"] < len(columns) else "N/D"
    price_col_name = columns[mapping["price_col"]]["name"] if 0 <= mapping["price_col"] < len(columns) else "N/D"

    agent_messages = [
        {
            "agent": "tariff",
            "agent_name": "Agente de Tarifas (Proveedor)",
            "badge": "Módulo 1 · Lectura Excel/CSV",
            "time": _now_time(),
            "text": (
                f"He analizado el archivo **{filename}** (Hoja: `{active_sheet}`, "
                f"{len(data_df)} filas y {len(columns)} columnas detectadas; cabecera en fila #{h_row + 1})."
            )
        },
        {
            "agent": "tariff",
            "agent_name": "Agente de Tarifas (Proveedor)",
            "badge": "Selección de Columnas",
            "time": _now_time(),
            "text": (
                f"He preseleccionado **{model_col_name}** como `Referencia/Modelo` y **{price_col_name}** como `Precio`. "
                f"Haz clic en cualquier cabecera de la tabla inferior si deseas cambiar la **Columna de Precio** antes de confirmar."
            )
        }
    ]

    return {
        "status": "success",
        "session_id": session_id,
        "filename": filename,
        "sheet_names": sheet_names,
        "active_sheet": active_sheet,
        "header_row": h_row,
        "total_rows": len(data_df),
        "columns": columns,
        "suggested_mapping": mapping,
        "preview_rows": preview_rows,
        "agent_messages": agent_messages
    }


def extract_tariff_with_mapping(
    session_id: str,
    model_col: int,
    price_col: int,
    desc_col: Optional[int] = -1,
    brand_col: Optional[int] = -1,
    sheet_name: Optional[str] = None,
    header_row: Optional[int] = None,
    provider_name: str = ""
) -> Dict[str, Any]:
    """
    Extrae todos los productos de la tarifa aplicando explícitamente las columnas
    seleccionadas por el usuario (Precio, Modelo y Descripción).
    """
    if session_id not in _TARIFF_SESSIONS:
        raise ValueError("La sesión de tarifa ha expirado o no existe. Por favor vuelve a subir el archivo.")

    sess = _TARIFF_SESSIONS[session_id]
    active_sheet = sheet_name if (sheet_name and sheet_name in sess.get("sheet_names", [])) else sess.get("active_sheet")
    if "current_df" in sess and sess.get("active_sheet") == active_sheet:
        df = sess["current_df"]
    else:
        df = _load_sheet_dataframe(sess["file_bytes"], sess["filename"], active_sheet)
        sess["current_df"] = df
        sess["active_sheet"] = active_sheet
    h_row = header_row if header_row is not None else sess["header_row"]

    data_df = df.iloc[h_row + 1:].reset_index(drop=True) if h_row + 1 < len(df) else df.copy()
    num_cols = df.shape[1]

    if not (0 <= model_col < num_cols):
        raise ValueError("El índice de la columna de Modelo/Referencia no es válido.")
    if not (0 <= price_col < num_cols):
        raise ValueError("El índice de la columna de Precio no es válido.")

    extracted_items: Dict[str, Dict[str, Any]] = {}
    skipped_rows = 0

    for r_idx, row in data_df.iterrows():
        raw_model = str(row.iloc[model_col]).strip() if model_col < len(row) and pd.notna(row.iloc[model_col]) else ""
        if not raw_model or raw_model.lower() in ("nan", "none", "null", "modelo", "referencia", "codigo", "código", "sku"):
            skipped_rows += 1
            continue

        # Limpiar saltos de línea dentro de la celda de modelo
        raw_model = re.split(r'[\r\n]+', raw_model)[0].strip()
        if len(raw_model) < 2 or not any(ch.isdigit() for ch in raw_model):
            # En tarifas reales los modelos/SKUs tienen al menos un dígito o código alfanumérico
            if not is_valid_sku(raw_model):
                skipped_rows += 1
                continue

        raw_price_cell = row.iloc[price_col] if price_col < len(row) else None
        price_val = clean_price_value(raw_price_cell)
        if price_val is None or price_val <= 0:
            skipped_rows += 1
            continue

        raw_desc = ""
        if desc_col is not None and 0 <= desc_col < num_cols and desc_col < len(row) and pd.notna(row.iloc[desc_col]):
            raw_desc = str(row.iloc[desc_col]).strip()
            if raw_desc.lower() in ("nan", "none", "null"):
                raw_desc = ""

        raw_brand = ""
        if brand_col is not None and 0 <= brand_col < num_cols and brand_col < len(row) and pd.notna(row.iloc[brand_col]):
            raw_brand = str(row.iloc[brand_col]).strip()
            if raw_brand.lower() in ("nan", "none", "null"):
                raw_brand = ""

        if not raw_brand:
            extracted_brand = ""
            if hasattr(stock_analyzer, "extract_brand_from_text"):
                try:
                    extracted_brand = stock_analyzer.extract_brand_from_text(f"{raw_model} {raw_desc}")
                except Exception:
                    extracted_brand = ""
            raw_brand = provider_name.strip() or extracted_brand

        category = stock_analyzer.classify_appliance_type(f"{raw_desc} {raw_model}", raw_model)
        norm_key = stock_analyzer.normalize_sku(raw_model)
        if not norm_key:
            skipped_rows += 1
            continue

        extracted_items[norm_key] = {
            "model": raw_model,
            "normalized_model": norm_key,
            "description": raw_desc or f"Artículo {raw_model}",
            "brand": raw_brand or "General",
            "category": category,
            "price": round(price_val, 2),
            "raw_price": str(raw_price_cell).strip() if pd.notna(raw_price_cell) else f"{price_val:.2f}"
        }

    items_list = list(extracted_items.values())
    sess["active_sheet"] = active_sheet
    sess["header_row"] = h_row
    sess["mapping"] = {
        "model_col": model_col,
        "price_col": price_col,
        "desc_col": desc_col if desc_col is not None else -1,
        "brand_col": brand_col if brand_col is not None else -1
    }
    sess["extracted_items"] = items_list
    sess["provider_name"] = provider_name.strip() or os.path.splitext(sess["filename"])[0]

    columns = sess["columns"]
    model_col_name = columns[model_col]["name"] if 0 <= model_col < len(columns) else f"Col {model_col + 1}"
    price_col_name = columns[price_col]["name"] if 0 <= price_col < len(columns) else f"Col {price_col + 1}"
    desc_col_name = columns[desc_col]["name"] if (desc_col is not None and 0 <= desc_col < len(columns)) else "No asignada"

    prices = [it["price"] for it in items_list if it["price"] > 0]
    min_p = min(prices) if prices else 0.0
    max_p = max(prices) if prices else 0.0
    avg_p = round(sum(prices) / len(prices), 2) if prices else 0.0

    agent_messages = [
        {
            "agent": "tariff",
            "agent_name": "Agente de Tarifas (Proveedor)",
            "badge": "Extracción Confirmada",
            "time": _now_time(),
            "text": (
                f"Mapeo confirmado por el usuario: Modelo = **{model_col_name}**, "
                f"Precio = **{price_col_name}**, Descripción = **{desc_col_name}**. "
                f"He extraído **{len(items_list)} referencias únicas** con precio válido "
                f"(rango: {min_p:.2f} € – {max_p:.2f} €, media: {avg_p:.2f} €)."
            )
        }
    ]

    return {
        "status": "success",
        "session_id": session_id,
        "items_count": len(items_list),
        "skipped_rows": skipped_rows,
        "stats": {
            "min_price": min_p,
            "max_price": max_p,
            "avg_price": avg_p,
            "model_col_name": model_col_name,
            "price_col_name": price_col_name,
            "desc_col_name": desc_col_name
        },
        "items_preview": items_list[:50],
        "agent_messages": agent_messages
    }


def create_stock_pdf_session(
    pdf_path: Optional[str],
    filename: str,
    parsed_products: List[Dict[str, Any]],
    raw_text_excerpt: str = "",
    pages_count: int = 0
) -> Dict[str, Any]:
    """
    Módulo 2 (Agente de Stock / Almacén):
    Almacena los modelos y cantidades extraídos del PDF de stock interno y genera el contexto del Agente 2.
    """
    stock_session_id = str(uuid.uuid4())[:12]

    # Consolidar por SKU normalizado (sumando stock si aparece en varias líneas del PDF)
    consolidated: Dict[str, Dict[str, Any]] = {}
    for p in parsed_products:
        sku = str(p.get("sku") or p.get("model") or "").strip()
        if not sku:
            continue
        norm_sku = stock_analyzer.normalize_sku(sku)
        if not norm_sku:
            continue
        qty = int(p.get("stock") if p.get("stock") is not None else p.get("stock_qty", 0))
        cost = float(p.get("cost") if p.get("cost") is not None else p.get("cost_price", 0.0))
        desc = str(p.get("description") or "").strip()
        brand = str(p.get("brand") or "Genérico").strip()
        cat = str(p.get("category") or "").strip()
        if not cat or cat in ("Otros", "N/D"):
            cat = stock_analyzer.classify_appliance_type(f"{desc} {sku}", sku)

        if norm_sku in consolidated:
            consolidated[norm_sku]["stock"] += qty
            if cost > 0 and consolidated[norm_sku]["cost"] == 0:
                consolidated[norm_sku]["cost"] = round(cost, 2)
        else:
            consolidated[norm_sku] = {
                "sku": sku,
                "normalized_sku": norm_sku,
                "brand": brand,
                "category": cat,
                "description": desc,
                "stock": qty,
                "cost": round(cost, 2)
            }

    items_list = list(consolidated.values())
    total_units = sum(it["stock"] for it in items_list)
    total_val = round(sum(it["stock"] * it["cost"] for it in items_list), 2)

    _STOCK_SESSIONS[stock_session_id] = {
        "stock_session_id": stock_session_id,
        "filename": filename,
        "pages_count": pages_count,
        "items": items_list,
        "raw_text_excerpt": raw_text_excerpt[:3000],
        "total_units": total_units,
        "total_valuation": total_val,
        "created_at": _now_time()
    }
    _trim_sessions(_STOCK_SESSIONS)

    agent_messages = [
        {
            "agent": "stock",
            "agent_name": "Agente de Stock (Almacén PDF)",
            "badge": "Módulo 2 · Lector PDF ERP",
            "time": _now_time(),
            "text": (
                f"He procesado el informe PDF **{filename}** ({pages_count or 1} pág.). "
                f"Se han extraído **{len(items_list)} referencias únicas** en almacén "
                f"que suman **{total_units} unidades físicas** (valoración interna: {total_val:,.2f} €)."
            )
        }
    ]

    return {
        "status": "success",
        "stock_session_id": stock_session_id,
        "filename": filename,
        "pages_count": pages_count,
        "items_count": len(items_list),
        "total_units": total_units,
        "total_valuation": total_val,
        "raw_text_excerpt": raw_text_excerpt[:1500],
        "items_preview": items_list[:50],
        "agent_messages": agent_messages
    }


def _extract_numeric_signature(code: str) -> str:
    """Extrae la secuencia numérica principal de un modelo/SKU (ej. '3TS998BA' -> '3998')."""
    return "".join(re.findall(r'\d+', code or ""))


def _compute_sku_similarity(tariff_norm: str, stock_norm: str) -> Tuple[float, str]:
    """
    Calcula la similitud entre un código normalizado de tarifa y uno de stock PDF.
    Garantiza que los números clave del modelo coincidan para no emparejar modelos distintos (ej. 3TS998B vs 3TS999B).
    """
    if not tariff_norm or not stock_norm:
        return 0.0, "NONE"

    if tariff_norm == stock_norm:
        return 1.0, "EXACTO"

    # 1. Coincidencia por prefijo (ej. 'WGB256A0ES' vs 'WGB256A0' o variantes de color al final)
    min_len = min(len(tariff_norm), len(stock_norm))
    max_len = max(len(tariff_norm), len(stock_norm))
    if min_len >= 5 and (tariff_norm.startswith(stock_norm) or stock_norm.startswith(tariff_norm)):
        num_t = _extract_numeric_signature(tariff_norm)
        num_s = _extract_numeric_signature(stock_norm)
        # Si comparten la misma raíz numérica o uno es prefijo con letras finales de color/país
        if num_t == num_s or (len(num_t) >= 3 and (num_t.startswith(num_s) or num_s.startswith(num_t))):
            ratio = min_len / max_len
            return max(0.86, round(ratio, 3)), "FUZZY"

    # 2. Coincidencia Fuzzy controlada: requiere que el bloque numérico principal coincida
    num_t = _extract_numeric_signature(tariff_norm)
    num_s = _extract_numeric_signature(stock_norm)
    if not num_t or not num_s or num_t != num_s:
        return 0.0, "NONE"

    ratio = SequenceMatcher(None, tariff_norm, stock_norm).ratio()
    if ratio >= 0.75:
        return round(ratio, 3), "FUZZY"
    return 0.0, "NONE"


def run_multi_agent_cross_reference(
    tariff_session_id: str,
    stock_session_id: Optional[str] = None,
    fallback_stock_items: Optional[List[Dict[str, Any]]] = None,
    fuzzy_threshold: float = 0.78,
    low_stock_threshold: int = 2,
    gemini_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Módulo 3: Motor de Coordinación Multi-Agente y Matching (Exacto + Fuzzy).
    Cruza el contexto del Agente de Tarifas (con la columna de precio elegida por el usuario)
    y el contexto del Agente de Stock (PDF), generando la conversación entre agentes y el Dashboard final.
    """
    if tariff_session_id not in _TARIFF_SESSIONS:
        raise ValueError("No se encontró la sesión del Agente de Tarifas. Sube y confirma primero el archivo Excel/CSV.")

    t_sess = _TARIFF_SESSIONS[tariff_session_id]
    tariff_items = t_sess.get("extracted_items") or []
    if not tariff_items:
        # Extraer automáticamente con el mapeo actual si aún no se había ejecutado
        mapping = t_sess["mapping"]
        extract_tariff_with_mapping(
            session_id=tariff_session_id,
            model_col=mapping["model_col"],
            price_col=mapping["price_col"],
            desc_col=mapping.get("desc_col", -1),
            brand_col=mapping.get("brand_col", -1)
        )
        tariff_items = t_sess.get("extracted_items") or []

    if not tariff_items:
        raise ValueError("La tarifa no contiene artículos válidos con las columnas seleccionadas.")

    # Obtener contexto del Agente de Stock
    stock_items: List[Dict[str, Any]] = []
    stock_filename = "Inventario Activo en Memoria"
    if stock_session_id and stock_session_id in _STOCK_SESSIONS:
        s_sess = _STOCK_SESSIONS[stock_session_id]
        stock_items = s_sess["items"]
        stock_filename = s_sess["filename"]
    elif _STOCK_SESSIONS:
        latest_sid = list(_STOCK_SESSIONS.keys())[-1]
        s_sess = _STOCK_SESSIONS[latest_sid]
        stock_items = s_sess["items"]
        stock_filename = s_sess["filename"]
    elif fallback_stock_items:
        temp_res = create_stock_pdf_session(None, "inventory.json (Almacén Local)", fallback_stock_items)
        stock_items = _STOCK_SESSIONS[temp_res["stock_session_id"]]["items"]
        stock_filename = "inventory.json (Almacén Local)"
    else:
        raise ValueError("No se ha cargado ningún PDF de Stock en el Agente de Almacén.")

    # Índices de búsqueda para Stock
    stock_by_norm: Dict[str, Dict[str, Any]] = {it["normalized_sku"]: it for it in stock_items}
    matched_stock_norms = set()

    matched_items: List[Dict[str, Any]] = []
    missing_items: List[Dict[str, Any]] = []
    exact_matches_count = 0
    fuzzy_matches_count = 0

    for t_item in tariff_items:
        t_norm = t_item["normalized_model"]
        t_model = t_item["model"]
        t_price = float(t_item["price"])
        t_desc = t_item["description"]
        t_cat = t_item.get("category") or "Otros"
        t_brand = t_item.get("brand") or "General"

        matched_s: Optional[Dict[str, Any]] = None
        match_type = "NONE"
        match_score = 0.0

        # 1. Intento de coincidencia exacta normalizada O(1)
        if t_norm in stock_by_norm:
            matched_s = stock_by_norm[t_norm]
            match_type = "EXACTO"
            match_score = 1.0
        else:
            # 2. Intento de Fuzzy Matching inteligente
            best_score = 0.0
            best_cand = None
            for s_norm, s_item in stock_by_norm.items():
                score, mtype = _compute_sku_similarity(t_norm, s_norm)
                if score >= fuzzy_threshold and score > best_score:
                    best_score = score
                    best_cand = s_item
                    match_type = mtype
            if best_cand is not None:
                matched_s = best_cand
                match_score = best_score

        if matched_s is not None:
            matched_stock_norms.add(matched_s["normalized_sku"])
            if match_type == "EXACTO":
                exact_matches_count += 1
            else:
                fuzzy_matches_count += 1

            s_qty = int(matched_s.get("stock", 0))
            s_cost = float(matched_s.get("cost", 0.0))
            price_diff = round(t_price - s_cost, 2) if s_cost > 0 else 0.0
            price_diff_pct = round(((t_price - s_cost) / s_cost) * 100, 1) if s_cost > 0 else 0.0

            if s_qty <= 0:
                status = "SIN_STOCK_PDF"
                suggested_order = max(1, low_stock_threshold)
            elif s_qty < low_stock_threshold:
                status = "STOCK_BAJO"
                suggested_order = max(1, low_stock_threshold - s_qty)
            else:
                status = "CUBIERTO"
                suggested_order = 0

            matched_items.append({
                "tariff_model": t_model,
                "stock_model": matched_s["sku"],
                "match_type": match_type,
                "match_score": round(match_score * 100, 1),
                "brand": t_brand if t_brand != "General" else matched_s.get("brand", "General"),
                "category": t_cat if t_cat != "Otros" else matched_s.get("category", "Otros"),
                "description": t_desc if len(t_desc) >= len(matched_s.get("description", "")) else matched_s.get("description", t_desc),
                "tariff_price": t_price,
                "stock_cost": s_cost,
                "price_diff": price_diff,
                "price_diff_pct": price_diff_pct,
                "stock_qty": s_qty,
                "status": status,
                "suggested_order_qty": suggested_order
            })

            # Si aparece en el PDF pero con 0 unidades, también lo incluimos en la vista de revisión de faltantes
            if s_qty <= 0:
                missing_items.append({
                    "tariff_model": t_model,
                    "brand": t_brand,
                    "category": t_cat,
                    "description": t_desc,
                    "tariff_price": t_price,
                    "stock_qty": 0,
                    "reason": "En PDF con 0 uds (Agotado)",
                    "suggested_order_qty": max(1, low_stock_threshold),
                    "estimated_cost": round(t_price * max(1, low_stock_threshold), 2)
                })
        else:
            # No aparece en absoluto en el PDF de stock
            missing_items.append({
                "tariff_model": t_model,
                "brand": t_brand,
                "category": t_cat,
                "description": t_desc,
                "tariff_price": t_price,
                "stock_qty": 0,
                "reason": "No figura en el PDF de Stock",
                "suggested_order_qty": 1,
                "estimated_cost": round(t_price, 2)
            })

    # Artículos que están en el PDF de Stock pero NO en la tarifa del proveedor (viceversa)
    stock_only_items: List[Dict[str, Any]] = []
    for s_norm, s_item in stock_by_norm.items():
        if s_norm not in matched_stock_norms:
            stock_only_items.append({
                "stock_model": s_item["sku"],
                "brand": s_item.get("brand", "Genérico"),
                "category": s_item.get("category", "Otros"),
                "description": s_item.get("description", ""),
                "stock_qty": int(s_item.get("stock", 0)),
                "stock_cost": float(s_item.get("cost", 0.0))
            })

    # Ordenar resultados: primero los que tienen stock bajo o agotado en coincidentes
    matched_items.sort(key=lambda x: (x["stock_qty"], -x["tariff_price"]))
    missing_items.sort(key=lambda x: (0 if "0 uds" in x["reason"] else 1, x["tariff_price"]))
    stock_only_items.sort(key=lambda x: -x["stock_qty"])

    columns = t_sess["columns"]
    mapping = t_sess["mapping"]
    price_col_name = columns[mapping["price_col"]]["name"] if 0 <= mapping["price_col"] < len(columns) else "Precio"
    model_col_name = columns[mapping["model_col"]]["name"] if 0 <= mapping["model_col"] < len(columns) else "Modelo"

    # Construir transcripción de comunicación Multi-Agente
    dialogue = [
        {
            "agent": "tariff",
            "agent_name": "Agente de Tarifas (Proveedor)",
            "badge": f"Tarifa: {t_sess['filename']}",
            "time": _now_time(),
            "text": (
                f"Envío al coordinador **{len(tariff_items)} modelos** extraídos de `{t_sess['filename']}` "
                f"(Hoja `{t_sess['active_sheet']}`). Columna de referencia: **{model_col_name}** | "
                f"Columna de precio seleccionada por el usuario: **{price_col_name}**."
            )
        },
        {
            "agent": "stock",
            "agent_name": "Agente de Stock (Almacén PDF)",
            "badge": f"Stock: {stock_filename}",
            "time": _now_time(),
            "text": (
                f"Envío inventario extraído del PDF `{stock_filename}` con **{len(stock_items)} referencias únicas** "
                f"y **{sum(it['stock'] for it in stock_items)} unidades** totales en almacén."
            )
        },
        {
            "agent": "coordinator",
            "agent_name": "Agente Coordinador (Motor de Matching)",
            "badge": "Cruce Exacto + Fuzzy",
            "time": _now_time(),
            "text": (
                f"Cruce completado entre ambas fuentes:\n"
                f"• **{len(matched_items)} artículos coincidentes** ({exact_matches_count} por coincidencia exacta y "
                f"{fuzzy_matches_count} por *Fuzzy Matching* de variantes de código).\n"
                f"• **{len(missing_items)} artículos de la tarifa faltantes / sin stock** pendientes de revisar.\n"
                f"• **{len(stock_only_items)} artículos del PDF de almacén** que no figuran en esta tarifa."
            )
        }
    ]

    # Si hay clave de Gemini configurada, añadir análisis breve del Agente IA de Compras
    if gemini_api_key and len(tariff_items) > 0:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_api_key)
            top_missing = [f"{m['tariff_model']} ({m['tariff_price']}€)" for m in missing_items[:6]]
            cheaper_in_tariff = [
                f"{m['tariff_model']} (Tarifa: {m['tariff_price']}€ vs Coste ERP: {m['stock_cost']}€)"
                for m in matched_items if m["stock_cost"] > 0 and m["price_diff"] < -1.0
            ][:5]
            prompt = (
                f"Eres el Agente Director de Compras IA. Resume en 3 frases breves y accionables el resultado del cruce:\n"
                f"- Tarifa: {t_sess['filename']} ({len(tariff_items)} refs, columna precio '{price_col_name}')\n"
                f"- Stock PDF: {stock_filename} ({len(stock_items)} refs)\n"
                f"- Coincidentes: {len(matched_items)} ({exact_matches_count} exactos, {fuzzy_matches_count} fuzzy)\n"
                f"- Faltantes/Sin stock en tarifa: {len(missing_items)} (ejemplos: {', '.join(top_missing) or 'ninguno'})\n"
                f"- Oportunidades con precio tarifa menor al coste actual: {', '.join(cheaper_in_tariff) or 'sin bajadas destacadas'}."
            )
            for m_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]:
                try:
                    resp = client.models.generate_content(model=m_name, contents=prompt)
                    if resp and resp.text:
                        dialogue.append({
                            "agent": "ai_advisor",
                            "agent_name": "Agente Estratega Gemini IA",
                            "badge": "Dictamen Inteligente",
                            "time": _now_time(),
                            "text": resp.text.strip()
                        })
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Error generando dictamen Gemini en cruce multi-agente: {e}")

    kpis = {
        "total_tariff_items": len(tariff_items),
        "total_stock_items": len(stock_items),
        "matched_count": len(matched_items),
        "exact_matches_count": exact_matches_count,
        "fuzzy_matches_count": fuzzy_matches_count,
        "matched_with_stock_count": sum(1 for m in matched_items if m["stock_qty"] > 0),
        "missing_in_stock_count": len(missing_items),
        "stock_only_count": len(stock_only_items),
        "price_col_name": price_col_name,
        "model_col_name": model_col_name
    }

    result_payload = {
        "status": "success",
        "kpis": kpis,
        "dialogue": dialogue,
        "matched_items": matched_items,
        "missing_items": missing_items,
        "stock_only_items": stock_only_items
    }

    global _LAST_CROSS_RESULT
    _LAST_CROSS_RESULT = result_payload
    return result_payload


def export_cross_reference_excel(custom_payload: Optional[Dict[str, Any]] = None) -> io.BytesIO:
    """Genera un archivo Excel (.xlsx) profesional con las 3 pestañas del cruce Multi-Agente."""
    data = custom_payload or _LAST_CROSS_RESULT
    if not data or not data.get("kpis"):
        raise ValueError("No hay ningún cruce Multi-Agente calculado para exportar.")

    wb = Workbook()
    header_fill = PatternFill(start_color="1E1B4B", end_color="1E1B4B", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    # Hoja 1: Artículos Coincidentes
    ws1 = wb.active
    ws1.title = "1_Coincidentes_Tarifa_Stock"
    headers1 = [
        "Modelo (Tarifa)", "Modelo (PDF Stock)", "Tipo Match", "Similitud (%)",
        "Marca", "Categoría", "Descripción", "Precio Tarifa (€)",
        "Coste ERP (€)", "Diferencia (€)", "Stock Actual (Uds)", "Estado", "Uds Sugeridas"
    ]
    ws1.append(headers1)
    for col_num in range(1, len(headers1) + 1):
        c = ws1.cell(row=1, column=col_num)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    for item in data.get("matched_items", []):
        ws1.append([
            item.get("tariff_model", ""),
            item.get("stock_model", ""),
            item.get("match_type", "EXACTO"),
            item.get("match_score", 100.0),
            item.get("brand", ""),
            item.get("category", ""),
            item.get("description", ""),
            item.get("tariff_price", 0.0),
            item.get("stock_cost", 0.0),
            item.get("price_diff", 0.0),
            item.get("stock_qty", 0),
            item.get("status", ""),
            item.get("suggested_order_qty", 0)
        ])

    # Hoja 2: Artículos Faltantes / Pendientes de Revisar
    ws2 = wb.create_sheet(title="2_Faltantes_En_Tarifa")
    headers2 = [
        "Modelo (Tarifa)", "Marca", "Categoría", "Descripción",
        "Precio Tarifa (€)", "Stock Actual", "Motivo / Estado", "Cantidad a Pedir", "Importe Estimado (€)"
    ]
    ws2.append(headers2)
    for col_num in range(1, len(headers2) + 1):
        c = ws2.cell(row=1, column=col_num)
        c.fill = PatternFill(start_color="7F1D1D", end_color="7F1D1D", fill_type="solid")
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    for item in data.get("missing_items", []):
        qty = int(item.get("suggested_order_qty", 1))
        price = float(item.get("tariff_price", 0.0))
        ws2.append([
            item.get("tariff_model", ""),
            item.get("brand", ""),
            item.get("category", ""),
            item.get("description", ""),
            price,
            item.get("stock_qty", 0),
            item.get("reason", "No figura en PDF de Stock"),
            qty,
            round(price * qty, 2)
        ])

    # Hoja 3: En Stock PDF pero No en Tarifa
    ws3 = wb.create_sheet(title="3_Solo_En_PDF_Stock")
    headers3 = ["Modelo (PDF Stock)", "Marca", "Categoría", "Descripción", "Stock en Almacén (Uds)", "Coste Unitario ERP (€)"]
    ws3.append(headers3)
    for col_num in range(1, len(headers3) + 1):
        c = ws3.cell(row=1, column=col_num)
        c.fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")

    for item in data.get("stock_only_items", []):
        ws3.append([
            item.get("stock_model", ""),
            item.get("brand", ""),
            item.get("category", ""),
            item.get("description", ""),
            item.get("stock_qty", 0),
            item.get("stock_cost", 0.0)
        ])

    # Ajustar ancho de columnas en las 3 hojas
    for ws in [ws1, ws2, ws3]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                cell.border = border_thin
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 48)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output

