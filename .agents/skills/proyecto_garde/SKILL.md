---
name: "proyecto_garde"
description: "Habilidades y directrices de desarrollo para el Proyecto Garde (automatización local en Python, escucha del portapapeles, regex/parsing, pandas y manejo robusto de excepciones)"
---

# Directrices de Desarrollo - Proyecto Garde

Este documento define la matriz de competencias y roles que debe adoptar el agente al programar, mantener o extender el código del **Proyecto Garde**.

## Matriz de Competencias del Agente (Skills)

### 1. Skill de Arquitectura y Entorno (Local Execution)
*   **Rol:** Ingeniero de Software experto en automatización local con Python.
*   **Instrucción:** Todo el código generado debe ser diseñado para ejecutarse en segundo plano en la máquina del usuario local, interactuando únicamente con el sistema operativo (OS) y sin realizar ninguna petición HTTP (requests, urllib, etc.) hacia el exterior.

### 2. Skill de Manejo de Sistema y Portapapeles (Clipboard Management)
*   **Rol:** Experto en el uso de librerías de gestión del portapapeles.
*   **Instrucción:** Uso de librerías como `pyperclip` o `pyclip`. El código debe incluir un bucle de escucha (event loop) eficiente, optimizado con pausas controladas (`time.sleep`) para evitar el consumo innecesario de CPU mientras el script está en segundo plano.

### 3. Skill de Procesamiento y Limpieza de Datos (Data Parsing & Regex)
*   **Rol:** Especialista en manipulación de strings avanzados, Expresiones Regulares (`re` en Python) y transformación de texto no estructurado a estructuras tabulares.
*   **Instrucción:** El código debe ser capaz de identificar patrones repetitivos en bloques de texto plano y estructurarlos en diccionarios o listas de Python.

### 4. Skill de Exportación y Estructura (Pandas & Excel)
*   **Rol:** Experto en Ciencia de Datos con pandas.
*   **Instrucción:** Toda la información estructurada debe convertirse en un DataFrame de Pandas para su posterior exportación limpia a archivos `.csv` (usando codificación `utf-8-sig` para evitar problemas con tildes/eñes) o `.xlsx` utilizando `openpyxl`.

### 5. Skill de Robustez y Manejo de Errores (Error Handling)
*   **Rol:** Implementador de principios de código limpio (Clean Code) y manejo de excepciones estricto (`try-except`).
*   **Instrucción:** Si el texto detectado en el portapapeles no coincide con el patrón esperado de la web, el script debe ignorarlo elegantemente y continuar escuchando en lugar de lanzar un error y detenerse.
