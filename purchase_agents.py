import os
import io
import re
import math
import uuid
import json
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Tuple
import collections

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import stock_analyzer

logger = logging.getLogger("garde_app.purchase_agents")

# Almacenamiento en memoria de sesiones de trabajo de los Agentes (con limpieza automática FIFO)
_TARIFF_SESSIONS: Dict[str, Dict[str, Any]] = {}
_STOCK_SESSIONS: Dict[str, Dict[str, Any]] = {}
_ORDER_SESSIONS: Dict[str, Dict[str, Any]] = {}
_SALES_SESSIONS: Dict[str, Dict[str, Any]] = {}
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
    if hasattr(stock_analyzer, "is_valid_Main_SKU"):
        return stock_analyzer.is_valid_Main_SKU(val)
    if val is None:
        return False
    s = str(val).strip()
    if len(s) < 2 or len(s) > 60:
        return False
    if " " in s and len(s.split()) > 6:
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

    # Excel (.xlsx / .xls): leer ÚNICAMENTE la hoja requerida de forma optimizada
    target = sheet_name or 0
    df_sheet = pd.read_excel(io.BytesIO(file_bytes), sheet_name=target, header=None, dtype=str)
    cleaned = df_sheet.replace(r'^\s*$', pd.NA, regex=True).dropna(how="all").dropna(axis=1, how="all")
    if not cleaned.empty:
        df_sheet = cleaned.reset_index(drop=True)
        if df_sheet.shape[1] > 80:
            df_sheet = df_sheet.iloc[:, :80]
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

    # Construir filas de vista previa ultrarrápida (hasta 25 filas en memoria directa)
    data_df = df.iloc[h_row + 1:].reset_index(drop=True) if h_row + 1 < len(df) else df.copy()
    preview_rows = []
    num_cols = df.shape[1]
    for row_vals in data_df.head(25).values:
        row_cells = []
        for c_idx in range(num_cols):
            val = row_vals[c_idx] if c_idx < len(row_vals) else ""
            if pd.isna(val) or str(val).strip().lower() in ("nan", "none", "<na>"):
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

    model_col_vals = data_df.iloc[:, model_col].values
    price_col_vals = data_df.iloc[:, price_col].values
    desc_col_vals = data_df.iloc[:, desc_col].values if (desc_col is not None and 0 <= desc_col < num_cols) else None
    brand_col_vals = data_df.iloc[:, brand_col].values if (brand_col is not None and 0 <= brand_col < num_cols) else None
    n_rows = len(data_df)

    for i in range(n_rows):
        raw_m = model_col_vals[i]
        if pd.isna(raw_m):
            skipped_rows += 1
            continue
        raw_model = str(raw_m).strip()
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

        raw_price_cell = price_col_vals[i]
        price_val = clean_price_value(raw_price_cell)
        if price_val is None or price_val <= 0:
            skipped_rows += 1
            continue

        raw_desc = ""
        if desc_col_vals is not None and pd.notna(desc_col_vals[i]):
            raw_desc = str(desc_col_vals[i]).strip()
            if raw_desc.lower() in ("nan", "none", "null"):
                raw_desc = ""

        raw_brand = ""
        if brand_col_vals is not None and pd.notna(brand_col_vals[i]):
            raw_brand = str(brand_col_vals[i]).strip()
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

        # 1. Clasificación precisa usando descripción directa y modelo (evita contaminación por otras columnas)
        primary_text = f"{raw_desc} {raw_model}".strip()
        category = stock_analyzer.classify_appliance_type(primary_text, raw_model)
        # 2. Si dio 'Otros', comprobar escaneo de toda la fila por si hay columnas de Familia/Subfamilia en el Excel
        if category == "Otros":
            row_cells = [str(df.iat[i, c_idx]).strip() for c_idx in range(df.shape[1]) if pd.notna(df.iat[i, c_idx])]
            row_full_text = " ".join([c for c in row_cells if c.lower() not in ("nan", "none", "null")])
            cat_row = stock_analyzer.classify_appliance_type(f"{primary_text} {row_full_text}".strip(), raw_model)
            if cat_row != "Otros":
                category = cat_row
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
                "cost": round(cost, 2),
                "unit_cost": round(cost, 2),
                "total_cost": round(cost * qty, 2)
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


