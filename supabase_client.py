import os
import json
import math
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

import httpx

logger = logging.getLogger("supabase_client")

def sanitize_for_json(obj: Any) -> Any:
    """Convierte de forma recursiva valores NaN o Infinitos en None para compatibilidad estricta con JSON."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_for_json(v) for v in obj]
    return obj

def clean_price_number(val: Any) -> Optional[float]:
    """Limpia cadenas de precios a flotantes válidos para la base de datos."""
    if val is None or val == "":
        return None
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if isinstance(val, int):
        return float(val)
    s = str(val).strip()
    s = s.replace("€", "").replace("EUR", "").replace("$", "").replace("£", "").strip()
    if not s or s.lower() == "nan" or s.lower() == "none":
        return None
    # Reemplazar coma por punto si es decimal español
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    elif "." in s and "," in s:
        # Por ejemplo 1.250,50 -> 1250.50
        s = s.replace(".", "").replace(",", ".")
    try:
        f = float(s)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except ValueError:
        return None



DEFAULT_SUPABASE_URL = "https://ehekxiexlhychzmrfnez.supabase.co"
DEFAULT_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVoZWt4aWV4bGh5Y2h6bXJmbmV6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODMwMTExMDksImV4cCI6MjA5ODU4NzEwOX0.1eZXv_v04ChRnVn0omwOJS7hdEDq2JdeAJSAI6MI-Zs"

class SupabaseClient:
    """
    Cliente ligero y resiliente para Supabase.
    Utiliza httpx para interactuar directamente con la API REST (PostgREST) de Supabase,
    garantizando cero fallos por dependencias ausentes y un rendimiento asíncrono y síncrono óptimo.
    """

    def __init__(self, url: Optional[str] = None, key: Optional[str] = None, timeout: float = 10.0):
        self.url = (url or os.getenv("SUPABASE_URL") or DEFAULT_SUPABASE_URL).strip().rstrip("/")
        self.key = (key or os.getenv("SUPABASE_KEY") or DEFAULT_SUPABASE_KEY).strip()
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.key and self.url.startswith("http"))

    def _headers(self, prefer_upsert: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer_upsert:
            headers["Prefer"] = prefer_upsert
        return headers

    def test_connection(self, url: Optional[str] = None, key: Optional[str] = None) -> Tuple[bool, str]:
        """Prueba la conexión y credenciales contra el endpoint REST de Supabase."""
        test_url = (url or self.url).strip().rstrip("/")
        test_key = (key or self.key).strip()

        if not test_url or not test_url.startswith("http"):
            return False, "La URL de Supabase no es válida o está vacía (debe comenzar con http:// o https://)."
        if not test_key:
            return False, "La clave de API (Anon o Service Role) es obligatoria."

        rest_url = f"{test_url}/rest/v1/"
        headers = {
            "apikey": test_key,
            "Authorization": f"Bearer {test_key}",
            "Accept": "application/json",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                # 1. Probar consulta ligera a extractions con las credenciales
                resp = client.get(f"{test_url}/rest/v1/extractions?limit=1", headers=headers)
                if resp.status_code in (200, 204, 206):
                    return True, "¡Conexión exitosa con Supabase y tabla de extractions lista!"

                # 2. Comprobar salud del servidor mediante auth/health
                health_resp = client.get(f"{test_url}/auth/v1/health", headers={"apikey": test_key})
                if health_resp.status_code == 200:
                    if resp.status_code == 404:
                        return True, "¡Conexión exitosa con Supabase! (Aviso: Ejecuta supabase_schema.sql para crear las tablas si aún no lo has hecho)."
                    return True, "¡Conexión exitosa con Supabase!"

                if resp.status_code == 401 and health_resp.status_code == 401:
                    return False, "Error de autenticación: La clave de API no es válida o ha caducado."
                elif resp.status_code == 404:
                    return False, f"Servidor no encontrado en {test_url}. Revisa la URL del proyecto."
                else:
                    return False, f"Supabase respondió con código {resp.status_code}: {resp.text[:150]}"
        except httpx.ConnectError:
            return False, f"No se pudo conectar con el servidor {test_url}. Verifica tu conexión a internet o la URL."
        except httpx.TimeoutException:
            return False, "Tiempo de espera agotado al intentar conectar con Supabase."
        except Exception as e:
            return False, f"Error inesperado al probar conexión: {str(e)}"

    def upsert_extractions(self, items: List[Dict[str, Any]], provider_id: Optional[str] = None, provider_name: Optional[str] = None) -> Tuple[int, Optional[str]]:
        """
        Inserta o actualiza extracciones en la tabla `extractions`.
        Utiliza 'on_conflict=provider_id,model' para evitar duplicados.
        """
        if not self.is_configured:
            return 0, "Supabase no está configurado."
        if not items:
            return 0, None

        payload = []
        for it in items:
            p_id = str(it.get("provider_id") or provider_id or it.get("Proveedor") or "default").strip()
            p_name = str(it.get("provider_name") or provider_name or it.get("Proveedor_Nombre") or p_id).strip()
            model = str(it.get("Modelo") or it.get("model") or it.get("SKU") or "").strip()
            if not model:
                continue

            brand = str(it.get("Marca") or it.get("brand") or "").strip() or None
            category = str(it.get("Tipo de Aparato") or it.get("Categoría") or it.get("category") or "").strip() or None
            product = str(it.get("Descripción") or it.get("product") or it.get("producto") or "").strip() or None
            attributes = str(it.get("Atributos") or it.get("attributes") or "").strip() or None

            p_no_vat = clean_price_number(it.get("Precio Sin IVA") or it.get("price_no_vat"))
            p_vat = clean_price_number(it.get("Precio Con IVA") or it.get("price_vat"))
            pvp = clean_price_number(it.get("PVP") or it.get("pvp"))

            payload.append({
                "provider_id": p_id,
                "provider_name": p_name,
                "model": model,
                "brand": brand,
                "category": category,
                "product": product,
                "price_no_vat": p_no_vat,
                "price_vat": p_vat,
                "pvp": pvp,
                "attributes": attributes,
                "raw_data": sanitize_for_json(it),
                "captured_at": it.get("Fecha") or it.get("timestamp") or datetime.utcnow().isoformat(),
            })

        if not payload:
            return 0, "No se encontraron filas con 'Modelo' válido para sincronizar."

        endpoint = f"{self.url}/rest/v1/extractions?on_conflict=provider_id,model"
        headers = self._headers(prefer_upsert="resolution=merge-duplicates")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code in (200, 201, 204):
                    return len(payload), None
                else:
                    return 0, f"Error en Supabase ({resp.status_code}): {resp.text[:200]}"
        except Exception as e:
            logger.error(f"Error sincronizando extractions con Supabase: {e}")
            return 0, str(e)

    def fetch_extractions(self, provider_id: Optional[str] = None, limit: int = 1000) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Obtiene las capturas desde Supabase."""
        if not self.is_configured:
            return [], "Supabase no está configurado."

        query = f"?select=*&order=captured_at.desc&limit={limit}"
        if provider_id:
            query += f"&provider_id=eq.{provider_id}"

        endpoint = f"{self.url}/rest/v1/extractions{query}"
        headers = self._headers()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    return resp.json(), None
                return [], f"Error recuperando datos ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            return [], str(e)

    def upsert_stock(self, items: List[Dict[str, Any]]) -> Tuple[int, Optional[str]]:
        """Inserta o actualiza ítems de inventario en la tabla `stock_items`."""
        if not self.is_configured:
            return 0, "Supabase no está configurado."
        if not items:
            return 0, None

        payload = []
        for it in items:
            model = str(it.get("model") or it.get("Modelo") or "").strip()
            if not model:
                continue

            cost_price = clean_price_number(it.get("cost_price") or it.get("coste") or it.get("Precio")) or 0.0
            stock_units = int(it.get("stock_units") or it.get("stock") or it.get("unidades") or 0)

            payload.append({
                "model": model,
                "brand": str(it.get("brand") or it.get("Marca") or "").strip() or None,
                "category": str(it.get("category") or it.get("Categoría") or "").strip() or None,
                "description": str(it.get("description") or it.get("Descripción") or "").strip() or None,
                "cost_price": cost_price,
                "stock_units": stock_units,
                "price_tier": str(it.get("price_tier") or it.get("Gama") or "").strip() or None,
                "ean": str(it.get("ean") or "").strip() or None,
                "source_file": str(it.get("source_file") or "").strip() or None,
                "raw_data": sanitize_for_json(it),
                "updated_at": datetime.utcnow().isoformat(),
            })

        if not payload:
            return 0, "No hay productos de stock válidos."

        # Procesar en bloques de 500 para evitar sobrecarga de payload
        chunk_size = 500
        total_synced = 0
        endpoint = f"{self.url}/rest/v1/stock_items?on_conflict=model"
        headers = self._headers(prefer_upsert="resolution=merge-duplicates")

        try:
            with httpx.Client(timeout=self.timeout * 2) as client:
                for i in range(0, len(payload), chunk_size):
                    chunk = payload[i:i + chunk_size]
                    resp = client.post(endpoint, json=chunk, headers=headers)
                    if resp.status_code in (200, 201, 204):
                        total_synced += len(chunk)
                    else:
                        return total_synced, f"Error en bloque {i}: {resp.text[:150]}"
            return total_synced, None
        except Exception as e:
            return total_synced, str(e)

    def fetch_stock(self, limit: int = 5000) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Obtiene el inventario desde Supabase."""
        if not self.is_configured:
            return [], "Supabase no está configurado."

        endpoint = f"{self.url}/rest/v1/stock_items?select=*&order=updated_at.desc&limit={limit}"
        headers = self._headers()

        try:
            with httpx.Client(timeout=self.timeout * 2) as client:
                resp = client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    return resp.json(), None
                return [], f"Error recuperando stock ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            return [], str(e)

    def upsert_providers(self, providers: List[Dict[str, Any]]) -> Tuple[int, Optional[str]]:
        """Sincroniza las plantillas y reglas de regex de proveedores."""
        if not self.is_configured or not providers:
            return 0, "Supabase no está configurado o no hay proveedores."

        payload = []
        for p in providers:
            p_id = str(p.get("id") or "").strip()
            if not p_id:
                continue
            payload.append({
                "id": p_id,
                "name": p.get("name") or p_id,
                "regex": p.get("regex") or "",
                "fields": p.get("fields") or [],
                "file_format": p.get("file_format") or "csv",
                "sample_text": p.get("sample_text") or "",
                "labels": p.get("labels") or [],
                "updated_at": datetime.utcnow().isoformat(),
            })

        endpoint = f"{self.url}/rest/v1/providers?on_conflict=id"
        headers = self._headers(prefer_upsert="resolution=merge-duplicates")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                if resp.status_code in (200, 201, 204):
                    return len(payload), None
                return 0, f"Error guardando proveedores: {resp.text[:150]}"
        except Exception as e:
            return 0, str(e)

    def fetch_providers(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Descarga los proveedores guardados en Supabase."""
        if not self.is_configured:
            return [], "Supabase no está configurado."

        endpoint = f"{self.url}/rest/v1/providers?select=*"
        headers = self._headers()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    return resp.json(), None
                return [], f"Error obteniendo proveedores ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            return [], str(e)

    def delete_extractions_by_provider(self, provider_id: str) -> Tuple[bool, Optional[str]]:
        """Elimina de Supabase todas las extracciones asociadas a un provider_id."""
        if not self.is_configured:
            return False, "Supabase no está configurado."
        p_id = str(provider_id).strip()
        if not p_id:
            return False, "provider_id no válido."

        endpoint = f"{self.url}/rest/v1/extractions?provider_id=eq.{p_id}"
        headers = self._headers()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.delete(endpoint, headers=headers)
                if resp.status_code in (200, 204):
                    return True, None
                return False, f"Supabase delete error ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            logger.error(f"Error eliminando extracciones de {p_id} en Supabase: {e}")
            return False, str(e)

    def delete_extraction_by_model(self, provider_id: str, model: str) -> Tuple[bool, Optional[str]]:
        """Elimina de Supabase una extracción específica por provider_id y model."""
        if not self.is_configured:
            return False, "Supabase no está configurado."
        p_id = str(provider_id).strip()
        m = str(model).strip()
        if not p_id or not m:
            return False, "Parámetros incompletos para eliminar fila."

        endpoint = f"{self.url}/rest/v1/extractions?provider_id=eq.{p_id}&model=eq.{m}"
        headers = self._headers()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.delete(endpoint, headers=headers)
                if resp.status_code in (200, 204):
                    return True, None
                return False, f"Supabase delete error ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            logger.error(f"Error eliminando fila {m} de {p_id} en Supabase: {e}")
            return False, str(e)

    def delete_provider_record(self, provider_id: str) -> Tuple[bool, Optional[str]]:
        """Elimina una plantilla de proveedor de la tabla providers en Supabase."""
        if not self.is_configured:
            return False, "Supabase no está configurado."
        p_id = str(provider_id).strip()
        if not p_id:
            return False, "provider_id no válido."

        endpoint = f"{self.url}/rest/v1/providers?id=eq.{p_id}"
        headers = self._headers()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.delete(endpoint, headers=headers)
                if resp.status_code in (200, 204):
                    return True, None
                return False, f"Supabase delete provider error ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            logger.error(f"Error eliminando proveedor {p_id} en Supabase: {e}")
            return False, str(e)

    def upsert_tariff(self, tariff_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Guarda o actualiza una tarifa completa en la tabla `tariffs` de Supabase.
        """
        if not self.is_configured:
            return False, "Supabase no está configurado."
        if not tariff_data or not tariff_data.get("id"):
            return False, "Datos de tarifa inválidos."

        endpoint = f"{self.url}/rest/v1/tariffs"
        headers = self._headers(prefer_upsert="resolution=merge-duplicates")

        safe_data = sanitize_for_json({
            "id": tariff_data.get("id"),
            "provider_name": tariff_data.get("provider_name") or "Proveedor",
            "tariff_name": tariff_data.get("tariff_name") or "",
            "file_type": tariff_data.get("file_type") or "",
            "original_filename": tariff_data.get("original_filename") or "",
            "upload_date": tariff_data.get("upload_date") or "",
            "total_items": int(tariff_data.get("total_items") or len(tariff_data.get("items") or [])),
            "items": tariff_data.get("items") or [],
            "created_at": tariff_data.get("created_at") or datetime.now().isoformat()
        })

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(endpoint, json=safe_data, headers=headers)
                if resp.status_code in (200, 201, 204):
                    return True, None
                if resp.status_code == 404:
                    return False, "La tabla 'tariffs' no existe aún en Supabase. Ejecuta supabase_schema.sql en tu SQL Editor."
                return False, f"Supabase error ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            logger.error(f"Error guardando tarifa en Supabase: {e}")
            return False, str(e)

    def fetch_tariffs(self, include_items: bool = True) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Descarga las tarifas guardadas en Supabase.
        """
        if not self.is_configured:
            return [], "Supabase no está configurado."

        select_cols = "*" if include_items else "id,provider_name,tariff_name,file_type,original_filename,upload_date,total_items,created_at"
        endpoint = f"{self.url}/rest/v1/tariffs?select={select_cols}&order=created_at.desc"
        headers = self._headers()

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(endpoint, headers=headers)
                if resp.status_code == 200:
                    return resp.json(), None
                if resp.status_code == 404:
                    return [], "Tabla 'tariffs' no encontrada en Supabase."
                return [], f"Error obteniendo tarifas ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            logger.error(f"Error cargando tarifas de Supabase: {e}")
            return [], str(e)

    def delete_tariff_record(self, tariff_id: str) -> Tuple[bool, Optional[str]]:
        """
        Elimina una tarifa de la tabla tariffs en Supabase.
        """
        if not self.is_configured:
            return False, "Supabase no está configurado."
        t_id = str(tariff_id).replace("tariff_", "").strip()
        if not t_id:
            return False, "tariff_id no válido."

        endpoint = f"{self.url}/rest/v1/tariffs?id=eq.{t_id}"
        headers = self._headers()

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.delete(endpoint, headers=headers)
                if resp.status_code in (200, 204):
                    return True, None
                return False, f"Supabase delete tariff error ({resp.status_code}): {resp.text[:150]}"
        except Exception as e:
            logger.error(f"Error eliminando tarifa {t_id} en Supabase: {e}")
            return False, str(e)

