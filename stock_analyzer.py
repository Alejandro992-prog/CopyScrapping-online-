import os
import sys
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

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

def normalize_sku(sku: str) -> str:
    """Normaliza un SKU/Modelo eliminando espacios, guiones, barras y pasando a mayúsculas."""
    if not sku:
        return ""
    s = str(sku).upper().strip()
    s = re.sub(r'[\s\-/\._]', '', s)
    return s

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
    """Carga los artículos de una tarifa de proveedor desde data/extractions/."""
    extractions_dir = os.path.join(get_base_data_dir(), "extractions")
    
    # Buscar archivo exacto o por prefijo
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
            
            # Buscar columnas estándar o equivalentes
            model = str(row_dict.get("model") or row_dict.get("modelo") or row_dict.get("sku") or "").strip()
            product = str(row_dict.get("product") or row_dict.get("producto") or row_dict.get("descripcion") or "").strip()
            raw_price = row_dict.get("price") or row_dict.get("precio") or row_dict.get("precio_sin_iva") or row_dict.get("PVP") or 0
            
            # Limpiar precio a numérico
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
        return items
    except Exception as e:
        print(f"Error cargando tarifa {provider_filename_or_id}: {e}")
        return []

def compare_stock_vs_tariff(
    stock_items: List[Dict[str, Any]],
    tariff_items: List[Dict[str, Any]],
    brand_filter: Optional[str] = None,
    low_stock_threshold: int = 2
) -> Dict[str, Any]:
    """Cruza la tarifa de un proveedor contra el stock de almacén."""
    norm_brand_filter = brand_filter.strip().upper() if brand_filter and brand_filter.strip().upper() != "TODAS" else None
    
    # 1. Crear índice de búsqueda rápida en stock
    stock_by_sku: Dict[str, Dict[str, Any]] = {}
    stock_by_desc: List[Dict[str, Any]] = []
    
    for item in stock_items:
        b = str(item.get("brand", "")).strip().upper()
        if norm_brand_filter and norm_brand_filter not in b:
            continue
            
        sku_clean = normalize_sku(item.get("sku", ""))
        ean_clean = normalize_sku(item.get("ean", ""))
        
        if sku_clean:
            stock_by_sku[sku_clean] = item
        if ean_clean and ean_clean != "ND":
            stock_by_sku[ean_clean] = item
            
        stock_by_desc.append(item)

    matched_stock_skus = set()
    
    shortages = []   # Roturas totales (0 uds o ausentes en almacén)
    low_stock = []   # Stock crítico (1 a threshold uds)
    in_stock = []    # Stock saludable (> threshold uds)
    
    total_order_cost = 0.0

    # 2. Evaluar cada producto de la tarifa del proveedor
    for t_item in tariff_items:
        model = t_item.get("model", "")
        product = t_item.get("product", "")
        price = float(t_item.get("price", 0.0))
        
        # Filtro de marca en la tarifa si está especificado
        if norm_brand_filter:
            text_to_check = f"{model} {product}".upper()
            if norm_brand_filter not in text_to_check:
                continue

        norm_model = normalize_sku(model)
        matched = None
        
        if norm_model and norm_model in stock_by_sku:
            matched = stock_by_sku[norm_model]
        elif norm_model and len(norm_model) >= 5:
            # Búsqueda parcial si el modelo está contenido
            for s_sku, s_item in stock_by_sku.items():
                if norm_model in s_sku or s_sku in norm_model:
                    matched = s_item
                    break

        if not matched and product:
            # Búsqueda en descripción de stock
            for s_item in stock_by_desc:
                s_desc_norm = normalize_sku(s_item.get("description", ""))
                if norm_model and norm_model in s_desc_norm:
                    matched = s_item
                    break

        current_qty = 0
        stock_sku = model
        category = "N/D"
        description = product
        
        if matched:
            matched_stock_skus.add(normalize_sku(matched.get("sku", "")))
            try:
                current_qty = int(matched.get("stock", 0))
            except Exception:
                try:
                    current_qty = int(float(matched.get("stock", 0)))
                except Exception:
                    current_qty = 0
            category = matched.get("category") or "N/D"
            description = matched.get("description") or product
            stock_sku = matched.get("sku") or model

        entry = {
            "model": model,
            "sku": stock_sku,
            "product": description,
            "category": category,
            "stock": current_qty,
            "supplier_price": price,
            "attributes": t_item.get("attributes", ""),
            "matched_in_warehouse": matched is not None
        }

        if current_qty == 0:
            suggested_reorder = max(1, low_stock_threshold * 2)
            entry["suggested_reorder"] = suggested_reorder
            entry["reorder_cost"] = round(suggested_reorder * price, 2)
            total_order_cost += entry["reorder_cost"]
            shortages.append(entry)
        elif current_qty <= low_stock_threshold:
            suggested_reorder = max(1, (low_stock_threshold * 2) - current_qty)
            entry["suggested_reorder"] = suggested_reorder
            entry["reorder_cost"] = round(suggested_reorder * price, 2)
            total_order_cost += entry["reorder_cost"]
            low_stock.append(entry)
        else:
            entry["suggested_reorder"] = 0
            entry["reorder_cost"] = 0.0
            in_stock.append(entry)

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

    return {
        "brand": brand_filter or "Todas",
        "low_stock_threshold": low_stock_threshold,
        "kpis": {
            "total_tariff_items": len(shortages) + len(low_stock) + len(in_stock),
            "shortages_count": len(shortages),
            "low_stock_count": len(low_stock),
            "in_stock_count": len(in_stock),
            "surplus_count": len(surplus_items),
            "total_estimated_reorder_cost": round(total_order_cost, 2)
        },
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
    custom_model: str = "gemini-2.5-flash"
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

    try:
        response = client.models.generate_content(
            model=custom_model,
            contents=prompt,
        )
        return response.text or "No se obtuvo respuesta de Gemini."
    except Exception as e:
        # Intento de rescate con modelo estándar
        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
            )
            return response.text or "No se obtuvo respuesta de Gemini."
        except Exception as e2:
            return f"Error al generar informe con Gemini: {str(e)} | Fallback: {str(e2)}"

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
    
    headers1 = ["Modelo / SKU", "Descripción", "Categoría", "Stock Actual", "Pedido Sugerido", "Coste Tarifa (€)", "Total Línea (€)"]
    ws1.append(["AUDITORÍA DE FALTAS Y PROPUESTA DE PEDIDO"])
    ws1.merge_cells("A1:G1")
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
            it.get("product", ""),
            it.get("category", ""),
            it.get("stock", 0),
            it.get("suggested_reorder", 1),
            it.get("supplier_price", 0.0),
            it.get("reorder_cost", 0.0)
        ])
        ws1.row_dimensions[row_num].height = 20
        for c_idx in range(1, 8):
            cell = ws1.cell(row=row_num, column=c_idx)
            cell.border = thin_border
            if c_idx == 4: # Stock actual
                cell.fill = PatternFill(start_color=C_SHORTAGE, end_color=C_SHORTAGE, fill_type="solid")
                cell.font = Font(color=C_SHORTAGE_TXT, bold=True)
                cell.alignment = Alignment(horizontal="center")
            elif c_idx in [5, 6, 7]:
                cell.alignment = Alignment(horizontal="right")
                if c_idx in [6, 7]:
                    cell.number_format = '#,##0.00 €'
        row_num += 1

    # ─────────────────────────────────────────────────────────────────────────
    # HOJA 2: STOCK BAJO (ALERTA)
    # ─────────────────────────────────────────────────────────────────────────
    ws2 = wb.create_sheet(title="Stock Bajo")
    ws2.append(["ALERTAS DE STOCK BAJO (REPOSICIÓN INMINENTE)"])
    ws2.merge_cells("A1:G1")
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
            it.get("product", ""),
            it.get("category", ""),
            it.get("stock", 0),
            it.get("suggested_reorder", 1),
            it.get("supplier_price", 0.0),
            it.get("reorder_cost", 0.0)
        ])
        ws2.row_dimensions[row_num2].height = 20
        for c_idx in range(1, 8):
            cell = ws2.cell(row=row_num2, column=c_idx)
            cell.border = thin_border
            if c_idx == 4:
                cell.fill = PatternFill(start_color=C_LOW, end_color=C_LOW, fill_type="solid")
                cell.font = Font(color=C_LOW_TXT, bold=True)
                cell.alignment = Alignment(horizontal="center")
            elif c_idx in [5, 6, 7]:
                cell.alignment = Alignment(horizontal="right")
                if c_idx in [6, 7]:
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
