"""
Analiza el texto extraido de una factura (OCR/PDF) e intenta sacar los items:
descripcion, codigo, cantidad y costo unitario.

Es heuristico (las facturas varian), por eso el resultado se muestra en pantalla
para que el usuario lo revise/edite antes de confirmar la compra.
"""
import re

_NUM = re.compile(r"(?<!\S)\d[\d.,]*(?=\s|$)")

# Palabras que indican que la linea NO es un producto (encabezados/totales).
# Las "duras" descartan la linea; las "suaves" solo si aparecen 2 o mas.
_DUROS = [
    "subtotal", "sub total", "total", "iva", "i.v.a", "descuento", "base imponible",
    "ruc", "factura", "fecha", "clave de acceso", "autoriz", "ambiente", "razon social",
    "direccion", "telefono", "celular", "correo", "www", "email", "cajero", "condicion",
    "ciudad", "provincia", "punto de emision", "establecimiento", "comprobante",
]
_SUAVES = ["cantidad", "descripcion", "precio", "valor", "unidad", "codigo", "producto",
           "p.unit", "pvp", "pvp unitario", "cant."]


def _a_float(s):
    s = re.sub(r"[^\d.,-]", "", s or "")
    if not s:
        return None
    try:
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except ValueError:
        return None


def parsear_items(texto):
    """Devuelve una lista de dicts: {descripcion, codigo, cantidad, costo}."""
    resultados = []
    for linea in (texto or "").splitlines():
        l = " ".join(linea.split())
        if len(l) < 4:
            continue
        low = l.lower()
        if any(p in low for p in _DUROS):
            continue
        if sum(1 for p in _SUAVES if p in low) >= 2:
            continue

        nums = list(_NUM.finditer(l))
        if len(nums) < 2:
            continue

        primera = nums[0].start()
        desc = l[:primera].strip(" .:-|*#")
        valores = [_a_float(m.group()) for m in nums]
        valores = [v for v in valores if v is not None]
        if not desc or len(valores) < 2:
            continue

        # Cantidad: primer numero entero "pequeno" y sin separadores decimales
        cantidad = None
        for v, m in zip(valores, nums):
            txt = m.group()
            if "." not in txt and "," not in txt and v is not None and 1 <= v <= 100000:
                cantidad = int(v)
                break
        if cantidad is None:
            cantidad = 1

        # Costo: preferir el ultimo valor (suele ser el total) dividido por cantidad,
        # salvo que ya haya un costo unitario claro (penultimo). Usamos el penultimo
        # si existe y es menor que el ultimo.
        costo = valores[-1]
        if len(valores) >= 2 and valores[-2] and valores[-1] and valores[-2] < valores[-1] * 1.5:
            costo = valores[-2]
        elif cantidad > 1 and valores[-1]:
            costo = round(valores[-1] / cantidad, 4)

        # Codigo: primer token de la descripcion si parece codigo
        codigo = ""
        partes = desc.split()
        if partes and any(ch.isdigit() for ch in partes[0]) and len(partes[0]) <= 15:
            codigo = partes[0]
            desc = " ".join(partes[1:]).strip() or desc

        resultados.append({
            "descripcion": desc[:150],
            "codigo": codigo[:50],
            "cantidad": max(1, cantidad),
            "costo": round(float(costo or 0), 2),
        })

    return resultados
