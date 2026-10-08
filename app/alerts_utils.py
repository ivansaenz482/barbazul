"""
Logica centralizada para calcular las alertas del sistema.
Se usa tanto en la pagina de Alertas como en la campanita de la barra superior
y en el script de correo, para que todos muestren siempre los mismos numeros.
"""
from datetime import datetime, timedelta, date
from app.models import Product, Sale, PurchaseInvoice


def get_low_stock_products():
    """Productos activos cuyo stock total (local + matriz) ya llego (o esta por debajo) del minimo"""
    return [
        p for p in Product.query.filter_by(active=True).all()
        if p.total_stock() <= p.min_stock
    ]


def get_overstock_products():
    """Productos activos con stock total por encima del maximo definido (posible sobre-compra)"""
    return [
        p for p in Product.query.filter_by(active=True).all()
        if p.max_stock and p.total_stock() >= p.max_stock
    ]


def get_overdue_credits():
    """Ventas a credito, no pagadas, cuya fecha de vencimiento ya paso"""
    hoy = datetime.now().date()
    ventas = Sale.query.filter(Sale.payment_type == "credito", Sale.status != "pagado").all()
    return [s for s in ventas if s.due_date is not None and s.due_date < hoy]


def get_upcoming_supplier_payments(days=15):
    """Facturas de compra a crédito próximas a vencer (dentro de `days` días, con saldo pendiente)"""
    hoy = datetime.now().date()
    limite = hoy + timedelta(days=days)
    invoices = PurchaseInvoice.query.filter(
        PurchaseInvoice.payment_type == "credito",
        PurchaseInvoice.due_date.isnot(None),
        PurchaseInvoice.due_date >= hoy,
        PurchaseInvoice.due_date <= limite,
        PurchaseInvoice.status != "pagado",
    ).all()
    return [inv for inv in invoices if inv.saldo_pendiente() > 0.009]


def get_overdue_supplier_payments():
    """Facturas de compra a crédito vencidas con saldo pendiente"""
    hoy = datetime.now().date()
    invoices = PurchaseInvoice.query.filter(
        PurchaseInvoice.payment_type == "credito",
        PurchaseInvoice.due_date.isnot(None),
        PurchaseInvoice.due_date < hoy,
        PurchaseInvoice.status != "pagado",
    ).all()
    return [inv for inv in invoices if inv.saldo_pendiente() > 0.009]


def get_alerts_summary():
    """Resumen compacto usado por la campanita de notificaciones"""
    return {
        "bajo_stock": len(get_low_stock_products()),
        "sobre_stock": len(get_overstock_products()),
        "creditos_vencidos": len(get_overdue_credits()),
        "pagos_proveedores_proximos": len(get_upcoming_supplier_payments()),
        "pagos_proveedores_vencidos": len(get_overdue_supplier_payments()),
    }


def get_upcoming_credits(days=7):
    """Ventas a credito con saldo, que vencen dentro de los proximos `days` dias."""
    hoy = datetime.now().date()
    limite = hoy + timedelta(days=days)
    ventas = Sale.query.filter(
        Sale.payment_type == "credito", Sale.status != "pagado",
        Sale.due_date.isnot(None), Sale.due_date >= hoy, Sale.due_date <= limite,
    ).all()
    return [s for s in ventas if s.saldo_pendiente() > 0.009]


def get_tax_reminder():
    """Proximo vencimiento de impuestos segun el RUC (SRI). Devuelve dict o None."""
    from app.models import SriConfig
    from app.sri_utils import dia_vencimiento
    cfg = SriConfig.actual()
    if not cfg or not cfg.ruc:
        return None
    dia = dia_vencimiento(cfg.ruc)
    hoy = datetime.now().date()
    if hoy.day <= dia:
        venc = date(hoy.year, hoy.month, dia)
    else:
        y, m = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        venc = date(y, m, dia)
    return {
        "dia": dia,
        "fecha": venc,
        "dias": (venc - hoy).days,
        "ambiente": cfg.ambiente_label() if hasattr(cfg, "ambiente_label") else "",
    }
