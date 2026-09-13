# ⚡ Garde Clipboard Parser Online - Automatización Inteligente y Análisis de Precios

¡Bienvenido a **Garde Clipboard Parser**! Una potente plataforma local y web de automatización, captura de datos y análisis pasivo de precios locales y de competidores, diseñada para el sector de electrodomésticos y comercio B2B/B2C.

El sistema permite capturar productos desde el portapapeles del navegador (Ctrl+C / Ctrl+V), mediante subida de imágenes/fotos con OCR local o Google Gemini Vision estructurado, y a través de un Asistente No-Code de Expresiones Regulares (Regex). Además, consolida los catálogos y permite comparar precios cruzados entre múltiples proveedores.

---

## 🚀 Características Principales

* **🕵️‍♂️ Captura en Vivo (Portapapeles & Web)**:
  - Detección automática de texto en el portapapeles con solo copiar (`Ctrl + C`) y enfocar la pestaña web.
  - Soporte global para pegar (`Ctrl + V`) en cualquier parte del dashboard.
  - Mapeo inteligente con Regex pre-compiladas y sistema de rescate adaptativo ante textos ruidosos.
* **👁️ Visión Artificial y OCR Híbrido**:
  - Extracción directa de productos desde imágenes y capturas de pantalla mediante **Google Gemini Vision** (`gemini-3.6-flash`, `gemini-3.8-flash`, etc.).
  - Motor de respaldo local offline con **EasyOCR** y **PyTesseract**.
  - Reconocimiento automático de categorías ("Tipo de Aparato"), marcas y rangos de precio (Sin IVA, Con IVA y PVP).
* **🧙‍♂️ Asistente No-Code de Regex**:
  - Selecciona y etiqueta fragmentos de texto en la interfaz visual (`Producto`, `Modelo / SKU`, `Precio`, `Atributos`).
  - El backend genera de manera matemática la expresión regular óptima y permite guardarla como plantilla de proveedor.
* **📦 Matriz de Inventario y Stock (ERP / Catálogos)**:
  - Carga masiva de inventarios (Excel/PDF de ERPs como Balay, Bosch, etc.).
  - Detección inteligente de colores por gama de coste (Económica, Media, Premium) personalizable por categoría.
  - Búsqueda en vivo y exportación formateada.
* **📊 Fusión & Comparador Cruzado de Precios**:
  - Une bases de datos de varios proveedores mediante la clave única de cruce (`Modelo / SKU`).
  - Destaca automáticamente al proveedor más económico (líder de coste) y calcula la diferencia porcentual con respecto al resto.
  - Exportación a hojas de cálculo `.xlsx` con diseño profesional.
* **🔒 Seguridad y Control de Acceso**:
  - Autenticación HTTP Basic configurable para entornos multiusuario.
  - Cuentas de operador y perfil administrador ("root").

---

## 🛠️ Pila Tecnológica

* **Backend**: Python 3.10+, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
* **Procesamiento de Datos**: [Pandas](https://pandas.pydata.org/), [OpenPyXL](https://openpyxl.readthedocs.io/)
* **IA y Visión**: [Google GenAI SDK](https://github.com/google/generative-ai-python), EasyOCR, PyTesseract, Pillow, PyPDF
* **Frontend**: Vanilla HTML5, CSS3 moderno (tema oscuro con glassmorphism), JavaScript Vanilla modular (sin frameworks pesados)

---

## 📁 Estructura del Proyecto

```text
CopyScrapping (online)/
├── app.py                  # Servidor FastAPI principal y lógica completa
├── static/                 # Interfaz de usuario (Frontend)
│   ├── index.html          # Estructura del dashboard y modales
│   ├── style.css           # Estilos y tema visual oscuro
│   └── app.js              # Lógica de cliente, portapapeles y eventos
├── data/                   # Directorio de persistencia de datos
│   ├── config.json         # Proveedores, claves API y configuración activa
│   ├── users.json          # Usuarios registrados
│   ├── dictionary.json     # Diccionario de marcas y categorías
│   ├── extractions/        # Archivos CSV/XLSX generados por proveedor
│   ├── stock/              # Archivos de inventario procesados
│   └── consolidated/       # Archivos unificados de comparativas
├── requirements.txt        # Dependencias de Python
├── Dockerfile              # Configuración para despliegue en la nube
├── .dockerignore           # Exclusiones para imágenes Docker optimizadas
├── build_exe.py            # Script para compilar el ejecutable local de Windows
└── README.md               # Esta guía de usuario
```

---

## 📦 Instalación y Puesta en Marcha

### 1. Requisitos Previos
- Python 3.10 o superior instalado.
- Opcional: Clave de API de Google Gemini (si deseas usar extracción con IA Vision).

### 2. Instalación de Dependencias
```bash
pip install -r requirements.txt
```

### 3. Iniciar el Servidor
```bash
python app.py
```
O bien mediante Uvicorn directamente:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```
Abre tu navegador habitual en: **`http://localhost:8000`**

---

## 📖 Guía Rápida de Uso (Paso a Paso)

### Paso 1: Configurar o Entrenar un Proveedor
1. Ve a la pestaña **Asistente No-Code**.
2. Asigna un nombre (ej. `Balay Electro`) y formato de salida (`CSV` o `XLSX`).
3. Pega un texto de ejemplo de la web del proveedor:
   ```text
   Lavadora Balay 3TS273BA 419 EUR Blanco A
   ```
4. Selecciona las partes con el ratón y haz clic en los botones superiores:
   - `Lavadora Balay` ➡️ **🏷️ Producto**
   - `3TS273BA` ➡️ **🧩 Modelo / SKU**
   - `419 EUR` ➡️ **💵 Precio**
   - `Blanco A` ➡️ **⚙️ Atributos**
5. Pulsa **Generar y Testear Regex** y luego **Guardar Proveedor**.

### Paso 2: Capturar en Vivo
1. En **Monitoreo en Vivo**, selecciona el proveedor activo.
2. Asegúrate de que el interruptor de escucha esté activado (verde).
3. En cualquier otra pestaña o programa de tu ordenador, pulsa `Ctrl + C` sobre un producto.
4. Al volver al dashboard o pulsar `Ctrl + V`, el producto se extrae y guarda automáticamente en `data/extractions/<proveedor>.csv`.

### Paso 3: Fusión y Comparador de Precios
1. Ve a la pestaña **Fusión & Comparador**.
2. Marca las casillas de los proveedores que deseas comparar (ej. `balay.csv` y `bosch.csv`).
3. Selecciona la columna de unión (`Modelo / SKU`).
4. Haz clic en **Unificar Tablas y Comparar Precios**.
5. Se generará la matriz interactiva destacando al competidor más barato y podrás descargar el informe en Excel.

---

## 🐳 Despliegue en la Nube (Docker)

El repositorio incluye un `Dockerfile` optimizado con puerto dinámico `$PORT`.
Para desplegar en servicios como **Render**, **Railway**, **Fly.io** o un VPS propio:
```bash
docker build -t garde-clipboard-parser .
docker run -p 8000:8000 -v $(pwd)/data:/app/data garde-clipboard-parser
```
> **Nota de Persistencia**: Monta el volumen persistente en `/app/data` para conservar tus proveedores y archivos extraídos.

---

## 💻 Compilación para Windows (.EXE)

Para empaquetar la aplicación en un ejecutable autónomo para Windows sin necesidad de que el cliente tenga Python instalado:
```bash
pip install pyinstaller
python build_exe.py
```
El ejecutable autónomo se generará en la carpeta `dist/GardeClipboardParser.exe`.
