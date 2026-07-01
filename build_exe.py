import os
import subprocess
import sys

def build():
    print("Iniciando compilación con PyInstaller...")
    
    # Comando PyInstaller
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        # En Windows se usa ";" para separar el origen del destino en --add-data.
        # En macOS/Linux se usa ":". Usamos el separador de ruta de búsqueda del OS.
        f"--add-data=static{os.pathsep}static",
        "--name=GardeClipboardParser",
        "app.py"
    ]
    
    print(f"Ejecutando comando: {' '.join(cmd)}")
    result = subprocess.run(cmd, shell=True)
    
    if result.returncode == 0:
        print("\n¡Éxito! El archivo ejecutable se ha creado en la carpeta 'dist'.")
        print("Ruta del ejecutable: dist/GardeClipboardParser.exe")
    else:
        print("\nOcurrió un error al compilar con PyInstaller.")
        sys.exit(result.returncode)

if __name__ == "__main__":
    build()
