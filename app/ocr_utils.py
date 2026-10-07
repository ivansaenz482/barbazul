"""
Utilidades para extraer texto de facturas en imagen o PDF.

- Imagenes (jpg/png): se leen directo con Tesseract OCR.
- PDF con texto seleccionable (ej. facturas electronicas): se extrae el texto
  directamente, sin necesidad de OCR (mas rapido y preciso).
- PDF escaneado, o PDF con la capa de texto "corrupta" (un problema comun en
  algunas facturas electronicas del SRI, donde la fuente incrustada no mapea
  bien los caracteres): se convierte cada pagina a imagen y se le aplica OCR,
  igual que a una foto.
"""
import re
import pytesseract
import pdfplumber
from PIL import Image

try:
    import fitz  # PyMuPDF (opcional, necesario para PDFs escaneados o con texto corrupto)
    _PYMUPDF_AVAILABLE = True
except ImportError:
    _PYMUPDF_AVAILABLE = False


class OCRNotAvailableError(Exception):
    """Se lanza cuando Tesseract OCR (o PyMuPDF, si hace falta) no esta disponible."""
    pass


def configure_tesseract(tesseract_cmd: str):
    """Configura la ruta del ejecutable de Tesseract si se especifico en .env"""
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def extract_text_from_image(file_path: str) -> str:
    try:
        image = Image.open(file_path)
        texto = pytesseract.image_to_string(image, lang="spa+eng")
        return texto.strip()
    except pytesseract.TesseractNotFoundError:
        raise OCRNotAvailableError(
            "Tesseract OCR no está instalado o Windows no lo encuentra. "
            "Instálalo desde https://github.com/UB-Mannheim/tesseract/wiki "
            "y configura TESSERACT_CMD en tu archivo .env con la ruta del ejecutable."
        )


_PATRON_VALIDO = re.compile(r"[A-Za-zÀ-ÿ0-9\s.,:;()\-/%$#°ºª'\"\n]")
_PATRON_MOJIBAKE = re.compile(r"[ÂÃÎÏØÐ]{1,}|[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _calidad_texto(texto: str) -> float:
    """
    Estima que tan 'legible' es un texto extraido de un PDF, en promedio.
    """
    if not texto:
        return 0.0
    validos = len(_PATRON_VALIDO.findall(texto))
    return validos / len(texto)


def _tiene_texto_corrupto(texto: str, minimo_marcadores: int = 3) -> bool:
    """
    Detecta corrupcion LOCALIZADA (ej. solo el encabezado con el logo salio mal),
    que un promedio global no alcanza a detectar si el resto del documento es largo
    y legible. Busca simbolos tipicos de una fuente de PDF mal codificada
    (mojibake, como 'Â' repetido) o caracteres de control invisibles.
    """
    if not texto:
        return False
    return len(_PATRON_MOJIBAKE.findall(texto)) >= minimo_marcadores


def extract_text_from_pdf(file_path: str) -> str:
    texto_completo = []

    # 1. Intentar extraer texto directo (PDFs con capa de texto, ej. facturas electronicas)
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            texto_pagina = page.extract_text()
            if texto_pagina:
                texto_completo.append(texto_pagina)

    texto_extraido = "\n".join(texto_completo).strip()
    calidad = _calidad_texto(texto_extraido)
    corrupto = _tiene_texto_corrupto(texto_extraido)

    # Si el texto es largo, se ve legible EN PROMEDIO, y no tiene marcadores de
    # corrupcion localizada (ej. un encabezado con fuente mal codificada),
    # no hace falta OCR (mas rapido y preciso)
    if len(texto_extraido) > 20 and calidad >= 0.85 and not corrupto:
        return texto_extraido

    # 2. El PDF no tiene texto util (escaneado), o el texto tiene partes
    #    corruptas (problema de codificacion de fuente, comun en algunas
    #    facturas electronicas). En ambos casos, renderizar cada pagina como
    #    imagen y leerla con OCR, igual que una foto.
    if not _PYMUPDF_AVAILABLE:
        if texto_extraido and (calidad < 0.85 or corrupto):
            raise OCRNotAvailableError(
                "Este PDF tiene un problema de codificación de fuente (es común en algunas "
                "facturas electrónicas del SRI) que impide leerlo correctamente en modo texto. "
                "Para leerlo bien, instala el componente opcional PyMuPDF con "
                "'pip install PyMuPDF' y vuelve a intentarlo, o como alternativa, toma una foto "
                "o captura de pantalla de la factura y súbela como 'Imagen' en vez de 'PDF'."
            )
        raise OCRNotAvailableError(
            "Este PDF parece ser una imagen escaneada (sin texto seleccionable) y tu instalación "
            "no tiene el componente necesario para leerlo (PyMuPDF). "
            "Como alternativa, puedes tomarle una foto a la factura y subirla como 'Imagen' en vez de 'PDF', "
            "o ingresar los productos manualmente."
        )

    try:
        doc = fitz.open(file_path)
        textos_ocr = []
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            img_path = file_path + f"_page{page.number}.png"
            pix.save(img_path)
            textos_ocr.append(extract_text_from_image(img_path))
        doc.close()
        return "\n".join(textos_ocr).strip()
    except pytesseract.TesseractNotFoundError:
        raise OCRNotAvailableError(
            "Tesseract OCR no está instalado o Windows no lo encuentra. "
            "Instálalo desde https://github.com/UB-Mannheim/tesseract/wiki "
            "y configura TESSERACT_CMD en tu archivo .env con la ruta del ejecutable."
        )


def extract_text(file_path: str, extension: str) -> str:
    """Punto de entrada unico: detecta el tipo de archivo y aplica la estrategia correcta"""
    extension = extension.lower().lstrip(".")
    if extension == "pdf":
        return extract_text_from_pdf(file_path)
    elif extension in ("png", "jpg", "jpeg"):
        return extract_text_from_image(file_path)
    else:
        raise ValueError(f"Extensión no soportada para OCR: {extension}")
