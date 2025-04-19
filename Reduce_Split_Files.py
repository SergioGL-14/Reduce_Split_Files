#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import subprocess
import shutil
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from PyPDF2 import PdfReader, PdfWriter
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# =========================
# CONFIGURACIÓN GLOBAL
# =========================
PDF24_EXECUTABLES = [
    Path(r"C:\Program Files\PDF24\pdf24-DocTool.exe"),
    Path(r"C:\Program Files (x86)\PDF24\pdf24-DocTool.exe"),
]
DEFAULT_QUALITY = 85
MIN_QUALITY = 30
QUALITY_STEP = 5
DEFAULT_MAX_SIZE = (1024, 768)
SIZE_THRESHOLD = 1 * 1024 * 1024  # 1 MB
PDF_DPI = 144
PDF_IMAGE_QUALITY = 75

# =========================
# LOGGER
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# =========================
# UTILIDADES
# =========================
def find_pdf24_executable() -> Path:
    """Busca la ruta de PDF24 en el sistema Windows."""
    for path in PDF24_EXECUTABLES:
        if path.exists():
            logger.debug(f"PDF24 encontrado en: {path}")
            return path
    return None

PDF24_PATH = find_pdf24_executable()
if PDF24_PATH is None:
    logger.error("No se encontró PDF24. Instálalo o ajusta PDF24_EXECUTABLES.")
    sys.exit(1)

def is_supported_image(ext: str) -> bool:
    """Comprueba si la extensión es de imagen compatible."""
    return ext in {'.jpg', '.jpeg', '.png', '.heic', '.jfif'}

# =========================
# BLOQUE: COMPRESIÓN DE IMÁGENES
# =========================
def compress_image(
    input_path: Path,
    output_path: Path,
    quality: int = DEFAULT_QUALITY,
    max_size: tuple = DEFAULT_MAX_SIZE,
    threshold: int = SIZE_THRESHOLD
) -> bool:
    """
    Comprime una imagen JPEG/PNG hasta que quede por debajo de threshold.
    Devuelve True si tuvo éxito, False en caso contrario.
    """
    try:
        img = Image.open(input_path)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        current_quality = quality

        while current_quality >= MIN_QUALITY:
            img.save(output_path, quality=current_quality, optimize=True)
            size_kb = output_path.stat().st_size / 1024
            logger.debug(f"Intento calidad {current_quality}% → {size_kb:.2f} KB")
            if output_path.stat().st_size <= threshold:
                logger.info(f"✅ Imagen comprimida: {output_path} ({size_kb:.2f} KB)")
                return True
            current_quality -= QUALITY_STEP

        logger.warning(
            f"No se pudo reducir {output_path.name} sin bajar de {MIN_QUALITY}%"
        )
        return False

    except UnidentifiedImageError:
        logger.error(f"Formato no válido o corrupto: {input_path}")
    except PermissionError:
        logger.error(f"Acceso denegado: {input_path}")
    except Exception as e:
        logger.exception(f"Error al comprimir imagen: {e}")
    return False

def convert_heic_jfif_to_png(
    input_path: Path,
    max_size: tuple = DEFAULT_MAX_SIZE,
    threshold: int = SIZE_THRESHOLD,
    quality: int = 40
) -> Path:
    """
    Convierte HEIC/JFIF a PNG, luego comprime si supera threshold.
    Devuelve la ruta del archivo PNG o None si falló.
    """
    output_path = input_path.with_suffix('.png')
    try:
        img = Image.open(input_path).convert('RGB')
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        img.save(output_path, format='PNG', optimize=True)
        logger.info(f"Convertido a PNG: {output_path} ({output_path.stat().st_size/1024:.2f} KB)")

        if output_path.stat().st_size > threshold:
            compress_image(output_path, output_path, quality=quality, max_size=max_size, threshold=threshold)
        return output_path

    except UnidentifiedImageError:
        logger.error(f"No se pudo abrir {input_path}")
    except PermissionError:
        logger.error(f"Acceso denegado: {input_path}")
    except Exception as e:
        logger.exception(f"Error al convertir {input_path} a PNG: {e}")
    return None

