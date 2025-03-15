import fitz
import os
import sys
import pikepdf
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
from io import BytesIO
import tkinter as tk
from tkinter import filedialog

###############################################################################
#                          Función para comprimir imágenes                    #
###############################################################################
def compress_image(input_path, output_path, quality=40, max_size=(1024, 768)):
    """
    Comprime imágenes JPG/PNG a un tamaño y calidad específicos.
    """
    try:
        img = Image.open(input_path)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        img.save(output_path, quality=quality, optimize=True)
        print(f"Imagen comprimida: {output_path}")
    except Exception as e:
        print(f"Error al comprimir imagen: {e}")

###############################################################################
#                          Función para comprimir PDFs                        #
###############################################################################
def compress_pdf(input_path, output_path, quality=50):
    """
    Comprime un PDF reduciendo la calidad de las imágenes (usando PyMuPDF/fitz)
    y luego comprime los streams (usando pikepdf).
    """
    temp_output = output_path.replace('.pdf', '_temp.pdf')
    final_temp_output = output_path.replace('.pdf', '_final.pdf')

    # Procesar imágenes dentro del PDF con fitz
    with fitz.open(input_path) as doc:
        for page in doc:
            images = page.get_images(full=True)
            for img in images:
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                # Si la imagen tiene canal alfa, convertirla a RGB
                if pix.n > 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)

                img_pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                img_buffer = BytesIO()
                # Guardamos en JPG con la calidad indicada
                img_pil.save(img_buffer, format="JPEG", quality=quality, optimize=True)
                img_buffer.seek(0)
                page.replace_image(xref, stream=img_buffer.read())

        # Guardamos temporalmente
        doc.save(temp_output, garbage=4, deflate=True)

    # Comprimir con pikepdf
    with pikepdf.open(temp_output) as pdf:
        pdf.save(final_temp_output, compress_streams=True)

    os.remove(temp_output)

    # Si existe output_path, lo borramos para renombrar
    if os.path.exists(output_path):
        os.remove(output_path)
    os.rename(final_temp_output, output_path)

###############################################################################
#                            Función para dividir PDF                         #
###############################################################################
def split_pdf(input_path, output_folder):
    """
    Divide un PDF en 2 partes con la misma cantidad de páginas (lo más equilibrado posible).
    Devuelve la ruta de los dos PDFs resultantes.
    """
    reader = PdfReader(input_path)
    num_pages = len(reader.pages)
    half = (num_pages + 1) // 2 

    part1 = PdfWriter()
    part2 = PdfWriter()

    for i in range(num_pages):
        if i < half:
            part1.add_page(reader.pages[i])
        else:
            part2.add_page(reader.pages[i])

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    part1_path = os.path.join(output_folder, f"{base_name}_parte1.pdf")
    part2_path = os.path.join(output_folder, f"{base_name}_parte2.pdf")

    with open(part1_path, "wb") as f1:
        part1.write(f1)
    with open(part2_path, "wb") as f2:
        part2.write(f2)

    print(f"PDF dividido en: {part1_path} y {part2_path}")
    return part1_path, part2_path

###############################################################################
#                           Procesar archivo según extensión                  #
###############################################################################
def process_file(file_path, threshold=1*1024*1024):
    """
    Si es imagen, se comprime.
    Si es PDF, se comprime primero (con compresión más agresiva). 
    Si sigue pesando > 1MB, se divide en dos y se comprime cada parte 
    con la calidad que quieras (ej: la misma o diferente).
    """
    base, ext = os.path.splitext(file_path)
    ext = ext.lower()

    if ext in ['.jpg', '.jpeg', '.png']:
        # Comprimir imágenes
        compressed_file = f"{base}_compressed{ext}"
        compress_image(file_path, compressed_file, quality=40, max_size=(1024, 768))
        # Si tras comprimir sigue > 1MB, bajamos más la calidad o resolución
        if os.path.getsize(compressed_file) > threshold:
            compress_image(compressed_file, compressed_file, quality=30, max_size=(800, 600))

    elif ext == '.pdf':
        output_folder = os.path.dirname(file_path)
        base_name = os.path.splitext(os.path.basename(file_path))[0]


        compressed_pdf_path = os.path.join(output_folder, f"{base_name}_compressed.pdf")
        compress_pdf(file_path, compressed_pdf_path, quality=25)

        size_after = os.path.getsize(compressed_pdf_path)
        if size_after <= threshold:
            # Si ya está por debajo de 1MB, listo
            print(f"'{compressed_pdf_path}' está por debajo de 1MB ({size_after//1024} KB).")
        else:
            print(f"'{compressed_pdf_path}' aún pesa {size_after//1024} KB. Dividiendo en dos partes...")

            # 2) Dividir en dos
            part1_path, part2_path = split_pdf(compressed_pdf_path, output_folder)
            os.remove(compressed_pdf_path)  # Borramos el archivo grande

            # 3) Comprimir cada parte (puedes mantener la misma calidad o cambiarla)
            compress_pdf(part1_path, part1_path, quality=50)
            compress_pdf(part2_path, part2_path, quality=50)

            # Comprobar tamaños finales
            s1 = os.path.getsize(part1_path)
            s2 = os.path.getsize(part2_path)
            print(f"Parte1 => {part1_path} ({s1//1024} KB)")
            print(f"Parte2 => {part2_path} ({s2//1024} KB)")

    else:
        print(f"Formato no soportado: {file_path}")

###############################################################################
#                                   MAIN                                      #
###############################################################################
if __name__ == "__main__":
    files = []

    # Si el script recibe rutas por la línea de comandos, las toma de ahí
    if len(sys.argv) > 1:
        files = [f for f in sys.argv[1:] if os.path.isfile(f)]
    else:
        # Si no, abre una ventana de selección de archivos (PDF o imágenes)
        root = tk.Tk()
        root.withdraw()
        files = filedialog.askopenfilenames(
            title="Selecciona archivos para comprimir (PDF/Imágenes)",
            filetypes=[("PDF e Imágenes", "*.pdf;*.jpg;*.jpeg;*.png")]
        )

    # Procesa cada archivo seleccionado
    for file in files:
        process_file(file, threshold=1*1024*1024)