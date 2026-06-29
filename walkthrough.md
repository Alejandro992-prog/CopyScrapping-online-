# Registro de Desarrollo y Walkthrough - Clipboard Parser (Proyecto Garde)

Este documento contiene el registro de desarrollo e inicialización de la herramienta **Garde Clipboard Parser Inteligente**, creada para el análisis pasivo de precios locales.

---

## 1. Habilidades del Agente Configuradas

Se configuró un archivo de directrices en la carpeta del agente de desarrollo local:
*   **Ruta de Configuración**: `.agents/skills/proyecto_garde/SKILL.md`
*   **Competencias Clave**:
    1.  **Ejecución Local (Aislamiento de Red)**: Diseño 100% offline para evitar bloqueos de IP y sistemas anti-bot.
    2.  **Manejo Eficiente del Portapapeles**: Escucha en bucle con micro-pausas (`time.sleep(0.5)`) para mantener el uso de CPU en 0%.
    3.  **Procesamiento Semántico (Regex)**: Análisis robusto y mapeo dinámico de grupos nombrados.
    4.  **Ingeniería de Datos (Pandas)**: Manipulación de estructuras tabulares y exportación con codificación `utf-8-sig`.
    5.  **Tolerancia a Fallos**: Excepciones controladas para ignorar textos no coincidentes de forma pasiva sin interrumpir la ejecución.

---

## 2. Arquitectura de Archivos en el Espacio de Trabajo

*   **`requirements.txt`**: Librerías de Python instaladas localmente (`fastapi`, `uvicorn`, `pyperclip`, `pandas`, `openpyxl`).
*   **`config.json`**: Base de datos de configuración de proveedores y expresiones regulares entrenadas.
*   **`app.py`**: Backend principal en FastAPI que implementa la lógica del daemon de captura, generación automática de Regex y el unificador analítico de Pandas.
*   **`static/index.html`**: Layout interactivo con pestañas de Monitoreo, Entrenamiento No-Code y Fusión.
*   **`static/style.css`**: Hoja de estilos Vanilla CSS con un tema premium oscuro y estilos de etiquetado visual.
*   **`static/app.js`**: Integración Javascript que maneja la selección interactiva de texto para entrenamiento y la visualización de los datos.

---

## 3. Características Clave del Sistema

*   **Asistente No-Code de Regex**: Permite resaltar texto bruto (ej. descripciones de productos) directamente en el navegador, etiquetar campos (Producto, Modelo, Precio, Atributos) y el backend genera de forma automática la expresión regular ideal.
*   **Daemon de Captura Pasiva**: Funciona en segundo plano de manera invisible. Cuando el usuario pulsa `Ctrl + C` sobre un producto coincidente en cualquier sitio web, este se añade y formatea al instante en un archivo Excel/CSV propio de ese proveedor.
*   **Unificación y Consolidación Inteligente**: Módulo que recibe múltiples bases de datos de proveedores, las unifica de manera inteligente por el SKU/Modelo y calcula automáticamente al proveedor líder en coste y la diferencia porcentual con respecto al resto de competidores.

---

## 4. Estado de Ejecución del Servidor
*   **URL Local**: `http://127.0.0.1:8000`
*   **Monitoreo**: Activo en segundo plano.
