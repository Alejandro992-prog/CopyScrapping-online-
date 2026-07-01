# 📋  Clipboard Parser - Clipboard Parser Inteligente para Análisis de Precios

¡Bienvenido a ** Clipboard Parser**! Una potente herramienta local de automatización y análisis pasivo de precios locales y de competidores, diseñada para el **Proyecto **. 

Este sistema escucha en segundo plano el portapapeles de tu sistema operativo de forma 100% offline, detecta patrones de productos mediante Expresiones Regulares (Regex) auto-generadas y extrae y unifica datos en archivos tabulares (CSV/Excel) de forma silenciosa y eficiente.

---

## 🚀 Características Principales

*   **🕵️‍♂️ Captura Pasiva en Segundo Plano (Daemon)**: Se ejecuta de manera invisible y eficiente en tu sistema operativo. Cuando haces `Ctrl + C` sobre un texto que coincide con el patrón de un proveedor activo, extrae los datos al instante sin interrumpir tu flujo de trabajo.
*   **🧙‍♂️ Asistente No-Code de Regex**: Permite resaltar texto bruto (descripciones de productos) en la interfaz gráfica, etiquetar campos (`Producto`, `Modelo/SKU`, `Precio`, `Atributos`) y el backend genera automáticamente la expresión regular optimizada.
*   **📊 Fusión & Comparador de Precios**: Permite seleccionar y fusionar múltiples bases de datos de proveedores por columna común (`Modelo / SKU` o `Nombre`). Calcula automáticamente quién es el líder de coste (el más barato) y la diferencia porcentual con respecto al resto.
*   **🔒 Privacidad y Aislamiento (100% Offline)**: Todo el procesamiento y las bases de datos se gestionan localmente. Sin llamadas de red externas, evitando bloqueos de IP o sistemas anti-bot de las webs de competidores.

---

## 🛠️ Pila Tecnológica

*   **Backend**: Python 3.x, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
*   **Procesamiento de Datos**: [Pandas](https://pandas.pydata.org/), [OpenPyXL](https://openpyxl.readthedocs.io/)
*   **Integración con OS**: [Pyperclip](https://pyperclip.readthedocs.io/) para la escucha del portapapeles.
*   **Frontend**: HTML5, Vanilla CSS3 (Diseño Premium Oscuro, Glassmorphism, Micro-animaciones), Vanilla JavaScript (ES6+).

---

## 📁 Estructura del Proyecto

```bash
├── .agents/                 # Directrices de desarrollo del agente
├── data/                    # Directorio de bases de datos locales (ignorado en Git)
│   ├── providers/           # Configuraciones y bases de datos generadas
│   └── extractions/         # Archivos de salida (CSV/XLSX) de cada proveedor
├── static/                  # Archivos estáticos del Frontend
│   ├── index.html           # Interfaz gráfica principal
│   ├── style.css            # Estilos CSS (Tema Oscuro Premium)
│   └── app.js               # Lógica interactiva en JavaScript
├── app.py                   # Servidor FastAPI principal y lógica de daemon
├── config.json              # Base de datos de configuración de proveedores (ignorado en Git)
├── requirements.txt         # Dependencias del proyecto
└── README.md                # Esta guía de usuario
```

---

## 📦 Instalación y Configuración

1.  **Clonar el repositorio**:
    ```bash
    git clone <URL-del-repositorio>
    cd CopyScrapping
    ```

2.  **Instalar dependencias**:
    Asegúrate de tener Python instalado y ejecuta:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Iniciar el servidor**:
    Arranca la aplicación con Uvicorn:
    ```bash
    uvicorn app:app --reload
    ```
    El servidor estará disponible en [http://127.0.0.1:8000](http://127.0.0.1:8000).

---

## 📖 Instrucciones de Uso

Para ver una guía detallada paso a paso sobre cómo crear proveedores, entrenar el motor de Regex No-Code, realizar capturas y unificar tablas de comparación, por favor consulta la [Guía de Pruebas](file:///c:/Users/aleja/OneDrive/Escritorio/Programacion%20programas%20etc/CopyScrapping/instrucciones.md).

---

## 🛡️ Licencia

Este proyecto es de uso privado y local para el **Proyecto Clipboard Parser**. Todos los derechos reservados.
