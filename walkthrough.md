# Registro de Desarrollo y Walkthrough - Clipboard Parser (Proyecto Garde)

Este documento contiene el registro de desarrollo e inicialización de la herramienta **Garde Clipboard Parser Inteligente**, creada para el análisis de precios locales de proveedores en entornos locales u online.

---

## 1. Habilidades del Agente Configuradas

Se configuró un archivo de directrices en la carpeta del agente de desarrollo local:
*   **Ruta de Configuración**: `.agents/skills/proyecto_garde/SKILL.md`
*   **Competencias Clave**:
    1.  **Ejecución Multi-entorno (Docker y Local)**: Diseñado para funcionar de manera local o en la nube mediante contenedores, adaptándose al puerto de entorno `$PORT`.
    2.  **Manejo del Portapapeles en Navegador (Seguridad Web)**: Detección automática de enfoque y lectura del portapapeles en el frontend (usando `navigator.clipboard`), soporte para Ctrl+V global en la página y caja de pegado rápido para entornos donde el portapapeles del host no es accesible por el backend.
    3.  **Procesamiento Semántico (Regex)**: Análisis robusto y mapeo dinámico de grupos nombrados.
    4.  **Ingeniería de Datos (Pandas)**: Manipulación de estructuras tabulares y exportación con codificación `utf-8-sig`.
    5.  **Tolerancia a Fallos**: Excepciones controladas para ignorar textos no coincidentes de forma pasiva sin interrumpir la ejecución.

---

## 2. Arquitectura de Archivos en el Espacio de Trabajo

*   **`requirements.txt`**: Librerías de Python instaladas (`fastapi`, `uvicorn`, `pandas`, `openpyxl`).
*   **`data/config.json`**: Base de datos de configuración de proveedores y expresiones regulares entrenadas (ubicada en `data/` para simplificar la persistencia a través de un único volumen montado).
*   **`app.py`**: Backend principal en FastAPI que implementa la lógica de la API de procesamiento de texto, autogeneración de Regex, normalización de datos y el unificador analítico de Pandas.
*   **`static/index.html`**: Layout interactivo con pestañas de Monitoreo, Entrenamiento No-Code y Fusión.
*   **`static/style.css`**: Hoja de estilos Vanilla CSS con un tema premium oscuro y estilos de etiquetado visual.
*   **`static/app.js`**: Integración Javascript que maneja la selección interactiva de texto para entrenamiento, lectura del portapapeles del navegador en enfoque / pegado, y la visualización de los datos.
*   **`Dockerfile`**: Configuración de Docker optimizada para despliegues en la nube (Render, Railway, Fly.io, etc.).

---

## 3. Características Clave del Sistema

*   **Asistente No-Code de Regex**: Permite resaltar texto bruto (ej. descripciones de productos) directamente en el navegador, etiquetar campos (Producto, Modelo, Precio, Atributos) y el backend genera de forma automática la expresión regular ideal.
*   **Captura Inteligente por Enfoque y Ctrl+V (Versión Online)**: Cuando el usuario pulsa `Ctrl+C` en cualquier sitio web para copiar un producto y vuelve a la pestaña de CopyScrapping, la aplicación web detecta automáticamente el enfoque y lee el portapapeles (previo permiso de privacidad del navegador), procesándolo al instante. También soporta pegado manual mediante `Ctrl+V` global y una caja de pegado rápido.
*   **Unificación y Consolidación Inteligente**: Módulo que recibe múltiples bases de datos de proveedores, las unifica de manera inteligente por el SKU/Modelo y calcula automáticamente al proveedor líder en coste y la diferencia porcentual con respecto al resto de competidores.

---

## 4. Estado de Ejecución y Despliegue

*   **Ejecución en Desarrollo:**
    *   Iniciar el servidor: `uvicorn app:app --reload` o `python app.py`
    *   URL Local: `http://127.0.0.1:8000`
*   **Despliegue y Contenedores (Docker):**
    *   La aplicación incluye un `Dockerfile` que expone el puerto definido por `$PORT` (por defecto `8000`).
    *   **Persistencia Centralizada**: El archivo de configuración `config.json` y los directorios de datos se ubican bajo la carpeta `/app/data`. Esto permite configurar persistencia permanente en la nube montando un único disco/volumen en `/app/data`.
    *   **Migración Automática**: El backend detecta si existía un archivo `config.json` heredado en la raíz y lo migra automáticamente a `/app/data/config.json` al iniciar, garantizando la retrocompatibilidad.
*   **Empaquetado Local (PyInstaller):**
    *   Si se requiere una versión ejecutable de escritorio local, se puede usar `python build_exe.py` (requiere instalar `pyinstaller`). Genera el archivo autónomo `dist/GardeClipboardParser.exe`.

---

## 5. Correcciones Recientes y Mejoras

*   **Corrección de Extracción Parcial (Solo un producto)**:
    *   **Problema**: Al copiar bloques con múltiples productos, si la expresión regular entrenada era muy estricta (por ejemplo, con atributos técnicos no etiquetados como "9kg"), el motor de procesamiento extraía únicamente el producto que coincidía exactamente y omitía el resto, debido a que el extractor adaptativo solo servía como alternativa si no había ninguna coincidencia exacta en absoluto.
    *   **Solución**: Se optimizó la función `process_text` en [app.py](file:///c:/Users/aleja/OneDrive/Escritorio/Programacion%20programas%20etc/ideas%20Nuevos%20Proyectos/CopyScrapping%20%28online%29/app.py) para dividir el texto copiado. Ahora, las partes exactas se extraen usando la expresión regular, y todas las secciones de texto no coincidentes se envían automáticamente al extractor adaptativo inteligente. Esto garantiza que todos los productos del bloque copiado sean procesados y guardados de forma consolidada.

*   **Matriz de Stock y Cobertura (ERP PDF)**:
    *   **Funcionalidad**: Se creó una pestaña para que los compradores suban informes de stock en PDF de su ERP. El sistema analiza el texto del PDF, identifica los productos usando heurísticas basadas en tokens (aislando modelos, marcas, cantidades y precios), y calcula una matriz bidimensional (Capacidad vs Rango de Precios).
    *   **Integración**: Al pulsar en cualquier celda de la matriz de inventario, se muestran las referencias internas. Se puede hacer clic en un botón "🔍 Mercado" en cada artículo para buscar en paralelo en todas las extracciones de competidores y ver qué proveedores tienen ofertas activas para ese mismo modelo, facilitando la toma de decisiones de compras.


