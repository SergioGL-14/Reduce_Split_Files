import os
import sys
import subprocess
import shutil
from PIL import Image, UnidentifiedImageError
from PyPDF2 import PdfReader, PdfWriter
import tkinter as tk
from tkinter import filedialog, messagebox

# Buscar PDF24 automáticamente
def find_pdf24():
    possible_paths = [
        r"C:\Program Files\PDF24\pdf24-DocTool.exe",
        r"C:\Program Files (x86)\PDF24\pdf24-DocTool.exe"
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None

PDF24_PATH = find_pdf24()
if PDF24_PATH is None:
    print("Error: No se encontró PDF24. Asegúrate de que esté instalado.")
    sys.exit(1)

# Comprimir imágenes con Pillow
def compress_image(input_path, output_path, quality=40, max_size=(1024,768), threshold=1*1024*1024):
    try:
        if not os.path.exists(input_path):
            print(f"Error: El archivo {input_path} no existe.")
            return

        img = Image.open(input_path)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        img.save(output_path, quality=quality, optimize=True)

        while os.path.getsize(output_path) > threshold and quality > 10:
            quality -= 10
            img.save(output_path, quality=quality, optimize=True)
        
        print(f"Imagen comprimida: {output_path} ({os.path.getsize(output_path)/1024:.2f} KB)")

    except UnidentifiedImageError:
        print(f"Error: No se pudo abrir la imagen {input_path}. Formato no válido o archivo corrupto.")
    except PermissionError:
        print(f"Error: No se puede acceder a {input_path}. Puede estar en uso por otro programa.")
    except Exception as e:
        print(f"Error desconocido al comprimir imagen: {e}")

# Comprimir PDF usando PDF24
def compress_pdf(input_pdf, output_pdf, dpi=144, image_quality=75):
    try:
        if not os.path.exists(input_pdf):
            print(f"Error: El archivo {input_pdf} no existe.")
            return

        output_dir = os.path.dirname(output_pdf)
        temp_pdf = os.path.join(output_dir, f"temp_{os.path.basename(input_pdf)}")
        compressed_pdf = os.path.join(output_dir, f"{os.path.basename(output_pdf)}")  # Salida esperada

        shutil.copy2(input_pdf, temp_pdf)

        # 🔹 Ejecutar PDF24 forzando el nombre de salida
        subprocess.run([
            PDF24_PATH,
            "-compress",
            "-dpi", str(dpi),
            "-imageQuality", str(image_quality),
            "-outputFile", compressed_pdf,
            temp_pdf
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Verificar si el archivo comprimido existe y renombrarlo si es necesario
        if os.path.exists(compressed_pdf):
            print(f"PDF comprimido: {compressed_pdf} ({os.path.getsize(compressed_pdf)/1024:.2f} KB)")

        # Eliminar el archivo temporal original
        if os.path.exists(temp_pdf):
            os.remove(temp_pdf)
            print(f"🗑️ Eliminado archivo temporal: {temp_pdf}")

    except subprocess.CalledProcessError:
        print("Error: No se pudo ejecutar PDF24. Verifica la instalación.")
    except PermissionError:
        print(f"Error: No se puede acceder a {input_pdf}. Puede estar en uso por otro programa.")
    except Exception as e:
        print(f"Error desconocido al comprimir PDF: {e}")

# Dividir PDF en dos partes
def split_pdf(input_pdf, output_pdf1, output_pdf2):
    try:
        if not os.path.exists(input_pdf):
            print(f"Error: El archivo {input_pdf} no existe.")
            return

        reader = PdfReader(input_pdf)
        num_pages = len(reader.pages)
        if num_pages < 2:
            print(f"Advertencia: El PDF {input_pdf} tiene solo una página, no se dividirá.")
            return

        mid_point = num_pages // 2
        writer1 = PdfWriter()
        writer2 = PdfWriter()

        for i in range(num_pages):
            if i < mid_point:
                writer1.add_page(reader.pages[i])
            else:
                writer2.add_page(reader.pages[i])

        with open(output_pdf1, 'wb') as f:
            writer1.write(f)
        with open(output_pdf2, 'wb') as f:
            writer2.write(f)

        print(f"PDF dividido en {output_pdf1} y {output_pdf2}")

    except Exception as e:
        print(f"Error desconocido al dividir PDF: {e}")

# Gestionar compresión de PDFs
def handle_pdf_compression(file_path, threshold=1*1024*1024):
    base, ext = os.path.splitext(file_path)
    compressed_file = f"{base}_compressed.pdf"

    compress_pdf(file_path, compressed_file)

    if os.path.exists(compressed_file) and os.path.getsize(compressed_file) > threshold:
        part1 = f"{base}_compressed_part1.pdf"
        part2 = f"{base}_compressed_part2.pdf"

        split_pdf(compressed_file, part1, part2)

        for part in [part1, part2]:
            if os.path.exists(part) and os.path.getsize(part) > threshold:
                compress_pdf(part, part, dpi=100, image_quality=60)

        # Eliminar el archivo comprimido si se ha dividido
        if os.path.exists(compressed_file):
            os.remove(compressed_file)

# Gestionar archivos según extensión
def process_file(file_path, threshold=1*1024*1024):
    try:
        if not os.path.isfile(file_path):
            print(f"Error: {file_path} no es un archivo válido.")
            return

        base, ext = os.path.splitext(file_path)
        ext = ext.lower()

        if ext in ['.jpg', '.jpeg', '.png']:
            compressed_file = f"{base}_compressed{ext}"
            compress_image(file_path, compressed_file, threshold=threshold)

        elif ext == '.pdf':
            handle_pdf_compression(file_path, threshold)

        else:
            print(f"Formato no soportado: {file_path}")

    except Exception as e:
        print(f"Error desconocido al procesar archivo {file_path}: {e}")

# Función principal con interfaz opcional
def main():
    try:
        if len(sys.argv) > 1:
            files = [f for f in sys.argv[1:] if os.path.isfile(f)]
        else:
            root = tk.Tk()
            root.withdraw()
            files = filedialog.askopenfilenames(
                title="Selecciona archivos para comprimir (PDF/Imágenes)",
                filetypes=[("PDF e Imágenes", "*.pdf;*.jpg;*.jpeg;*.png")]
            )

        if not files:
            messagebox.showinfo("No se seleccionaron archivos", "No se han seleccionado archivos para procesar.")
            return

        for file in files:
            process_file(file)

        print("Proceso terminado. Comprueba los archivos comprimidos.")

    except Exception as e:
        print(f"Error crítico en la ejecución del script: {e}")

if __name__ == "__main__":
    main()
