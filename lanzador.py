import subprocess
import os
import sys

def main():
    # 1. Obtener la ruta donde está este .exe
    base_path = os.path.dirname(os.path.abspath(sys.executable))
    
    # 2. Configurar variables de entorno críticas
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["CUDA_MODULE_LOADING"] = "LAZY"
    
    # 3. Definir rutas al Python del venv y al script principal
    # Usamos shell=True para que respete el entorno de Windows
    python_exe = os.path.join(base_path, ".venv", "Scripts", "python.exe")
    script_main = os.path.join(base_path, "main.py")
    
    if not os.path.exists(python_exe):
        print(f"Error: No se encontro el entorno virtual en {python_exe}")
        input("Presiona Enter para salir...")
        return

    # 4. Lanzar el proceso de forma limpia
    try:
        # Esto ejecuta: .venv\Scripts\python.exe main.py
        subprocess.run([python_exe, script_main], check=True)
    except Exception as e:
        print(f"Error al ejecutar la app: {e}")
        input("Presiona Enter para salir...")

if __name__ == "__main__":
    main()