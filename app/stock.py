"""
Ubicaciones de stock unificadas.

Una "ubicacion" es un texto:
  - "local"          -> Product.current_stock
  - "matriz"         -> Product.stock_matriz
  - "sucursal:<id>"  -> fila en la tabla branch_stock (stock por sucursal)

Todas las operaciones de inventario (ventas, compras, transferencias,
ajustes) usan estas funciones para leer y mover stock, sin importar si
la ubicacion es una bodega o una sucursal.
"""
from app.extensions import db

LOCAL = "local"
MATRIZ = "matriz"
PREFIJO_SUCURSAL = "sucursal:"


def es_sucursal(ubicacion):
    return bool(ubicacion) and str(ubicacion).startswith(PREFIJO_SUCURSAL)


def branch_id_de(ubicacion):
    if es_sucursal(ubicacion):
        try:
            return int(str(ubicacion).split(":", 1)[1])
        except (ValueError, IndexError):
            return None
    return None


def clave_sucursal(branch_id):
    return f"{PREFIJO_SUCURSAL}{branch_id}"


def etiqueta_ubicacion(ubicacion):
    """Nombre legible de una ubicacion (consulta la sucursal si aplica)."""
    from app.models import Branch
    if ubicacion == LOCAL:
        return "Bodega Local"
    if ubicacion == MATRIZ:
        return "Bodega Matriz"
    bid = branch_id_de(ubicacion)
    if bid:
        b = Branch.query.get(bid)
        if b:
            return f"Sucursal {b.name}"
    return ubicacion or "—"


def listar_ubicaciones(solo_activas=True):
    """Devuelve [(clave, etiqueta)] de todas las ubicaciones."""
    from app.models import Branch
    items = [(LOCAL, "Bodega Local"), (MATRIZ, "Bodega Matriz")]
    q = Branch.query
    if solo_activas:
        q = q.filter(Branch.active.is_(True))
    for b in q.order_by(Branch.name).all():
        items.append((clave_sucursal(b.branch_id), f"Sucursal {b.name}"))
    return items


def claves_ubicaciones(solo_activas=True):
    return [c for c, _ in listar_ubicaciones(solo_activas)]


def es_ubicacion_valida(ubicacion):
    if ubicacion in (LOCAL, MATRIZ):
        return True
    from app.models import Branch
    bid = branch_id_de(ubicacion)
    return bool(bid and Branch.query.get(bid))


def _fila_sucursal(product, branch_id, crear=False):
    from app.models import BranchStock
    fila = BranchStock.query.filter_by(branch_id=branch_id, product_id=product.product_id).first()
    if fila is None and crear:
        fila = BranchStock(branch_id=branch_id, product_id=product.product_id, quantity=0)
        db.session.add(fila)
        db.session.flush()
    return fila


def stock_en(product, ubicacion):
    """Stock actual de un producto en la ubicacion indicada."""
    if ubicacion == MATRIZ:
        return product.stock_matriz or 0
    if ubicacion == LOCAL:
        return product.current_stock or 0
    bid = branch_id_de(ubicacion)
    if bid:
        fila = _fila_sucursal(product, bid)
        return fila.quantity if fila else 0
    return product.current_stock or 0


def sumar_stock(product, ubicacion, cantidad):
    if not cantidad or cantidad <= 0:
        return
    if ubicacion == MATRIZ:
        product.stock_matriz = (product.stock_matriz or 0) + cantidad
    elif ubicacion == LOCAL:
        product.current_stock = (product.current_stock or 0) + cantidad
    else:
        bid = branch_id_de(ubicacion)
        if bid:
            fila = _fila_sucursal(product, bid, crear=True)
            fila.quantity = (fila.quantity or 0) + cantidad


def restar_stock(product, ubicacion, cantidad):
    if not cantidad or cantidad <= 0:
        return
    if ubicacion == MATRIZ:
        product.stock_matriz = max(0, (product.stock_matriz or 0) - cantidad)
    elif ubicacion == LOCAL:
        product.current_stock = max(0, (product.current_stock or 0) - cantidad)
    else:
        bid = branch_id_de(ubicacion)
        if bid:
            fila = _fila_sucursal(product, bid, crear=True)
            fila.quantity = max(0, (fila.quantity or 0) - cantidad)


def stock_por_ubicaciones(product):
    """[(etiqueta, cantidad)] del producto en todas las ubicaciones (para vistas)."""
    resultado = []
    for clave, _etq in listar_ubicaciones(solo_activas=False):
        resultado.append((etiqueta_ubicacion(clave), clave, stock_en(product, clave)))
    return resultado


def mapa_stock_por_ubicacion():
    """{clave_ubicacion: {product_id: cantidad}} para poblar formularios (JS)."""
    from app.models import Product, BranchStock
    mapa = {LOCAL: {}, MATRIZ: {}}
    for pid, cs, sm in db.session.query(
            Product.product_id, Product.current_stock, Product.stock_matriz).all():
        mapa[LOCAL][pid] = cs or 0
        mapa[MATRIZ][pid] = sm or 0
    for clave, _etq in listar_ubicaciones():
        if clave.startswith(PREFIJO_SUCURSAL):
            mapa.setdefault(clave, {})
    for bs in BranchStock.query.all():
        mapa.setdefault(clave_sucursal(bs.branch_id), {})[bs.product_id] = bs.quantity or 0
    return mapa