# =========================
# BLOQUE: COMPRESIÓN DE PDFs
# =========================
def compress_pdf(
    input_pdf: Path,
    output_pdf: Path,
    dpi: int = PDF_DPI,
    image_quality: int = PDF_IMAGE_QUALITY
) -> bool:
    """
    Comprime un PDF usando PDF24. Devuelve True si tuvo éxito.
    """
    try:
        temp_pdf = output_pdf.parent / f"temp_{input_pdf.name}"
        shutil.copy2(input_pdf, temp_pdf)

        subprocess.run([
            str(PDF24_PATH),
            "-compress",
            "-dpi", str(dpi),
            "-imageQuality", str(image_quality),
            "-outputFile", str(output_pdf),
            str(temp_pdf)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if output_pdf.exists():
            size_kb = output_pdf.stat().st_size / 1024
            logger.info(f"✅ PDF comprimido: {output_pdf} ({size_kb:.2f} KB)")
            temp_pdf.unlink(missing_ok=True)
            return True

    except subprocess.CalledProcessError:
        logger.error("Fallo al ejecutar PDF24.")
    except PermissionError:
        logger.error(f"Acceso denegado: {input_pdf}")
    except Exception as e:
        logger.exception(f"Error al comprimir PDF: {e}")
    return False

def split_pdf_in_half(input_pdf: Path, out1: Path, out2: Path) -> bool:
    """
    Divide un PDF en dos partes iguales. Devuelve True si tuvo éxito.
    """
    try:
        reader = PdfReader(str(input_pdf))
        pages = reader.pages
        if len(pages) < 2:
            logger.warning(f"{input_pdf.name} tiene < 2 páginas; no se divide.")
            return False

        mid = len(pages) // 2
        w1, w2 = PdfWriter(), PdfWriter()
        for i, page in enumerate(pages):
            (w1 if i < mid else w2).add_page(page)

        for writer, path in [(w1, out1), (w2, out2)]:
            with open(path, 'wb') as f:
                writer.write(f)
            logger.info(f"PDF dividido: {path}")

        return True

    except Exception as e:
        logger.exception(f"Error al dividir PDF: {e}")
    return False

def handle_pdf_file(file_path: Path, threshold: int = SIZE_THRESHOLD):
    """
    Orquesta la compresión y, si hace falta, división de un PDF grande.
    """
    base = file_path.with_suffix('')
    reduced = base.with_name(base.name + "_REDUCIDO.pdf")

    if compress_pdf(file_path, reduced):
        if reduced.stat().st_size > threshold:
            p1 = base.with_name(base.name + "_REDUCIDO_part1.pdf")
            p2 = base.with_name(base.name + "_REDUCIDO_part2.pdf")
            if split_pdf_in_half(reduced, p1, p2):
                for part in (p1, p2):
                    if part.stat().st_size > threshold:
                        compress_pdf(part, part, dpi=100, image_quality=60)
            reduced.unlink(missing_ok=True)

# =========================
# BLOQUE: PROCESAMIENTO GENERAL
# =========================
def process_file(file_path: Path, threshold: int = SIZE_THRESHOLD):
    """
    Detecta tipo de archivo y lo procesa adecuadamente.
    """
    ext = file_path.suffix.lower()
    logger.info(f"Procesando: {file_path.name}")

    if ext in ['.jpg', '.jpeg', '.png']:
        dest = file_path.with_name(file_path.stem + "_REDUCIDO" + ext)
        compress_image(file_path, dest, threshold=threshold)

    elif ext in ['.heic', '.jfif']:
        convert_heic_jfif_to_png(file_path, threshold=threshold)

    elif ext == '.pdf':
        handle_pdf_file(file_path, threshold)

    else:
        logger.warning(f"Formato no soportado: {file_path.name}")

# =========================
# BLOQUE: INTERFAZ GRÁFICA
# =========================
class CompressionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("🗜️ Compresor de Archivos")
        self.geometry("500x300")
        self.configure(padx=20, pady=20)
        # Estilo ttk
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", padding=6, font=("Segoe UI", 10))
        style.configure("TLabel", font=("Segoe UI", 10))
        self._create_widgets()

    def _create_widgets(self):
        ttk.Label(self, text="Selecciona archivos para comprimir:").pack(pady=(0, 10))
        ttk.Button(self, text="Abrir Explorador", command=self.select_files).pack()
        self.progress = ttk.Progressbar(self, orient="horizontal", length=400, mode="determinate")
        self.progress.pack(pady=20)

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Archivos (PDF/Imágenes)",
            filetypes=[("PDF e Imágenes", "*.pdf;*.jpg;*.jpeg;*.png;*.heic;*.jfif")]
        )
        if not files:
            messagebox.showinfo("Info", "No se seleccionaron archivos.")
            return
        self._run_processing(files)

    def _run_processing(self, files):
        total = len(files)
        self.progress["maximum"] = total
        for idx, f in enumerate(files, 1):
            process_file(Path(f))
            self.progress["value"] = idx
            self.update_idletasks()
        messagebox.showinfo("¡Listo!", "Todos los archivos han sido procesados.")

# =========================
# PUNTO DE ENTRADA
# =========================
def main():
    if len(sys.argv) > 1:
        inputs = [Path(p) for p in sys.argv[1:] if Path(p).is_file()]
        for file in inputs:
            process_file(file)
        logger.info("Procesamiento por línea de comandos finalizado.")
    else:
        app = CompressionApp()
        app.mainloop()

if __name__ == "__main__":
    main()