def parse_order_pdf_fallback(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parser de respaldo para hojas de pedido PDF (ERP o albaranes de compra) cuando el formato difiere
    del informe de stock valorado estándar. Detecta líneas con SKU, cantidad y precio unitario.
    """
    if not raw_text:
        return []
    items: List[Dict[str, Any]] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if len(line) < 6:
            continue
        # Ignorar cabeceras comunes de pedido
        if re.search(r'\b(p[aá]gina|fecha|proveedor|cliente|nif|cif|subtotal|base imponible|iva|total pedido)\b', line, re.IGNORECASE):
            if not any(ch.isdigit() for ch in line[:10]):
                continue
        tokens = line.split()
        if len(tokens) < 2:
            continue
        # Buscar un token que sea un SKU válido
        sku_cand = ""
        sku_idx = -1
        for idx, tok in enumerate(tokens[:6]):
            clean_tok = tok.strip("()[].,;:")
            if is_valid_sku(clean_tok) and any(c.isalpha() for c in clean_tok) and any(c.isdigit() for c in clean_tok):
                sku_cand = clean_tok
                sku_idx = idx
                break
        if not sku_cand:
            continue

        # Extraer números (cantidades y precios) al final de la línea
        tail_tokens = tokens[sku_idx + 1:]
        nums: List[float] = []
        desc_tokens: List[str] = []
        for tok in tail_tokens:
            p_val = _clean_price_value(tok)
            if p_val is not None and re.search(r'\d', tok):
                nums.append(p_val)
            elif not nums:
                desc_tokens.append(tok)

        if not nums:
            continue

        # Determinar cantidad y precio unitario (si hay 2 o más números al final: ej. Cantidad, Precio Unitario, Total)
        qty = 1
        unit_price = 0.0
        if len(nums) == 1:
            unit_price = nums[0]
        elif len(nums) >= 2:
            # Comprobar relación Cantidad * Precio_Unitario ≈ Total
            found_rel = False
            for i_q in range(len(nums)):
                q_cand = nums[i_q]
                if q_cand == int(q_cand) and 1 <= q_cand <= 500:
                    for i_p in range(len(nums)):
                        if i_p == i_q:
                            continue
                        p_cand = nums[i_p]
                        for i_tot in range(len(nums)):
                            if i_tot in (i_q, i_p):
                                continue
                            if abs((q_cand * p_cand) - nums[i_tot]) <= 1.5 and p_cand > 5.0:
                                qty = int(q_cand)
                                unit_price = float(p_cand)
                                found_rel = True
                                break
                        if found_rel:
                            break
                if found_rel:
                    break
            if not found_rel:
                # Si el primero es un entero pequeño (unidades) y el siguiente es el precio unitario
                if nums[0] == int(nums[0]) and 1 <= nums[0] <= 200 and nums[1] > 5.0:
                    qty = int(nums[0])
                    unit_price = float(nums[1])
                elif nums[-2] > 5.0 and nums[-1] >= nums[-2]:
                    unit_price = float(nums[-2])
                    if nums[0] == int(nums[0]) and 1 <= nums[0] <= 200:
                        qty = int(nums[0])
                else:
                    unit_price = float(nums[-1])

        if unit_price <= 0:
            continue

        desc_str = " ".join(desc_tokens).strip() or f"Artículo {sku_cand}"
        brand_str = stock_analyzer.extract_brand_from_text(f"{sku_cand} {desc_str}") if hasattr(stock_analyzer, "extract_brand_from_text") else "General"
        cat_str = stock_analyzer.classify_appliance_type(f"{desc_str} {sku_cand}", sku_cand)
        items.append({
            "sku": sku_cand,
            "description": desc_str,
            "stock": qty,
            "cost": round(unit_price, 2),
            "brand": brand_str or "General",
            "category": cat_str
        })
    return items


def create_order_pdf_session(
    pdf_path: Optional[str],
    filename: str,
    parsed_products: List[Dict[str, Any]],
    raw_text_excerpt: str = "",
    pages_count: int = 0
) -> Dict[str, Any]:
    """
    Módulo 3 (Agente Auditor de Pedidos ERP):
    Almacena las líneas extraídas de la Hoja de Pedido del ERP (PDF) para auditar sus precios
    contra la tarifa actual del proveedor y gestionar diferencias por 'Fuera de Factura'.
    """
    order_session_id = str(uuid.uuid4())[:12]

    consolidated: Dict[str, Dict[str, Any]] = {}
    for p in parsed_products:
        sku = str(p.get("sku") or p.get("model") or "").strip()
        if not sku:
            continue
        norm_sku = stock_analyzer.normalize_sku(sku)
        if not norm_sku:
            continue
        qty = int(p.get("stock") if p.get("stock") is not None else p.get("order_qty", 1))
        if qty <= 0:
            qty = 1
        unit_price = float(p.get("cost") if p.get("cost") is not None else p.get("unit_price", 0.0))
        desc = str(p.get("description") or "").strip()
        brand = str(p.get("brand") or "General").strip()
        cat = str(p.get("category") or "").strip()
        if not cat or cat in ("Otros", "N/D"):
            cat = stock_analyzer.classify_appliance_type(f"{desc} {sku}", sku)

        if norm_sku in consolidated:
            consolidated[norm_sku]["order_qty"] += qty
            if unit_price > 0:
                consolidated[norm_sku]["order_unit_price"] = round(unit_price, 2)
            consolidated[norm_sku]["order_total_price"] = round(
                consolidated[norm_sku]["order_qty"] * consolidated[norm_sku]["order_unit_price"], 2
            )
        else:
            consolidated[norm_sku] = {
                "sku": sku,
                "normalized_sku": norm_sku,
                "brand": brand,
                "category": cat,
                "description": desc,
                "order_qty": qty,
                "order_unit_price": round(unit_price, 2),
                "order_total_price": round(unit_price * qty, 2)
            }

    items_list = list(consolidated.values())
    total_units = sum(it["order_qty"] for it in items_list)
    total_amount = round(sum(it["order_total_price"] for it in items_list), 2)

    _ORDER_SESSIONS[order_session_id] = {
        "order_session_id": order_session_id,
        "filename": filename,
        "pages_count": pages_count,
        "items": items_list,
        "raw_text_excerpt": raw_text_excerpt[:3000],
        "total_units": total_units,
        "total_order_amount": total_amount,
        "created_at": _now_time()
    }
    _trim_sessions(_ORDER_SESSIONS)

    agent_messages = [
        {
            "agent": "order",
            "agent_name": "Agente Auditor de Pedido (PDF ERP)",
            "badge": "Módulo 3 · Hoja de Pedido",
            "time": _now_time(),
            "text": (
                f"He leído la Hoja de Pedido **{filename}** ({pages_count or 1} pág.). "
                f"Detectadas **{len(items_list)} referencias pedidas** ({total_units} uds en total) "
                f"por un importe bruto en pedido de **{total_amount:,.2f} €**. Listo para auditar contra la Tarifa."
            )
        }
    ]

    return {
        "status": "success",
        "order_session_id": order_session_id,
        "filename": filename,
        "pages_count": pages_count,
        "items_count": len(items_list),
        "total_units": total_units,
        "total_order_amount": total_amount,
        "raw_text_excerpt": raw_text_excerpt[:1500],
        "items_preview": items_list[:50],
        "agent_messages": agent_messages
    }


def parse_sales_pdf_fallback(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parser heurístico de reserva para informes de ventas del ERP en PDF.
    Detecta líneas con SKU/Modelo, descripción, unidades vendidas en el periodo e importe de venta.
    """
    items = []
    if not raw_text:
        return items

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or len(line) < 4:
            continue

        if re.search(r'(?:total|subtotal|p[aá]gina|fecha|informe|listado|art[ií]culo|descripci[oó]n|ventas|unidades)', line, re.IGNORECASE) and not re.search(r'\d{3,}', line):
            continue

        tokens = line.split()
        if len(tokens) < 2:
            continue

        sku_cand = None
        for tok in tokens[:4]:
            t_clean = re.sub(r'^[^\w]+|[^\w]+$', '', tok)
            if is_valid_sku(t_clean):
                sku_cand = t_clean
                break
        if not sku_cand:
            continue

        nums = []
        desc_tokens = []
        for tok in tokens:
            if tok == sku_cand and not desc_tokens:
                continue
            num_clean = re.sub(r'[\u20ac€EUR\$\s\*\xa0]', '', tok)
            if re.match(r'^-?\d+([.,]\d+)?$', num_clean):
                val = float(num_clean.replace(',', '.'))
                nums.append(val)
            else:
                desc_tokens.append(tok)

        units_sold = 1
        sales_amt = 0.0
        if len(nums) == 1:
            units_sold = max(1, int(round(nums[0])))
        elif len(nums) >= 2:
            int_candidates = [n for n in nums if n == int(n) and 0 < n <= 10000]
            if int_candidates:
                units_sold = int(int_candidates[0])
                sales_amt = max(nums) if max(nums) != units_sold else 0.0
            else:
                units_sold = max(1, int(round(nums[0])))
                sales_amt = nums[-1]

        desc_str = " ".join(desc_tokens).strip() or f"Artículo {sku_cand}"
        brand_str = stock_analyzer.extract_brand_from_text(f"{sku_cand} {desc_str}") if hasattr(stock_analyzer, "extract_brand_from_text") else "General"
        cat_str = stock_analyzer.classify_appliance_type(f"{desc_str} {sku_cand}", sku_cand)

        items.append({
            "sku": sku_cand,
            "description": desc_str,
            "stock": units_sold,
            "units_sold": units_sold,
            "sales_amount": round(sales_amt, 2),
            "cost": round(sales_amt / units_sold, 2) if units_sold > 0 and sales_amt > 0 else 0.0,
            "brand": brand_str or "General",
            "category": cat_str
        })
    return items


def create_sales_pdf_session(
    pdf_path: Optional[str],
    filename: str,
    parsed_products: List[Dict[str, Any]],
    period_days: int = 30,
    raw_text_excerpt: str = "",
    pages_count: int = 0
) -> Dict[str, Any]:
    """
    Módulo 4 (Agente de Ventas y Rotación):
    Almacena el histórico de ventas (unidades vendidas y rotación diaria/mensual)
    para contrastarlo contra el stock disponible y las cantidades del pedido ERP.
    """
    sales_session_id = str(uuid.uuid4())[:12]
    period_days = max(1, int(period_days or 30))

    consolidated: Dict[str, Dict[str, Any]] = {}
    for p in parsed_products:
        sku = str(p.get("sku") or p.get("model") or "").strip()
        if not sku:
            continue
        norm_sku = stock_analyzer.normalize_sku(sku)
        if not norm_sku:
            continue
        qty = int(p.get("units_sold") if p.get("units_sold") is not None else p.get("stock", 1))
        if qty <= 0:
            qty = 1
        amount = float(p.get("sales_amount") if p.get("sales_amount") is not None else (float(p.get("cost", 0.0)) * qty))
        desc = str(p.get("description") or "").strip()
        brand = str(p.get("brand") or "General").strip()
        cat = str(p.get("category") or "").strip()
        if not cat or cat in ("Otros", "N/D"):
            cat = stock_analyzer.classify_appliance_type(f"{desc} {sku}", sku)

        if norm_sku in consolidated:
            consolidated[norm_sku]["units_sold"] += qty
            consolidated[norm_sku]["sales_amount"] += amount
        else:
            consolidated[norm_sku] = {
                "sku": sku,
                "normalized_sku": norm_sku,
                "brand": brand,
                "category": cat,
                "description": desc,
                "units_sold": qty,
                "sales_amount": round(amount, 2),
                "period_days": period_days
            }

    for it in consolidated.values():
        u = it["units_sold"]
        it["daily_sales_rate"] = round(u / period_days, 3)
        it["monthly_run_rate"] = round((u / period_days) * 30.0, 1)
        it["avg_unit_price"] = round(it["sales_amount"] / u, 2) if u > 0 and it["sales_amount"] > 0 else 0.0

    items_list = sorted(consolidated.values(), key=lambda x: x["units_sold"], reverse=True)
    total_units_sold = sum(it["units_sold"] for it in items_list)
    total_sales_amount = round(sum(it["sales_amount"] for it in items_list), 2)
    daily_global_rate = round(total_units_sold / period_days, 2)

    _SALES_SESSIONS[sales_session_id] = {
        "sales_session_id": sales_session_id,
        "filename": filename,
        "pages_count": pages_count,
        "period_days": period_days,
        "items": items_list,
        "raw_text_excerpt": raw_text_excerpt[:3000],
        "total_units_sold": total_units_sold,
        "total_sales_amount": total_sales_amount,
        "daily_global_rate": daily_global_rate,
        "created_at": _now_time()
    }
    _trim_sessions(_SALES_SESSIONS)

    agent_messages = [
        {
            "agent": "sales",
            "agent_name": "Agente de Ventas y Rotación (PDF ERP)",
            "badge": f"Módulo 4 · Ventas ({period_days} días)",
            "time": _now_time(),
            "text": (
                f"He procesado el informe de ventas **{filename}** ({pages_count or 1} pág.) "
                f"para un periodo de **{period_days} días**. "
                f"Analizadas **{len(items_list)} referencias vendidas** ({total_units_sold} uds totales, "
                f"ritmo de **{daily_global_rate} uds/día**). Listo para verificar rotación y suficiencia de pedido."
            )
        }
    ]

    return {
        "status": "success",
        "sales_session_id": sales_session_id,
        "filename": filename,
        "pages_count": pages_count,
        "period_days": period_days,
        "items_count": len(items_list),
        "total_units_sold": total_units_sold,
        "total_sales_amount": total_sales_amount,
        "daily_global_rate": daily_global_rate,
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

    # Coincidencia si una de las dos referencias contiene el nombre de la marca como prefijo
    # (ej. Tarifa: 'BALAY 3TS988B' -> 'BALAY3TS988B' vs Stock: '3TS988B')
    if hasattr(stock_analyzer, "strip_brand_from_sku"):
        t_nobrand = stock_analyzer.strip_brand_from_sku(tariff_norm)
        s_nobrand = stock_analyzer.strip_brand_from_sku(stock_norm)
        if (t_nobrand and t_nobrand == stock_norm) or (s_nobrand and tariff_norm == s_nobrand) or (t_nobrand and s_nobrand and t_nobrand == s_nobrand):
            return 1.0, "EXACTO"

    # Coincidencia de modelo base eliminando revisiones (/01, /02) o sufijo país/acabado
    t_base = re.sub(r'(?:0\d|ES|SP|EU|IB)$', '', tariff_norm)
    s_base = re.sub(r'(?:0\d|ES|SP|EU|IB)$', '', stock_norm)
    if t_base and s_base and t_base == s_base and len(t_base) >= 5:
        return 0.98, "EXACTO"

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


def _build_lookup_indices(items: List[Dict[str, Any]], sku_key: str = "normalized_sku"):
    """Construye índices O(1) de búsqueda por SKU normalizado, sin marca, base y numérico."""
    by_norm: Dict[str, Dict[str, Any]] = {}
    by_nobrand: Dict[str, Dict[str, Any]] = {}
    by_base: Dict[str, Dict[str, Any]] = {}
    by_numeric: Dict[str, List[Tuple[str, Dict[str, Any]]]] = collections.defaultdict(list)

    for it in items:
        norm = str(it.get(sku_key) or it.get("normalized_model") or it.get("sku") or "").strip()
        if not norm:
            continue
        by_norm[norm] = it
        if hasattr(stock_analyzer, "strip_brand_from_sku"):
            nb = stock_analyzer.strip_brand_from_sku(norm)
            if nb and nb not in by_nobrand:
                by_nobrand[nb] = it
        base = re.sub(r'(?:0\d|ES|SP|EU|IB)$', '', norm)
        if base and len(base) >= 5 and base not in by_base:
            by_base[base] = it
        num = _extract_numeric_signature(norm)
        if num:
            by_numeric[num].append((norm, it))

    return by_norm, by_nobrand, by_base, by_numeric


def _match_sku_to_catalog(
    sku_norm: str,
    catalog_by_norm: Dict[str, Any],
    catalog_by_nobrand: Dict[str, Any],
    catalog_by_base: Dict[str, Any],
    catalog_by_numeric: Dict[str, List[Tuple[str, Any]]],
    fuzzy_threshold: float = 0.78
) -> Tuple[Optional[Any], str, float]:
    """Busca un SKU en un catálogo usando coincidencia O(1) exacta, sin marca, base o fuzzy guiada."""
    if not sku_norm:
        return None, "NONE", 0.0

    if sku_norm in catalog_by_norm:
        return catalog_by_norm[sku_norm], "EXACTO", 1.0

    nb = stock_analyzer.strip_brand_from_sku(sku_norm) if hasattr(stock_analyzer, "strip_brand_from_sku") else sku_norm
    if nb and nb in catalog_by_norm:
        return catalog_by_norm[nb], "EXACTO", 1.0
    if sku_norm in catalog_by_nobrand:
        return catalog_by_nobrand[sku_norm], "EXACTO", 1.0
    if nb and nb in catalog_by_nobrand:
        return catalog_by_nobrand[nb], "EXACTO", 1.0

    base = re.sub(r'(?:0\d|ES|SP|EU|IB)$', '', sku_norm)
    if base and len(base) >= 5 and base in catalog_by_base:
        return catalog_by_base[base], "EXACTO", 0.98
    if nb:
        nb_base = re.sub(r'(?:0\d|ES|SP|EU|IB)$', '', nb)
        if nb_base and len(nb_base) >= 5 and nb_base in catalog_by_base:
            return catalog_by_base[nb_base], "EXACTO", 0.98

    num_s = _extract_numeric_signature(sku_norm)
    cands = catalog_by_numeric.get(num_s, []) if num_s else []
    best_cand = None
    best_score = 0.0
    best_type = "NONE"
    for c_norm, c_item in cands:
        score, mtype = _compute_sku_similarity(sku_norm, c_norm)
        if score >= fuzzy_threshold and score > best_score:
            best_score = score
            best_cand = c_item
            best_type = mtype

    if best_cand is not None:
        return best_cand, best_type, best_score

    return None, "NONE", 0.0


def run_multi_agent_cross_reference(
    tariff_session_id: Optional[str] = None,
    stock_session_id: Optional[str] = None,
    order_session_id: Optional[str] = None,
    sales_session_id: Optional[str] = None,
    sales_period_days: Optional[int] = 30,
    target_coverage_days: Optional[int] = 30,
    fallback_stock_items: Optional[List[Dict[str, Any]]] = None,
    fuzzy_threshold: float = 0.78,
    low_stock_threshold: int = 2,
    gemini_api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Motor de Coordinación Multi-Agente y Matching Desacoplado.
    Permite cruzar CUALQUIER combinación de 2, 3 o los 4 documentos disponibles:
    1. Tarifa de Proveedor (Excel / CSV)
    2. Stock Interno (PDF / Inventario ERP)
    3. Hoja de Pedido ERP (PDF)
    4. Informe de Ventas y Rotación (PDF ERP)
    """
    # 1. Obtener contexto de Tarifa (si se ha cargado)
    tariff_items: List[Dict[str, Any]] = []
    t_sess: Dict[str, Any] = {}
    price_col_name = "Precio"
    model_col_name = "Modelo"
    if tariff_session_id and tariff_session_id in _TARIFF_SESSIONS:
        t_sess = _TARIFF_SESSIONS[tariff_session_id]
        tariff_items = t_sess.get("extracted_items") or []
        if not tariff_items and "mapping" in t_sess:
            mapping = t_sess["mapping"]
            extract_tariff_with_mapping(
                session_id=tariff_session_id,
                model_col=mapping["model_col"],
                price_col=mapping["price_col"],
                desc_col=mapping.get("desc_col", -1),
                brand_col=mapping.get("brand_col", -1)
            )
            tariff_items = t_sess.get("extracted_items") or []
        cols = t_sess.get("columns", [])
        mapping = t_sess.get("mapping", {})
        if cols and "price_col" in mapping and 0 <= mapping["price_col"] < len(cols):
            price_col_name = cols[mapping["price_col"]]["name"]
        if cols and "model_col" in mapping and 0 <= mapping["model_col"] < len(cols):
            model_col_name = cols[mapping["model_col"]]["name"]

    # 2. Obtener contexto de Stock (si se ha cargado)
    stock_items: List[Dict[str, Any]] = []
    stock_filename = ""
    if stock_session_id and stock_session_id in _STOCK_SESSIONS:
        s_sess = _STOCK_SESSIONS[stock_session_id]
        stock_items = s_sess["items"]
        stock_filename = s_sess["filename"]
    elif fallback_stock_items:
        temp_res = create_stock_pdf_session(None, "inventory.json (Almacén Local)", fallback_stock_items)
        stock_items = _STOCK_SESSIONS[temp_res["stock_session_id"]]["items"]
        stock_filename = "inventory.json (Almacén Local)"

    # 3. Obtener contexto de Pedido ERP (si se ha cargado)
    order_items: List[Dict[str, Any]] = []
    order_filename = ""
    if order_session_id and order_session_id in _ORDER_SESSIONS:
        o_sess = _ORDER_SESSIONS[order_session_id]
        order_items = o_sess["items"]
        order_filename = o_sess["filename"]

    # 4. Obtener contexto de Ventas y Rotación (si se ha cargado)
    sales_items: List[Dict[str, Any]] = []
    sales_filename = ""
    effective_period_days = int(sales_period_days or 30)
    effective_target_coverage = int(target_coverage_days or 30)
    if sales_session_id and sales_session_id in _SALES_SESSIONS:
        sal_sess = _SALES_SESSIONS[sales_session_id]
        sales_items = sal_sess["items"]
        sales_filename = sal_sess["filename"]
        effective_period_days = sal_sess.get("period_days", effective_period_days)

    # Validar regla de oro: al menos 2 fuentes activas
    active_sources = []
    if tariff_items:
        active_sources.append("tariff")
        for it in tariff_items:
            if "normalized_model" not in it:
                it["normalized_model"] = stock_analyzer.normalize_sku(it.get("model", ""))
    if stock_items:
        active_sources.append("stock")
        for it in stock_items:
            if "normalized_sku" not in it:
                it["normalized_sku"] = stock_analyzer.normalize_sku(it.get("sku", ""))
    if order_items:
        active_sources.append("order")
        for it in order_items:
            if "normalized_sku" not in it:
                it["normalized_sku"] = stock_analyzer.normalize_sku(it.get("sku", ""))
    if sales_items:
        active_sources.append("sales")
        for it in sales_items:
            if "normalized_sku" not in it:
                it["normalized_sku"] = stock_analyzer.normalize_sku(it.get("sku", ""))

    if len(active_sources) < 2:
        raise ValueError(
            f"Debes cargar al menos 2 fuentes de datos (Tarifa, Stock, Pedido o Ventas) para ejecutar el cruce comparativo. "
            f"Actualmente solo hay {len(active_sources)} activa(s)."
        )

    # Construir índices O(1) para las fuentes activas
    stock_by_norm, stock_by_nobrand, stock_by_base, stock_by_numeric = _build_lookup_indices(stock_items, "normalized_sku")
    tariff_by_norm, tariff_by_nobrand, tariff_by_base, tariff_by_numeric = _build_lookup_indices(tariff_items, "normalized_model")
    order_by_norm, order_by_nobrand, order_by_base, order_by_numeric = _build_lookup_indices(order_items, "normalized_sku")
    sales_by_norm, sales_by_nobrand, sales_by_base, sales_by_numeric = _build_lookup_indices(sales_items, "normalized_sku")

    matched_stock_norms = set()
    matched_items: List[Dict[str, Any]] = []
    missing_items: List[Dict[str, Any]] = []
    stock_only_items: List[Dict[str, Any]] = []
    exact_matches_count = 0
    fuzzy_matches_count = 0

    if tariff_items and stock_items:
        for t_item in tariff_items:
            t_norm = t_item["normalized_model"]
            t_model = t_item["model"]
            t_price = float(t_item["price"])
            t_desc = t_item["description"]
            t_cat = t_item.get("category") or "Otros"
            t_brand = t_item.get("brand") or "General"

            matched_s, match_type, match_score = _match_sku_to_catalog(
                t_norm, stock_by_norm, stock_by_nobrand, stock_by_base, stock_by_numeric, fuzzy_threshold
            )

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
                    "category": (matched_s.get("category") if matched_s.get("category") and matched_s.get("category") not in ("Otros", "N/D", "") else (t_cat if t_cat and t_cat != "Otros" else "Otros")),
                    "description": t_desc if len(t_desc) >= len(matched_s.get("description", "")) else matched_s.get("description", t_desc),
                    "tariff_price": t_price,
                    "stock_cost": s_cost,
                    "stock_unit_cost": s_cost,
                    "stock_total_cost": round(s_cost * s_qty, 2),
                    "price_diff": price_diff,
                    "price_diff_pct": price_diff_pct,
                    "stock_qty": s_qty,
                    "status": status,
                    "suggested_order_qty": suggested_order
                })

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

        matched_items.sort(key=lambda x: (x["stock_qty"], -x["tariff_price"]))
        missing_items.sort(key=lambda x: (0 if "0 uds" in x["reason"] else 1, x["tariff_price"]))
        stock_only_items.sort(key=lambda x: -x["stock_qty"])
    elif stock_items and not tariff_items:
        for s_norm, s_item in stock_by_norm.items():
            stock_only_items.append({
                "stock_model": s_item["sku"],
                "brand": s_item.get("brand", "Genérico"),
                "category": s_item.get("category", "Otros"),
                "description": s_item.get("description", ""),
                "stock_qty": int(s_item.get("stock", 0)),
                "stock_cost": float(s_item.get("cost", 0.0))
            })

    # -------------------------------------------------------------------------
    # AUDITORÍA DE HOJA DE PEDIDO ERP vs TARIFA, STOCK Y VENTAS (MÓDULO 3)
    # -------------------------------------------------------------------------
    order_audit_items: List[Dict[str, Any]] = []
    order_matched_count = 0
    order_discrepancies_count = 0
    order_overprice_count = 0
    order_gross_overprice_amount = 0.0
    order_expected_tariff_total = 0.0

    if order_items:
        for o_item in order_items:
            o_norm = o_item["normalized_sku"]
            o_sku = o_item["sku"]
            o_qty = int(o_item.get("order_qty", 1))
            o_unit_price = float(o_item.get("order_unit_price", 0.0))
            o_total_price = round(o_unit_price * o_qty, 2)
            o_desc = o_item.get("description", "")
            o_brand = o_item.get("brand", "General")
            o_cat = o_item.get("category", "Otros")

            matched_t, o_match_type, o_match_score = _match_sku_to_catalog(
                o_norm, tariff_by_norm, tariff_by_nobrand, tariff_by_base, tariff_by_numeric, fuzzy_threshold
            )

            matched_s, _, _ = _match_sku_to_catalog(
                o_norm, stock_by_norm, stock_by_nobrand, stock_by_base, stock_by_numeric, fuzzy_threshold
            )
            current_stock_qty = int(matched_s["stock"]) if matched_s else None

            matched_sal, _, _ = _match_sku_to_catalog(
                o_norm, sales_by_norm, sales_by_nobrand, sales_by_base, sales_by_numeric, fuzzy_threshold
            )
            sal_monthly_run = float(matched_sal["monthly_run_rate"]) if matched_sal else None

            if matched_t is not None:
                order_matched_count += 1
                t_price_val = float(matched_t["price"])
                unit_diff = round(o_unit_price - t_price_val, 2)
                total_diff = round(unit_diff * o_qty, 2)
                diff_pct = round((unit_diff / t_price_val) * 100, 1) if t_price_val > 0 else 0.0
                order_expected_tariff_total += round(t_price_val * o_qty, 2)

                if abs(unit_diff) <= 0.05:
                    audit_status = "PRECIO_OK"
                elif unit_diff > 0.05:
                    audit_status = "MAS_CARO_EN_PEDIDO"
                    order_discrepancies_count += 1
                    order_overprice_count += 1
                    order_gross_overprice_amount += total_diff
                else:
                    audit_status = "MAS_BARATO_EN_PEDIDO"
                    order_discrepancies_count += 1

                final_cat = o_cat if o_cat not in ("Otros", "N/D", "") else matched_t.get("category", "Otros")
                final_desc = o_desc if len(o_desc) >= len(matched_t.get("description", "")) else matched_t.get("description", o_desc)
                t_model_str = matched_t["model"]
            else:
                t_price_val = 0.0
                unit_diff = 0.0
                total_diff = 0.0
                diff_pct = 0.0
                audit_status = "NO_EN_TARIFA"
                final_cat = o_cat
                final_desc = o_desc
                t_model_str = "No figura en tarifa" if tariff_items else "Sin tarifa cargada"

            order_audit_items.append({
                "order_model": o_sku,
                "tariff_model": t_model_str,
                "match_type": o_match_type,
                "match_score": round(o_match_score * 100, 1),
                "brand": o_brand,
                "category": final_cat,
                "description": final_desc,
                "order_qty": o_qty,
                "stock_qty": current_stock_qty,
                "monthly_run_rate": sal_monthly_run,
                "order_unit_price": o_unit_price,
                "order_total_price": o_total_price,
                "tariff_price": t_price_val,
                "unit_diff": unit_diff,
                "total_diff": total_diff,
                "diff_pct": diff_pct,
                "audit_status": audit_status,
                "has_off_invoice": False,
                "off_invoice_unit": 0.0
            })

        def _order_audit_sort_key(x: Dict[str, Any]):
            st = x["audit_status"]
            if st == "MAS_CARO_EN_PEDIDO":
                return (0, -x["total_diff"])
            if st == "MAS_BARATO_EN_PEDIDO":
                return (1, x["total_diff"])
            if st == "NO_EN_TARIFA":
                return (2, -x["order_total_price"])
            return (3, -x["order_total_price"])

        order_audit_items.sort(key=_order_audit_sort_key)

    # -------------------------------------------------------------------------
    # ANÁLISIS DE VENTAS, ROTACIÓN Y COBERTURA DE PEDIDO (MÓDULO 4)
    # -------------------------------------------------------------------------
    sales_rotation_items: List[Dict[str, Any]] = []
    sales_insufficient_count = 0
    sales_imminent_stockout_count = 0
    sales_overorder_count = 0
    processed_sales_norms = set()

    if sales_items:
        for sal_it in sales_items:
            sn = sal_it["normalized_sku"]
            processed_sales_norms.add(sn)
            u_sold = sal_it["units_sold"]
            d_rate = sal_it["daily_sales_rate"]
            m_rate = sal_it["monthly_run_rate"]

            st_cand, _, _ = _match_sku_to_catalog(sn, stock_by_norm, stock_by_nobrand, stock_by_base, stock_by_numeric, fuzzy_threshold)
            curr_stock = int(st_cand["stock"]) if st_cand else 0

            ord_cand, _, _ = _match_sku_to_catalog(sn, order_by_norm, order_by_nobrand, order_by_base, order_by_numeric, fuzzy_threshold)
            ord_qty = int(ord_cand["order_qty"]) if ord_cand else 0
            ord_unit_price = float(ord_cand["order_unit_price"]) if ord_cand else 0.0

            tar_cand, _, _ = _match_sku_to_catalog(sn, tariff_by_norm, tariff_by_nobrand, tariff_by_base, tariff_by_numeric, fuzzy_threshold)
            tar_price = float(tar_cand["price"]) if tar_cand else 0.0

            curr_days = round(curr_stock / d_rate, 1) if d_rate > 0 else 999.0
            proj_days = round((curr_stock + ord_qty) / d_rate, 1) if d_rate > 0 else 999.0

            target_units = int(math.ceil(effective_target_coverage * d_rate)) if d_rate > 0 else 0
            shortage_units = max(0, target_units - (curr_stock + ord_qty))
            surplus_units = max(0, (curr_stock + ord_qty) - int(math.ceil(60 * d_rate))) if d_rate > 0 else 0

            if ord_qty > 0 and proj_days < 20 and d_rate > 0:
                diag_status = "PEDIDO_INSUFICIENTE"
                diag_badge = "🔴 Pedido Insuficiente"
                diag_text = (
                    f"Cubre solo {proj_days:.0f} días de demanda (ritmo {m_rate:.0f} uds/mes). "
                    f"Faltan ~{shortage_units} uds para cubrir {effective_target_coverage} días."
                )
                sales_insufficient_count += 1
            elif ord_qty > 0 and proj_days > 90 and d_rate > 0:
                diag_status = "SOBREPEDIDO"
                diag_badge = "🟡 Sobrepedido (>90d)"
                diag_text = (
                    f"Stock + Pedido cubren {proj_days:.0f} días de venta "
                    f"(exceso de ~{surplus_units} uds sobre cobertura de 60 días)."
                )
                sales_overorder_count += 1
            elif ord_qty > 0:
                diag_status = "COBERTURA_OPTIMA"
                diag_badge = "🟢 Cobertura Óptima"
                diag_text = f"Cubre {proj_days:.0f} días de venta ({curr_stock} en stock + {ord_qty} pedidas)."
            elif ord_qty == 0 and curr_stock > 0 and curr_days < 15 and d_rate > 0:
                diag_status = "ROTURA_INMINENTE"
                diag_badge = "⚠️ Rotura Inminente"
                diag_text = f"Quedan solo {curr_stock} uds en almacén ({curr_days:.0f} días de cobertura) y NO está en el pedido."
                sales_imminent_stockout_count += 1
            elif ord_qty == 0 and curr_stock > 0:
                diag_status = "STOCK_DISPONIBLE"
                diag_badge = "⚪ Stock Disponible"
                diag_text = f"Stock en almacén cubre {curr_days:.0f} días de venta."
            elif ord_qty == 0 and curr_stock <= 0 and d_rate > 0:
                diag_status = "ROTURA_TOTAL_SIN_PEDIDO"
                diag_badge = "🔴 Sin Stock ni Pedido"
                diag_text = f"0 uds en almacén y NO se ha pedido. Ritmo de {m_rate:.0f} uds/mes."
                sales_imminent_stockout_count += 1
            else:
                diag_status = "SIN_VENTAS_PREVIAS"
                diag_badge = "⚪ Sin Rotación"
                diag_text = f"Sin rotación en el periodo analizado ({effective_period_days} días)."

            sales_rotation_items.append({
                "sku": sal_it["sku"],
                "description": sal_it["description"],
                "brand": sal_it["brand"],
                "category": sal_it["category"],
                "units_sold": u_sold,
                "units_sold_in_period": u_sold,
                "period_days": effective_period_days,
                "daily_sales_rate": d_rate,
                "monthly_run_rate": m_rate,
                "stock_qty": curr_stock,
                "current_stock": curr_stock,
                "current_stock_days": curr_days,
                "stock_coverage_days": round(curr_days, 1) if curr_days < 900 else None,
                "order_qty": ord_qty,
                "ordered_units": ord_qty,
                "projected_stock_days": proj_days,
                "projected_coverage_days": round(proj_days, 1) if proj_days < 900 else None,
                "target_coverage_days": effective_target_coverage,
                "shortage_units": shortage_units,
                "shortage_units_for_target": shortage_units,
                "surplus_units": surplus_units,
                "excess_surplus_units": surplus_units,
                "tariff_price": tar_price,
                "order_unit_price": ord_unit_price,
                "diag_status": diag_status,
                "diagnostic": diag_status,
                "diag_badge": diag_badge,
                "diag_text": diag_text
            })

        if order_items:
            for o_it in order_items:
                on = o_it["normalized_sku"]
                s_cand, _, _ = _match_sku_to_catalog(on, sales_by_norm, sales_by_nobrand, sales_by_base, sales_by_numeric, fuzzy_threshold)
                if not s_cand and on not in processed_sales_norms:
                    st_cand, _, _ = _match_sku_to_catalog(on, stock_by_norm, stock_by_nobrand, stock_by_base, stock_by_numeric, fuzzy_threshold)
                    curr_s = int(st_cand["stock"]) if st_cand else 0
                    tar_cand, _, _ = _match_sku_to_catalog(on, tariff_by_norm, tariff_by_nobrand, tariff_by_base, tariff_by_numeric, fuzzy_threshold)
                    tar_p = float(tar_cand["price"]) if tar_cand else 0.0

                    sales_rotation_items.append({
                        "sku": o_it["sku"],
                        "description": o_it["description"],
                        "brand": o_it["brand"],
                        "category": o_it["category"],
                        "units_sold": 0,
                        "units_sold_in_period": 0,
                        "period_days": effective_period_days,
                        "daily_sales_rate": 0.0,
                        "monthly_run_rate": 0.0,
                        "stock_qty": curr_s,
                        "current_stock": curr_s,
                        "current_stock_days": 999.0,
                        "stock_coverage_days": None,
                        "order_qty": o_it["order_qty"],
                        "ordered_units": o_it["order_qty"],
                        "projected_stock_days": 999.0,
                        "projected_coverage_days": None,
                        "target_coverage_days": effective_target_coverage,
                        "shortage_units": 0,
                        "shortage_units_for_target": 0,
                        "surplus_units": 0,
                        "excess_surplus_units": 0,
                        "tariff_price": tar_p,
                        "order_unit_price": o_it["order_unit_price"],
                        "diag_status": "PEDIDO_SIN_VENTAS",
                        "diagnostic": "PEDIDO_SIN_VENTAS",
                        "diag_badge": "ℹ️ Pedido sin Venta Registrada",
                        "diag_text": f"En pedido ({o_it['order_qty']} uds) pero sin ventas en los últimos {effective_period_days} días. Comprobar si es novedad."
                    })

        def _sales_rotation_sort_key(x: Dict[str, Any]):
            st = x["diag_status"]
            if st in ("PEDIDO_INSUFICIENTE", "ROTURA_TOTAL_SIN_PEDIDO"):
                return (0, -x["shortage_units"], -x["monthly_run_rate"])
            if st == "ROTURA_INMINENTE":
                return (1, x["current_stock_days"], -x["monthly_run_rate"])
            if st == "SOBREPEDIDO":
                return (2, -x["surplus_units"])
            if st == "COBERTURA_OPTIMA":
                return (3, -x["monthly_run_rate"])
            return (4, -x["units_sold"])

        sales_rotation_items.sort(key=_sales_rotation_sort_key)

    # Si hay clave de Gemini y quedan modelos con categoría 'Otros', resolverlos en un único lote ultrarrápido
    if gemini_api_key:
        unknown_skus = []
        for it in matched_items:
            if it.get("category") in ("Otros", "N/D", "", None):
                unknown_skus.append(it["tariff_model"])
        for it in missing_items:
            if it.get("category") in ("Otros", "N/D", "", None):
                unknown_skus.append(it["tariff_model"])
        for it in order_audit_items:
            if it.get("category") in ("Otros", "N/D", "", None):
                unknown_skus.append(it["order_model"])
        for it in sales_rotation_items:
            if it.get("category") in ("Otros", "N/D", "", None):
                unknown_skus.append(it["sku"])
        unique_unknown = list(dict.fromkeys([m for m in unknown_skus if m and len(m) >= 2]))
        if unique_unknown:
            try:
                import app
                resolved_map = app.resolve_unknown_models_with_gemini(
                    unique_unknown[:50],
                    brand=t_sess.get("provider_name", "General"),
                    api_key=gemini_api_key
                )
                if resolved_map:
                    for it in matched_items:
                        m_key = it["tariff_model"]
                        if m_key in resolved_map:
                            it["category"] = resolved_map[m_key]
                    for it in missing_items:
                        m_key = it["tariff_model"]
                        if m_key in resolved_map:
                            it["category"] = resolved_map[m_key]
                    for it in order_audit_items:
                        m_key = it["order_model"]
                        if m_key in resolved_map:
                            it["category"] = resolved_map[m_key]
                    for it in sales_rotation_items:
                        m_key = it["sku"]
                        if m_key in resolved_map:
                            it["category"] = resolved_map[m_key]
            except Exception as e_ai:
                logger.debug(f"Error resolviendo modelos desconocidos con IA en lote: {e_ai}")

    # Construir transcripción de comunicación Multi-Agente
    dialogue = []

    if tariff_items:
        dialogue.append({
            "agent": "tariff",
            "agent_name": "Agente de Tarifas (Proveedor)",
            "badge": f"Tarifa: {t_sess.get('filename', 'Tarifa')}",
            "time": _now_time(),
            "text": (
                f"Envío al coordinador **{len(tariff_items)} modelos** extraídos de `{t_sess.get('filename', 'Tarifa')}` "
                f"(Hoja `{t_sess.get('active_sheet', 'Activa')}`). Columna de referencia: **{model_col_name}** | "
                f"Columna de precio seleccionada por el usuario: **{price_col_name}**."
            )
        })

    if stock_items:
        dialogue.append({
            "agent": "stock",
            "agent_name": "Agente de Stock (Almacén PDF)",
            "badge": f"Stock: {stock_filename}",
            "time": _now_time(),
            "text": (
                f"Envío inventario extraído de `{stock_filename}` con **{len(stock_items)} referencias** "
                f"y **{sum(it.get('stock', 0) for it in stock_items)} unidades** totales en almacén."
            )
        })

    if order_items:
        dialogue.append({
            "agent": "order",
            "agent_name": "Agente Auditor de Pedido (PDF ERP)",
            "badge": f"Pedido: {order_filename}",
            "time": _now_time(),
            "text": (
                f"He procesado las **{len(order_items)} líneas** de la Hoja de Pedido `{order_filename}`:\n"
                + (
                    f"• **{order_matched_count} localizados en tarifa** ({order_overprice_count} con precio superior, "
                    f"variación bruta: **+{order_gross_overprice_amount:,.2f} €** — revisa si corresponden a *Fuera de Factura*).\n"
                    if tariff_items else ""
                )
                + f"• Importe total pedido: **{sum(it['order_total_price'] for it in order_items):,.2f} €** ({sum(it['order_qty'] for it in order_items)} uds)."
            )
        })

    if sales_items:
        dialogue.append({
            "agent": "sales",
            "agent_name": "Agente de Ventas y Rotación (PDF ERP)",
            "badge": f"Ventas ({effective_period_days} días): {sales_filename}",
            "time": _now_time(),
            "text": (
                f"He analizado el histórico de ventas de **{effective_period_days} días**:\n"
                f"• **{len(sales_items)} referencias vendidas** ({sum(it['units_sold'] for it in sales_items)} uds totales, "
                f"ritmo de **{sum(it['units_sold'] for it in sales_items)/effective_period_days:.1f} uds/día**).\n"
                + (
                    f"• ⚠️ **{sales_insufficient_count} artículos del pedido son INSUFICIENTES** para cubrir la rotación mensual (riesgo de rotura en <20 días).\n"
                    if order_items else ""
                )
                + (
                    f"• 🚨 **{sales_imminent_stockout_count} referencias en almacén con rotura inminente** (<15 días de existencias) que conviene reponer."
                    if stock_items and not order_items else ""
                )
            )
        })

    # Mensaje resumen del Coordinador
    coord_lines = [f"Cruce coordinado entre **{len(active_sources)} fuentes activas**:"]
    if tariff_items and stock_items:
        coord_lines.append(f"• **Tarifa ↔ Stock:** {len(matched_items)} coincidentes ({exact_matches_count} exactos, {fuzzy_matches_count} fuzzy), {len(missing_items)} faltantes.")
    if order_items and tariff_items:
        coord_lines.append(f"• **Pedido ERP ↔ Tarifa:** {order_matched_count}/{len(order_items)} auditados, **{order_discrepancies_count} diferencias de precio**.")
    if sales_items and order_items:
        coord_lines.append(f"• **Ventas ↔ Pedido ERP:** {sales_insufficient_count} pedidos insuficientes vs rotación real.")
    if sales_items and stock_items and not order_items:
        coord_lines.append(f"• **Ventas ↔ Stock:** {sales_imminent_stockout_count} referencias en riesgo inminente de rotura.")

    dialogue.append({
        "agent": "coordinator",
        "agent_name": "Agente Coordinador Multi-Agente",
        "badge": f"Cruce {len(active_sources)} Fuentes",
        "time": _now_time(),
        "text": "\n".join(coord_lines)
    })

    # Dictamen Gemini si hay API key
    if gemini_api_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_api_key, http_options={"timeout": 6.0})
            summary_facts = [f"- Fuentes cruzadas: {', '.join(active_sources)}"]
            if tariff_items:
                summary_facts.append(f"- Tarifa: {len(tariff_items)} modelos.")
            if stock_items:
                summary_facts.append(f"- Stock: {len(stock_items)} referencias.")
            if order_items:
                summary_facts.append(f"- Pedido ERP: {len(order_items)} líneas, {order_overprice_count} con sobrecoste vs tarifa (+{order_gross_overprice_amount:.2f}€).")
            if sales_items:
                summary_facts.append(f"- Ventas ({effective_period_days}d): {sales_insufficient_count} pedidos insuficientes, {sales_imminent_stockout_count} en riesgo rotura.")

            prompt = (
                f"Eres el Agente Estratega de Compras y Aprovisionamiento. Resume en 3 frases breves y directas las conclusiones clave y qué acciones debe tomar el comprador:\n"
                + "\n".join(summary_facts)
            )
            for m_name in ["gemini-3.5-flash", "gemini-3.5-flash-lite"]:
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

    order_total_units = sum(it["order_qty"] for it in order_audit_items)
    order_total_amount = round(sum(it["order_total_price"] for it in order_audit_items), 2)
    sales_total_units = sum(it["units_sold"] for it in sales_rotation_items)

    kpis = {
        "active_sources": active_sources,
        "active_modules_count": len(active_sources),
        "total_tariff_items": len(tariff_items),
        "total_stock_items": len(stock_items),
        "matched_count": len(matched_items),
        "exact_matches_count": exact_matches_count,
        "fuzzy_matches_count": fuzzy_matches_count,
        "matched_with_stock_count": sum(1 for m in matched_items if m.get("stock_qty", 0) > 0),
        "missing_in_stock_count": len(missing_items),
        "stock_only_count": len(stock_only_items),
        "price_col_name": price_col_name,
        "model_col_name": model_col_name,
        "order_lines_count": len(order_audit_items),
        "order_matched_count": order_matched_count,
        "order_total_units": order_total_units,
        "order_total_amount": order_total_amount,
        "order_expected_tariff_total": round(order_expected_tariff_total, 2),
        "order_discrepancies_count": order_discrepancies_count,
        "order_overprice_count": order_overprice_count,
        "order_gross_overprice_amount": round(order_gross_overprice_amount, 2),
        "sales_items_count": len(sales_rotation_items),
        "sales_total_units": sales_total_units,
        "sales_period_days": effective_period_days,
        "target_coverage_days": effective_target_coverage,
        "sales_daily_run_rate": round(sales_total_units / max(1, effective_period_days), 2),
        "sales_monthly_run_rate": round((sales_total_units / max(1, effective_period_days)) * 30.0, 1),
        "sales_insufficient_order_count": sales_insufficient_count,
        "sales_imminent_stockout_count": sales_imminent_stockout_count,
        "sales_overorder_count": sales_overorder_count
    }

    result_payload = {
        "status": "success",
        "active_sources": active_sources,
        "active_modules_count": len(active_sources),
        "kpis": kpis,
        "dialogue": dialogue,
        "matched_items": matched_items,
        "missing_items": missing_items,
        "stock_only_items": stock_only_items,
        "order_audit_items": order_audit_items,
        "sales_rotation_items": sales_rotation_items
    }

    global _LAST_CROSS_RESULT
    _LAST_CROSS_RESULT = result_payload
    return result_payload


def export_cross_reference_excel(cross_result: Optional[Dict[str, Any]] = None) -> io.BytesIO:
    """Genera un archivo Excel (.xlsx) con las pestañas de los módulos activos (Tarifa, Stock, Pedido y Ventas)."""
    data = cross_result or _LAST_CROSS_RESULT
    if not data or not data.get("kpis"):
        raise ValueError("No hay ningún cruce Multi-Agente calculado para exportar.")

    wb = Workbook()
    default_ws = wb.active

    header_font = Font(color="FFFFFF", bold=True, size=11)
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )
    sheets_to_format = []
    created_sheets = 0

    matched_items = data.get("matched_items") or []
    missing_items = data.get("missing_items") or []
    stock_only = data.get("stock_only_items") or []
    order_audit = data.get("order_audit_items") or []
    sales_rotation = data.get("sales_rotation_items") or []

    # Hoja 1: Artículos Coincidentes Tarifa/Stock
    if matched_items:
        ws1 = default_ws if created_sheets == 0 else wb.create_sheet(title="1_Coincidentes_Tarifa_Stock")
        ws1.title = "1_Coincidentes_Tarifa_Stock"
        created_sheets += 1
        sheets_to_format.append(ws1)
        headers1 = [
            "Modelo (Tarifa)", "Modelo (PDF Stock)", "Tipo Match", "Similitud (%)",
            "Marca", "Categoría", "Descripción", "Precio Tarifa (€)",
            "Coste ERP (€)", "Diferencia (€)", "Stock Actual (Uds)", "Estado", "Uds Sugeridas"
        ]
        ws1.append(headers1)
        for col_num in range(1, len(headers1) + 1):
            c = ws1.cell(row=1, column=col_num)
            c.fill = PatternFill(start_color="1E1B4B", end_color="1E1B4B", fill_type="solid")
            c.font = header_font
            c.alignment = Alignment(horizontal="center", vertical="center")

        for item in matched_items:
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

    # Hoja 2: Faltantes en Tarifa
    if missing_items:
        ws2 = default_ws if created_sheets == 0 else wb.create_sheet(title="2_Faltantes_En_Tarifa")
        ws2.title = "2_Faltantes_En_Tarifa"
        created_sheets += 1
        sheets_to_format.append(ws2)
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

        for item in missing_items:
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

    # Hoja 3: Solo en PDF de Stock
    if stock_only:
        ws3 = default_ws if created_sheets == 0 else wb.create_sheet(title="3_Solo_En_PDF_Stock")
        ws3.title = "3_Solo_En_PDF_Stock"
        created_sheets += 1
        sheets_to_format.append(ws3)
        headers3 = ["Modelo (PDF Stock)", "Marca", "Categoría", "Descripción", "Stock en Almacén (Uds)", "Coste Unitario ERP (€)"]
        ws3.append(headers3)
        for col_num in range(1, len(headers3) + 1):
            c = ws3.cell(row=1, column=col_num)
            c.fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
            c.font = header_font
            c.alignment = Alignment(horizontal="center", vertical="center")

        for item in stock_only:
            ws3.append([
                item.get("stock_model", ""),
                item.get("brand", ""),
                item.get("category", ""),
                item.get("description", ""),
                item.get("stock_qty", 0),
                item.get("stock_cost", 0.0)
            ])

    # Hoja 4: Auditoría de Pedido ERP vs Tarifa (con Fuera de Factura)
    if order_audit:
        ws4 = default_ws if created_sheets == 0 else wb.create_sheet(title="4_Auditoria_Pedido_ERP")
        ws4.title = "4_Auditoria_Pedido_ERP"
        created_sheets += 1
        sheets_to_format.append(ws4)
        headers4 = [
            "Modelo (Pedido ERP)", "Modelo (Tarifa)", "Marca", "Categoría", "Descripción",
            "Uds Pedidas", "Stock Actual", "Precio Unit. Pedido (€)", "Precio Unit. Tarifa (€)",
            "Dif. Unitaria Bruta (€)", "¿Lleva Fuera de Factura?", "Fuera de Factura Unit. (€)",
            "Total Fuera de Factura Línea (€)", "Precio Neto Real Unit. (€)", "Dif. Neta Final Unit. (€)", "Estado Auditoría"
        ]
        ws4.append(headers4)
        for col_num in range(1, len(headers4) + 1):
            c = ws4.cell(row=1, column=col_num)
            c.fill = PatternFill(start_color="9A3412", end_color="9A3412", fill_type="solid")
            c.font = header_font
            c.alignment = Alignment(horizontal="center", vertical="center")

        for item in order_audit:
            o_qty = int(item.get("order_qty", 1))
            o_unit = float(item.get("order_unit_price", 0.0))
            t_unit = float(item.get("tariff_price", 0.0))
            u_diff = round(o_unit - t_unit, 2) if t_unit > 0 else 0.0
            has_ff = bool(item.get("has_off_invoice", False))
            ff_unit = float(item.get("off_invoice_unit", 0.0)) if has_ff else 0.0
            ff_total = round(ff_unit * o_qty, 2)
            net_real = round(o_unit - ff_unit, 2)
            net_diff = round(net_real - t_unit, 2) if t_unit > 0 else 0.0
            st_label = item.get("audit_status", "")
            if has_ff and abs(net_diff) <= 0.05 and t_unit > 0:
                st_label = "CUADRA CON FUERA DE FACTURA"

            ws4.append([
                item.get("order_model", ""),
                item.get("tariff_model", ""),
                item.get("brand", ""),
                item.get("category", ""),
                item.get("description", ""),
                o_qty,
                item.get("stock_qty", "") if item.get("stock_qty") is not None else "—",
                o_unit,
                t_unit,
                u_diff,
                "SÍ" if has_ff else "NO",
                ff_unit,
                ff_total,
                net_real,
                net_diff,
                st_label
            ])

    # Hoja 5: Rotación de Ventas y Cobertura de Pedido
    if sales_rotation:
        ws5 = default_ws if created_sheets == 0 else wb.create_sheet(title="5_Rotacion_Ventas_Cobertura")
        ws5.title = "5_Rotacion_Ventas_Cobertura"
        created_sheets += 1
        sheets_to_format.append(ws5)
        headers5 = [
            "Modelo / SKU", "Marca", "Categoría", "Descripción",
            "Uds Vendidas en Periodo", "Días Periodo", "Venta Diaria (Uds/día)", "Rotación Mensual (Uds/mes)",
            "Stock Almacén (Uds)", "Cobertura Stock (Días)", "Uds en Pedido ERP", "Cobertura Proyectada (Días)",
            "Uds Faltantes p/ Objetivo", "Alerta / Diagnóstico", "Recomendación del Agente"
        ]
        ws5.append(headers5)
        for col_num in range(1, len(headers5) + 1):
            c = ws5.cell(row=1, column=col_num)
            c.fill = PatternFill(start_color="065F46", end_color="065F46", fill_type="solid")
            c.font = header_font
            c.alignment = Alignment(horizontal="center", vertical="center")

        for item in sales_rotation:
            ws5.append([
                item.get("sku", ""),
                item.get("brand", ""),
                item.get("category", ""),
                item.get("description", ""),
                item.get("units_sold", 0),
                item.get("period_days", 30),
                item.get("daily_sales_rate", 0.0),
                item.get("monthly_run_rate", 0.0),
                item.get("stock_qty", 0),
                item.get("current_stock_days", 0.0) if item.get("current_stock_days", 0.0) < 900 else "—",
                item.get("order_qty", 0),
                item.get("projected_stock_days", 0.0) if item.get("projected_stock_days", 0.0) < 900 else "—",
                item.get("shortage_units", 0),
                item.get("diag_badge", item.get("diag_status", "")),
                item.get("diag_text", "")
            ])

    if created_sheets == 0:
        default_ws.title = "Resumen"
        default_ws.append(["Sin datos suficientes para exportar"])
        sheets_to_format.append(default_ws)

    for ws in sheets_to_format:
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

