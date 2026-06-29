# Guía de Pruebas del Clipboard Parser (Proyecto Garde)

Sigue estos pasos para probar el funcionamiento del Clipboard Parser Inteligente en tu máquina local.

---

## Paso 1: Crear tu primer Proveedor (Entrenamiento No-Code)

1. Entra en la pestaña **Asistente No-Code** en el panel superior de la aplicación.
2. Rellena los datos básicos en el formulario:
   * **Nombre del Proveedor**: `Balay Electro`
   * **ID**: `balay` (se autogenera automáticamente en minúsculas)
   * **Formato**: `CSV`
3. Pega este texto real de ejemplo en la caja de texto:
   ```text
   Lavadora Balay 3TS273BA 419 EUR Blanco A
   ```
4. Ahora, selecciona con el ratón las partes del texto en la caja interactiva y asígnales su etiqueta correspondiente haciendo clic en los botones de color superiores:
   * Selecciona `Lavadora Balay` ➡️ Haz clic en **🏷️ Producto**.
   * Selecciona `3TS273BA` ➡️ Haz clic en **🧩 Modelo / SKU**.
   * Selecciona `419` ➡️ Haz clic en **💵 Precio**.
   * Selecciona `Blanco A` ➡️ Haz clic en **⚙️ Atributos Técnicos**.
5. Haz clic en el botón **Generar y Testear Regex**. Verás cómo el backend genera la expresión regular de forma automática y te muestra los datos extraídos de muestra abajo.
6. Haz clic en **Guardar Proveedor**. ¡Ya tienes tu primera plantilla configurada!

---

## Paso 2: Probar la Captura Automática (Ctrl + C)

1. Ve a la pestaña **Monitoreo en Vivo**.
2. En el menú desplegable de **Proveedor Activo**, selecciona `Balay Electro`.
3. Asegúrate de que el interruptor de "Escucha del Portapapeles" esté **encendido (en verde)**.
4. Abre cualquier otro programa de tu ordenador (un bloc de notas, otra pestaña de tu navegador habitual, un correo, etc.) y **copia (Ctrl + C)** exactamente este texto:
   ```text
   Lavadora Balay 3TS280XX 399 EUR Blanco B
   ```
5. Regresa al Dashboard de Garde. Verás que en la consola de logs aparece instantáneamente:
   `[HH:MM:SS] Capturado y guardado: Lavadora Balay`
6. Además, verás que el producto se añade automáticamente a la tabla de **Capturas Recientes** en la parte inferior, habiendo creado o actualizado el archivo de base de datos en `data/extractions/balay.csv`.

---

## Paso 3: Probar la Fusión de Tablas (Precios Cruzados)

Si deseas probar la unificación y comparación de precios cruzados entre varios proveedores:

1. Crea un segundo proveedor siguiendo el **Paso 1** (por ejemplo, con el nombre `Bosch Electro`, ID `bosch` y copia un texto de ejemplo similar).
2. Actívalo en la pestaña de monitoreo y captura algún dato copiando un texto de producto de esa marca con Ctrl+C.
3. Ve a la pestaña **Fusión & Comparador**.
4. Verás los dos archivos de extracción de datos listados. Selecciónalos marcando sus casillas de verificación.
5. Selecciona la columna de unión (`Modelo / SKU` o `Producto / Nombre`) y haz clic en el botón **Unificar Tablas y Comparar Precios**.
6. Se generará una tabla comparativa en la parte inferior en tiempo real, destacando en color verde el precio del competidor más barato (líder de coste) y mostrando la diferencia en porcentaje respecto a los otros competidores.
7. Puedes descargar esta matriz unificada en formato Excel o CSV con el botón de descarga.
