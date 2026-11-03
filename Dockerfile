# Dockerfile para Garde Clipboard Parser Online
# Diseñado para desplegar fácilmente en Render, Railway, Fly.io o VPS

FROM python:3.10-slim

# Evitar que Python escriba archivos .pyc en el disco y activar salida sin buffer
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

WORKDIR /app

# Instalar dependencias del sistema para OCR (Tesseract, EasyOCR / OpenCV)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-spa \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias necesarias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código de la aplicación
COPY . .

# Exponer el puerto
EXPOSE 8000

# Ejecutar la aplicación
CMD uvicorn app:app --host 0.0.0.0 --port $PORT
