import io
from datetime import datetime, date, timedelta
from calendar import monthrange
from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from app.models import Sale, Customer, User, DeliveryGuide, Payment, Product, Category, Supplier, PurchaseInvoice, SupplierPayment, Seller, Expense, Employee, CommissionPayment, SalesGoal
from app.extensions import db
from app.utils import role_required, perm_required

reports_bp = Blueprint("reports", __name__, url_prefix="/reportes")


def _obtener_grupos_ventas_por_cliente():
    """
    Logica compartida de filtros para el reporte de ventas por cliente.
    La usan tanto la vista HTML como la exportacion a Excel, para que
    ambas muestren siempre exactamente los mismos datos.
    """
    customer_id = request.args.get("customer_id", "").strip()
    payment_type = request.args.get("payment_type", "").strip()
    vendedor_id = request.args.get("vendedor_id", "").strip()
    bodega = request.args.get("bodega", "").strip()
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()

    query = Sale.query

    # El personal sin permiso de reporte de caja solo ve sus propias ventas; con permiso ve todas
    if not current_user.is_admin() and not current_user.can_view_reporte_caja():
        query = query.filter(Sale.user_id == current_user.user_id)

    if customer_id:
        query = query.filter(Sale.customer_id == int(customer_id))
    if payment_type in ("efectivo", "credito"):
        query = query.filter(Sale.payment_type == payment_type)
    if vendedor_id:
        query = query.filter(Sale.vendedor_id == int(vendedor_id))
    if bodega in ("local", "matriz"):
        query = query.filter(Sale.bodega == bodega)
    if desde:
        query = query.filter(Sale.sale_date >= datetime.strptime(desde, "%Y-%m-%d"))
    if hasta:
        query = query.filter(Sale.sale_date < datetime.strptime(hasta, "%Y-%m-%d").replace(hour=23, minute=59, second=59))

    sales = query.order_by(Customer.full_name, Sale.sale_date).join(Customer).all()

    grouped = {}
    for s in sales:
        key = s.customer_id
        if key not in grouped:
            grouped[key] = {"cliente": s.customer, "ventas": [], "total": 0.0, "utilidad": 0.0}
        grouped[key]["ventas"].append(s)
        grouped[key]["total"] += float(s.total_amount)
        grouped[key]["utilidad"] += s.utilidad()

    grupos = sorted(grouped.values(), key=lambda g: g["cliente"].full_name)
    grand_total = sum(g["total"] for g in grupos)
    grand_utilidad = sum(g["utilidad"] for g in grupos)

    return grupos, grand_total, grand_utilidad, customer_id, payment_type, desde, hasta, vendedor_id, bodega


@reports_bp.route("/ventas-por-cliente")
@login_required
@perm_required("can_view_reporte_caja")
def ventas_por_cliente():
    grupos, grand_total, grand_utilidad, customer_id, payment_type, desde, hasta, vendedor_id, bodega = _obtener_grupos_ventas_por_cliente()

    if current_user.is_admin():
        customers = Customer.query.order_by(Customer.full_name).all()
    else:
        customers = sorted({g["cliente"] for g in grupos}, key=lambda c: c.full_name)

    vendedores = Seller.query.order_by(Seller.name).all() if current_user.is_admin() else []

    return render_template(
        "reports_ventas_por_cliente.html",
        grupos=grupos,
        customers=customers,
        selected_customer=customer_id,
        selected_payment=payment_type,
        desde=desde,
        hasta=hasta,
        vendedores=vendedores,
        selected_vendedor=vendedor_id,
        selected_bodega=bodega,
        grand_total=grand_total,
        grand_utilidad=grand_utilidad,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


@reports_bp.route("/ventas-por-cliente/excel")
@login_required
@perm_required("can_view_reporte_caja")
def ventas_por_cliente_excel():
    grupos, grand_total, grand_utilidad, *_ = _obtener_grupos_ventas_por_cliente()

    wb = Workbook()
    ws = wb.active
    ws.title = "Ventas por Cliente"

    es_admin = current_user.is_admin()

    # --- Encabezado del reporte ---
    ws.merge_cells("A1:G1")
    ws["A1"] = "Reporte de Ventas por Cliente"
    ws["A1"].font = Font(size=14, bold=True, color="145369")

    ws.merge_cells("A2:G2")
    ws["A2"] = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {current_user.full_name}"
    ws["A2"].font = Font(size=9, italic=True, color="6b7c85")

    fila = 4
    encabezado_fill = PatternFill(start_color="145369", end_color="145369", fill_type="solid")
    encabezado_font = Font(bold=True, color="FFFFFF")

    for g in grupos:
        # Nombre del cliente como sub-titulo
        ws.merge_cells(f"A{fila}:G{fila}")
        celda_cliente = ws[f"A{fila}"]
        celda_cliente.value = f"{g['cliente'].full_name}" + (f" — {g['cliente'].cedula}" if g["cliente"].cedula else "")
        celda_cliente.font = Font(bold=True, size=11)
        celda_cliente.fill = PatternFill(start_color="e3e8ec", end_color="e3e8ec", fill_type="solid")
        fila += 1

        # Encabezados de columna
        columnas = ["Venta #", "Fecha", "Tipo", "Estado", "Vendedor", "Total"]
        if es_admin:
            columnas.append("Utilidad")
        for col_idx, titulo in enumerate(columnas, start=1):
            celda = ws.cell(row=fila, column=col_idx, value=titulo)
            celda.font = encabezado_font
            celda.fill = encabezado_fill
            celda.alignment = Alignment(horizontal="center")
        fila += 1

        # Filas de ventas
        for s in g["ventas"]:
            ws.cell(row=fila, column=1, value=s.sale_id)
            ws.cell(row=fila, column=2, value=s.sale_date.strftime("%d/%m/%Y"))
            ws.cell(row=fila, column=3, value="Contado" if s.payment_type == "efectivo" else "Crédito")
            ws.cell(row=fila, column=4, value=s.status.capitalize())
            ws.cell(row=fila, column=5, value=s.vendedor.name if s.vendedor else "—")
            ws.cell(row=fila, column=6, value=round(float(s.total_amount), 2))
            if es_admin:
                ws.cell(row=fila, column=7, value=round(s.utilidad(), 2))
            fila += 1

        # Subtotal del cliente
        ws.cell(row=fila, column=5, value="Subtotal:").font = Font(bold=True)
        ws.cell(row=fila, column=6, value=round(g["total"], 2)).font = Font(bold=True)
        if es_admin:
            ws.cell(row=fila, column=7, value=round(g["utilidad"], 2)).font = Font(bold=True)
        fila += 2  # deja una fila en blanco entre clientes

    # Total general
    ws.cell(row=fila, column=5, value="TOTAL GENERAL:").font = Font(bold=True, size=11)
    ws.cell(row=fila, column=6, value=round(grand_total, 2)).font = Font(bold=True, size=11)
    if es_admin:
        ws.cell(row=fila, column=7, value=round(grand_utilidad, 2)).font = Font(bold=True, size=11)

    # Ajustar ancho de columnas
    anchos = [10, 12, 10, 12, 26, 12, 12]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    nombre_archivo = f"ventas_por_cliente_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =====================================================================
# LIQUIDACIÓN POR VENDEDOR (diario / semanal / mensual / trimestral / anual)
# =====================================================================

def _rango_por_periodo(periodo, fecha_ref):
    """Devuelve (fecha_inicio, fecha_fin) segun el periodo elegido, ambas incluidas."""
    if periodo == "diario":
        return fecha_ref, fecha_ref

    if periodo == "semanal":
        inicio = fecha_ref - timedelta(days=fecha_ref.weekday())  # lunes de esa semana
        fin = inicio + timedelta(days=6)
        return inicio, fin

    if periodo == "mensual":
        inicio = fecha_ref.replace(day=1)
        ultimo_dia = monthrange(fecha_ref.year, fecha_ref.month)[1]
        fin = fecha_ref.replace(day=ultimo_dia)
        return inicio, fin

    if periodo == "trimestral":
        trimestre = (fecha_ref.month - 1) // 3
        mes_inicio = trimestre * 3 + 1
        mes_fin = mes_inicio + 2
        inicio = date(fecha_ref.year, mes_inicio, 1)
        ultimo_dia = monthrange(fecha_ref.year, mes_fin)[1]
        fin = date(fecha_ref.year, mes_fin, ultimo_dia)
        return inicio, fin

    if periodo == "anual":
        return date(fecha_ref.year, 1, 1), date(fecha_ref.year, 12, 31)

    # Por defecto: hoy
    return fecha_ref, fecha_ref


@reports_bp.route("/liquidacion")
@login_required
@role_required("administrador")
def liquidacion_vendedores():
    periodo = request.args.get("periodo", "diario")
    if periodo not in ("diario", "semanal", "mensual", "trimestral", "anual"):
        periodo = "diario"

    fecha_str = request.args.get("fecha", "").strip()
    try:
        fecha_ref = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else date.today()
    except ValueError:
        fecha_ref = date.today()

    vendedor_id = request.args.get("vendedor_id", "").strip()

    fecha_inicio, fecha_fin = _rango_por_periodo(periodo, fecha_ref)

    # Solo cuentan las ventas ya liquidadas (Factura/Nota de Venta reales, no proformas pendientes)
    query = Sale.query.filter(
        Sale.liquidada == True,  # noqa: E712
        Sale.liquidated_at >= datetime.combine(fecha_inicio, datetime.min.time()),
        Sale.liquidated_at <= datetime.combine(fecha_fin, datetime.max.time()),
    )

    # El personal solo ve su propia liquidacion; el administrador ve a todos o filtra por uno
    if not current_user.is_admin():
        query = query.filter(Sale.user_id == current_user.user_id)
    elif vendedor_id:
        query = query.filter(Sale.user_id == int(vendedor_id))

    sales = query.all()

    # Agrupar por vendedor
    grouped = {}
    for s in sales:
        key = s.user_id
        if key not in grouped:
            grouped[key] = {
                "vendedor": s.seller,
                "num_ventas": 0,
                "total_ventas": 0.0,
                "total_utilidad": 0.0,
                "canceladas": 0,
                "pendientes": 0,
                "facturas": 0,
                "notas_venta": 0,
            }
        g = grouped[key]
        g["num_ventas"] += 1
        g["total_ventas"] += float(s.total_amount)
        g["total_utilidad"] += s.utilidad()
        if s.status == "pagado":
            g["canceladas"] += 1
        else:
            g["pendientes"] += 1
        if s.document_type == "factura":
            g["facturas"] += 1
        else:
            g["notas_venta"] += 1

    grupos = sorted(grouped.values(), key=lambda g: g["vendedor"].full_name)
    grand_total_ventas = sum(g["total_ventas"] for g in grupos)
    grand_total_utilidad = sum(g["total_utilidad"] for g in grupos)

    # Detalle de cada venta (cliente, forma de pago, estado) dentro del periodo/vendedor filtrado
    detalle_ventas = sorted(sales, key=lambda s: s.sale_date)

    # Guias de remision pendientes de entrega (emitidas dentro del mismo rango de fechas)
    guias_query = DeliveryGuide.query.filter(
        DeliveryGuide.entregada == False,  # noqa: E712
        DeliveryGuide.fecha_emision >= fecha_inicio,
        DeliveryGuide.fecha_emision <= fecha_fin,
    )
    if not current_user.is_admin():
        guias_query = guias_query.filter(DeliveryGuide.created_by == current_user.user_id)
    elif vendedor_id:
        guias_query = guias_query.filter(DeliveryGuide.created_by == int(vendedor_id))

    guias_pendientes = guias_query.order_by(DeliveryGuide.fecha_emision).all()

    vendedores = User.query.order_by(User.full_name).all() if current_user.is_admin() else []

    return render_template(
        "reports_liquidacion.html",
        grupos=grupos,
        detalle_ventas=detalle_ventas,
        guias_pendientes=guias_pendientes,
        periodo=periodo,
        fecha=fecha_ref.strftime("%Y-%m-%d"),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        vendedores=vendedores,
        selected_vendedor=vendedor_id,
        grand_total_ventas=grand_total_ventas,
        grand_total_utilidad=grand_total_utilidad,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


# =====================================================================
# CIERRE DE CAJA (resumen general del negocio, desglosado por metodo de pago)
# =====================================================================

@reports_bp.route("/cierre-caja")
@login_required
@perm_required("can_view_reporte_caja")
def cierre_caja():
    periodo = request.args.get("periodo", "diario")
    if periodo not in ("diario", "semanal", "mensual", "trimestral", "anual"):
        periodo = "diario"

    fecha_str = request.args.get("fecha", "").strip()
    try:
        fecha_ref = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else date.today()
    except ValueError:
        fecha_ref = date.today()

    fecha_inicio, fecha_fin = _rango_por_periodo(periodo, fecha_ref)
    inicio_dt = datetime.combine(fecha_inicio, datetime.min.time())
    fin_dt = datetime.combine(fecha_fin, datetime.max.time())

    # Ventas liquidadas (reales, no proformas pendientes) dentro del periodo
    ventas_query = Sale.query.filter(
        Sale.liquidada == True,  # noqa: E712
        Sale.liquidated_at >= inicio_dt,
        Sale.liquidated_at <= fin_dt,
    )
    if not current_user.is_admin() and not current_user.can_view_reporte_caja():
        ventas_query = ventas_query.filter(Sale.user_id == current_user.user_id)
    ventas = ventas_query.all()

    total_vendido = sum(float(s.total_amount) for s in ventas)
    total_utilidad = sum(s.utilidad() for s in ventas)
    total_efectivo_vendido = sum(float(s.total_amount) for s in ventas if s.payment_type == "efectivo")
    total_credito_vendido = sum(float(s.total_amount) for s in ventas if s.payment_type == "credito")
    num_ventas = len(ventas)

    # Pagos cobrados dentro del periodo (independiente de cuando se hizo la venta original),
    # desglosados por metodo de pago -- esto es lo que realmente "entro a caja"
    pagos_query = Payment.query.filter(
        Payment.payment_date >= inicio_dt,
        Payment.payment_date <= fin_dt,
    )
    if not current_user.is_admin() and not current_user.can_view_reporte_caja():
        pagos_query = pagos_query.join(Sale).filter(Sale.user_id == current_user.user_id)
    pagos = pagos_query.all()

    por_metodo = {}
    for p in pagos:
        metodo = p.payment_method or "otro"
        por_metodo.setdefault(metodo, 0.0)
        por_metodo[metodo] += float(p.amount)

    total_cobrado = sum(por_metodo.values())

    # Cuentas por cobrar pendientes generadas en este periodo (ventas a credito no pagadas aun)
    pendientes = [s for s in ventas if s.payment_type == "credito" and s.status != "pagado"]
    total_pendiente = sum(s.saldo_pendiente() for s in pendientes)

    return render_template(
        "reports_cierre_caja.html",
        periodo=periodo,
        fecha=fecha_ref.strftime("%Y-%m-%d"),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        num_ventas=num_ventas,
        total_vendido=total_vendido,
        total_utilidad=total_utilidad,
        total_efectivo_vendido=total_efectivo_vendido,
        total_credito_vendido=total_credito_vendido,
        por_metodo=por_metodo,
        total_cobrado=total_cobrado,
        total_pendiente=total_pendiente,
        pendientes=pendientes,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


# =====================================================================
# ESTADO DE CUENTA — CLIENTES DE CRÉDITO (con abonos y deuda actual)
# =====================================================================

@reports_bp.route("/clientes-credito")
@login_required
@role_required("administrador")
def estado_cuenta_clientes():
    customer_id = request.args.get("customer_id", "").strip()

    # El toggle de utilidad solo tiene efecto real si el usuario es administrador;
    # el personal nunca ve utilidad, aunque intente forzar el parametro por URL.
    ver_utilidad = request.args.get("ver_utilidad", "0") == "1" and current_user.is_admin()

    query = Customer.query.filter_by(customer_type="credito", active=True)
    if customer_id:
        query = query.filter(Customer.customer_id == int(customer_id))
    clientes = query.order_by(Customer.full_name).all()

    estado_cuentas = []
    for c in clientes:
        ventas_credito = [s for s in c.sales if s.payment_type == "credito" and s.liquidada]
        if not ventas_credito:
            continue

        ventas_info = []
        total_credito = 0.0
        total_abonado = 0.0
        total_utilidad_cliente = 0.0

        for s in sorted(ventas_credito, key=lambda x: x.sale_date):
            abonos = sorted(s.payments, key=lambda p: p.payment_date)
            saldo = s.saldo_pendiente()
            total_credito += float(s.total_amount)
            total_abonado += s.pagado_total()
            total_utilidad_cliente += s.utilidad()
            ventas_info.append({
                "venta": s,
                "abonos": abonos,
                "saldo": saldo,
            })

        estado_cuentas.append({
            "cliente": c,
            "ventas": ventas_info,
            "total_credito": total_credito,
            "total_abonado": total_abonado,
            "saldo_actual": total_credito - total_abonado,
            "total_utilidad": total_utilidad_cliente,
        })

    todos_los_clientes_credito = Customer.query.filter_by(customer_type="credito", active=True).order_by(Customer.full_name).all()

    return render_template(
        "reports_estado_cuenta.html",
        estado_cuentas=estado_cuentas,
        clientes=todos_los_clientes_credito,
        selected_customer=customer_id,
        ver_utilidad=ver_utilidad,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


# =====================================================================
# INVENTARIO TOTAL POR CATEGORÍAS (con filtro de categorías al imprimir)
# =====================================================================

def _stock_segun_bodega(product, bodega):
    """Devuelve el stock segun la bodega elegida: local, matriz o ambas (total)."""
    if bodega == "local":
        return product.current_stock or 0
    if bodega == "matriz":
        return product.stock_matriz or 0
    return product.total_stock()


def _obtener_inventario_por_categorias():
    """
    Comparte la logica de filtros entre la vista HTML y el Excel:
    devuelve (categorias_seleccionadas, solo_con_stock, ver_costo, ver_precio,
    ver_valor_costo, ver_valor_venta, bodega, productos_agrupados, categorias).
    """
    cats = request.args.getlist("categorias")
    bodega = request.args.get("bodega", "ambas")
    if bodega not in ("ambas", "local", "matriz"):
        bodega = "ambas"
    solo_con_stock = request.args.get("solo_con_stock", "0") == "1"
    ver_costo = request.args.get("ver_costo", "0") == "1"
    ver_precio = request.args.get("ver_precio", "0") == "1"
    ver_valor_costo = request.args.get("ver_valor_costo", "0") == "1"
    ver_valor_venta = request.args.get("ver_valor_venta", "0") == "1"

    query = Product.query
    if solo_con_stock:
        query = query.filter(Product.active == True)  # noqa: E712

    if cats:
        try:
            ids = [int(c) for c in cats]
            query = query.filter(Product.category_id.in_(ids))
        except ValueError:
            ids = []
    else:
        ids = []

    productos = query.order_by(Product.name).all()

    # Filtrar "solo con stock" a nivel de python (activos + stock > 0 segun bodega)
    if solo_con_stock:
        productos = [p for p in productos if _stock_segun_bodega(p, bodega) > 0]

    # Agrupar por categoria
    grupos = {}
    for p in productos:
        key = p.category_id if p.category_id else 0
        if key not in grupos:
            grupos[key] = {"categoria": p.category, "productos": [], "total_costo": 0.0, "total_venta": 0.0}
        grupos[key]["productos"].append(p)
        stock = _stock_segun_bodega(p, bodega)
        grupos[key]["total_costo"] += float(p.cost_price or 0) * stock
        grupos[key]["total_venta"] += float(p.sale_price or 0) * stock

    ordenados = sorted(grupos.values(), key=lambda g: g["categoria"].name if g["categoria"] else "Sin categoría")
    grand_total_costo = sum(g["total_costo"] for g in ordenados)
    grand_total_venta = sum(g["total_venta"] for g in ordenados)
    grand_unidades = sum(_stock_segun_bodega(p, bodega) for g in ordenados for p in g["productos"])

    categorias = Category.query.order_by(Category.name).all()

    return (ordenados, grand_total_costo, grand_total_venta, grand_unidades, ids,
            solo_con_stock, ver_costo, ver_precio, ver_valor_costo, ver_valor_venta, bodega, categorias)


@reports_bp.route("/inventario")
@login_required
@role_required("administrador")
def inventario_por_categorias():
    (grupos, grand_costo, grand_venta, grand_unidades, ids, solo_con_stock,
     ver_costo, ver_precio, ver_valor_costo, ver_valor_venta, bodega, categorias) = _obtener_inventario_por_categorias()

    return render_template(
        "reports_inventario.html",
        grupos=grupos,
        grand_total_costo=grand_costo,
        grand_total_venta=grand_venta,
        grand_unidades=grand_unidades,
        categorias=categorias,
        selected_categorias=[str(i) for i in ids],
        solo_con_stock=solo_con_stock,
        ver_costo=ver_costo,
        ver_precio=ver_precio,
        ver_valor_costo=ver_valor_costo,
        ver_valor_venta=ver_valor_venta,
        bodega=bodega,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


@reports_bp.route("/inventario/excel")
@login_required
@role_required("administrador")
def inventario_por_categorias_excel():
    (grupos, grand_costo, grand_venta, grand_unidades, *_, ver_costo, ver_precio,
     ver_valor_costo, ver_valor_venta, bodega, _cat) = _obtener_inventario_por_categorias()

    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario por Categorías"

    ws.merge_cells("A1:G1")
    ws["A1"] = "Inventario Total por Categorías"
    ws["A1"].font = Font(size=14, bold=True, color="145369")

    ws.merge_cells("A2:G2")
    ws["A2"] = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {current_user.full_name}"
    ws["A2"].font = Font(size=9, italic=True, color="6b7c85")

    etiqueta_bodega = {"ambas": "Ambas bodegas", "local": "Bodega Local", "matriz": "Bodega Matriz"}.get(bodega, "Ambas bodegas")
    ws.merge_cells("A3:G3")
    ws["A3"] = f"Bodega: {etiqueta_bodega}"
    ws["A3"].font = Font(size=9, italic=True, color="6b7c85")

    fila = 5
    encabezado_fill = PatternFill(start_color="145369", end_color="145369", fill_type="solid")
    encabezado_font = Font(bold=True, color="FFFFFF")
    columnas = ["Código", "Producto", "Unidad", "Stock"]
    if ver_costo:
        columnas.append("Costo")
    if ver_precio:
        columnas.append("Precio Venta")
    if ver_valor_costo:
        columnas.append("Valor Costo")
    if ver_valor_venta:
        columnas.append("Valor Venta")
    num_cols = len(columnas)
    ultima_letra = get_column_letter(num_cols)

    for g in grupos:
        nombre_cat = g["categoria"].name if g["categoria"] else "Sin categoría"
        ws.merge_cells(f"A{fila}:{ultima_letra}{fila}")
        celda = ws[f"A{fila}"]
        celda.value = f"{nombre_cat} — {len(g['productos'])} producto(s)"
        celda.font = Font(bold=True, size=11)
        celda.fill = PatternFill(start_color="e3e8ec", end_color="e3e8ec", fill_type="solid")
        fila += 1

        for col_idx, titulo in enumerate(columnas, start=1):
            celda = ws.cell(row=fila, column=col_idx, value=titulo)
            celda.font = encabezado_font
            celda.fill = encabezado_fill
            celda.alignment = Alignment(horizontal="center")
        fila += 1

        for p in g["productos"]:
            ws.cell(row=fila, column=1, value=p.sku or f"PROD-{p.product_id}")
            ws.cell(row=fila, column=2, value=p.name)
            ws.cell(row=fila, column=3, value=p.unit_measure or "unidad")
            ws.cell(row=fila, column=4, value=_stock_segun_bodega(p, bodega))
            col = 5
            if ver_costo:
                ws.cell(row=fila, column=col, value=round(float(p.cost_price or 0), 2)); col += 1
            if ver_precio:
                ws.cell(row=fila, column=col, value=round(float(p.sale_price or 0), 2)); col += 1
            if ver_valor_costo:
                ws.cell(row=fila, column=col, value=round(float(p.cost_price or 0) * _stock_segun_bodega(p, bodega), 2)); col += 1
            if ver_valor_venta:
                ws.cell(row=fila, column=col, value=round(float(p.sale_price or 0) * _stock_segun_bodega(p, bodega), 2)); col += 1
            fila += 1

        ws.cell(row=fila, column=2, value="Subtotal categoría:").font = Font(bold=True)
        col = 5
        if ver_costo:
            col += 1
        if ver_precio:
            col += 1
        if ver_valor_costo:
            ws.cell(row=fila, column=col, value=round(g["total_costo"], 2)).font = Font(bold=True); col += 1
        if ver_valor_venta:
            ws.cell(row=fila, column=col, value=round(g["total_venta"], 2)).font = Font(bold=True); col += 1
        fila += 2

    ws.cell(row=fila, column=2, value="TOTAL GENERAL:").font = Font(bold=True, size=11)
    ws.cell(row=fila, column=4, value=grand_unidades).font = Font(bold=True, size=11)
    col = 5
    if ver_costo:
        col += 1
    if ver_precio:
        col += 1
    if ver_valor_costo:
        ws.cell(row=fila, column=col, value=round(grand_costo, 2)).font = Font(bold=True, size=11); col += 1
    if ver_valor_venta:
        ws.cell(row=fila, column=col, value=round(grand_venta, 2)).font = Font(bold=True, size=11); col += 1

    anchos = [14, 40, 10, 12, 10, 12, 12, 12]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    nombre_archivo = f"inventario_por_categorias_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =====================================================================
# REPORTE DE PRECIOS POR PRODUCTO (contado / credito / mayorista)
# =====================================================================

def _obtener_productos_precios():
    """Filtros compartidos del reporte de precios (HTML y Excel)."""
    cats = request.args.getlist("categoria")
    q = request.args.get("q", "").strip()
    solo_activos = request.args.get("activos", "1") == "1"

    query = Product.query
    if solo_activos:
        query = query.filter(Product.active == True)  # noqa: E712

    ids = []
    if cats:
        try:
            ids = [int(c) for c in cats]
            query = query.filter(Product.category_id.in_(ids))
        except ValueError:
            ids = []

    if q:
        like = f"%{q}%"
        query = query.filter(
            (Product.name.ilike(like)) | (Product.sku.ilike(like)) | (Product.barcode.ilike(like))
        )

    productos = query.order_by(Product.name).all()
    categorias = Category.query.order_by(Category.name).all()
    return productos, categorias, ids, q, solo_activos


@reports_bp.route("/precios")
@login_required
@role_required("administrador")
def precios_productos():
    productos, categorias, ids, q, solo_activos = _obtener_productos_precios()
    return render_template(
        "reports_precios.html",
        productos=productos,
        categorias=categorias,
        selected_categorias=[str(i) for i in ids],
        q=q,
        solo_activos=solo_activos,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


@reports_bp.route("/precios/excel")
@login_required
@role_required("administrador")
def precios_productos_excel():
    productos, categorias, ids, q, solo_activos = _obtener_productos_precios()

    wb = Workbook()
    ws = wb.active
    ws.title = "Precios"

    ws.merge_cells("A1:G1")
    ws["A1"] = "Lista de Precios por Producto"
    ws["A1"].font = Font(size=14, bold=True, color="145369")

    ws.merge_cells("A2:G2")
    ws["A2"] = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {current_user.full_name}"
    ws["A2"].font = Font(size=9, italic=True, color="6b7c85")

    columnas = ["Código", "Producto", "Categoría", "Costo", "Contado", "Crédito", "Mayorista"]
    fila = 4
    encabezado_fill = PatternFill(start_color="145369", end_color="145369", fill_type="solid")
    encabezado_font = Font(bold=True, color="FFFFFF")
    for col_idx, titulo in enumerate(columnas, start=1):
        celda = ws.cell(row=fila, column=col_idx, value=titulo)
        celda.font = encabezado_font
        celda.fill = encabezado_fill
        celda.alignment = Alignment(horizontal="center")
    fila += 1

    for p in productos:
        ws.cell(row=fila, column=1, value=p.sku or f"PROD-{p.product_id}")
        ws.cell(row=fila, column=2, value=p.name)
        ws.cell(row=fila, column=3, value=p.category.name if p.category else "Sin categoría")
        ws.cell(row=fila, column=4, value=round(float(p.cost_price or 0), 2))
        ws.cell(row=fila, column=5, value=round(float(p.sale_price or 0), 2))
        ws.cell(row=fila, column=6, value=round(float(p.price_credito or 0), 2))
        ws.cell(row=fila, column=7, value=round(float(p.price_mayorista or 0), 2))
        fila += 1

    anchos = [16, 42, 18, 10, 10, 10, 10]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    nombre = f"lista_precios_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =====================================================================
# REPORTE DE PAGOS A PROVEEDORES (con menú de selección)
# =====================================================================
def _obtener_pagos_proveedores():
    """
    Lógica compartida para el reporte de pagos a proveedores.
    Devuelve los filtros aplicados, los pagos agrupados por proveedor y los totales.
    """
    supplier_id = request.args.get("supplier_id", "").strip()
    metodo = request.args.get("metodo", "").strip()
    estado = request.args.get("estado", "").strip()
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()

    # Filtros de columnas para imprimir/verificar solo lo que se desee
    ver_factura = request.args.get("ver_factura", "1") == "1"
    ver_referencia = request.args.get("ver_referencia", "1") == "1"
    ver_metodo = request.args.get("ver_metodo", "1") == "1"
    ver_vendedor = request.args.get("ver_vendedor", "1") == "1"
    ver_nota = request.args.get("ver_nota", "0") == "1"

    query = SupplierPayment.query.join(PurchaseInvoice)

    if supplier_id:
        query = query.filter(PurchaseInvoice.supplier_id == int(supplier_id))
    if metodo in ("efectivo", "cheque", "transferencia", "tarjeta", "otro"):
        query = query.filter(SupplierPayment.payment_method == metodo)
    if desde:
        query = query.filter(SupplierPayment.payment_date >= datetime.strptime(desde, "%Y-%m-%d"))
    if hasta:
        query = query.filter(SupplierPayment.payment_date < datetime.strptime(hasta, "%Y-%m-%d").replace(hour=23, minute=59, second=59))

    pagos = query.order_by(PurchaseInvoice.supplier_id, SupplierPayment.payment_date).all()

    if estado == "credito":
        pagos = [p for p in pagos if p.invoice.payment_type == "credito"]
    elif estado == "contado":
        pagos = [p for p in pagos if p.invoice.payment_type == "efectivo"]

    grouped = {}
    for p in pagos:
        key = p.invoice.supplier_id
        if key not in grouped:
            grouped[key] = {"proveedor": p.invoice.supplier, "pagos": [], "total": 0.0}
        grouped[key]["pagos"].append(p)
        grouped[key]["total"] += float(p.amount)

    grupos = sorted(grouped.values(), key=lambda g: g["proveedor"].name)
    grand_total = sum(g["total"] for g in grupos)

    suppliers = Supplier.query.order_by(Supplier.name).all()

    return (grupos, grand_total, supplier_id, metodo, estado, desde, hasta,
            ver_factura, ver_referencia, ver_metodo, ver_vendedor, ver_nota, suppliers)


@reports_bp.route("/pagos-proveedores")
@login_required
@role_required("administrador")
def pagos_proveedores():
    (grupos, grand_total, supplier_id, metodo, estado, desde, hasta,
     ver_factura, ver_referencia, ver_metodo, ver_vendedor, ver_nota, suppliers) = _obtener_pagos_proveedores()

    return render_template(
        "reports_pagos_proveedores.html",
        grupos=grupos,
        grand_total=grand_total,
        suppliers=suppliers,
        selected_supplier=supplier_id,
        selected_metodo=metodo,
        selected_estado=estado,
        desde=desde,
        hasta=hasta,
        ver_factura=ver_factura,
        ver_referencia=ver_referencia,
        ver_metodo=ver_metodo,
        ver_vendedor=ver_vendedor,
        ver_nota=ver_nota,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


@reports_bp.route("/pagos-proveedores/excel")
@login_required
@role_required("administrador")
def pagos_proveedores_excel():
    (grupos, grand_total, *_, ver_factura, ver_referencia, ver_metodo, ver_vendedor, ver_nota, _sup) = _obtener_pagos_proveedores()

    wb = Workbook()
    ws = wb.active
    ws.title = "Pagos a Proveedores"

    ws.merge_cells("A1:F1")
    ws["A1"] = "Reporte de Pagos a Proveedores"
    ws["A1"].font = Font(size=14, bold=True, color="145369")

    ws.merge_cells("A2:F2")
    ws["A2"] = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {current_user.full_name}"
    ws["A2"].font = Font(size=9, italic=True, color="6b7c85")

    fila = 4
    encabezado_fill = PatternFill(start_color="145369", end_color="145369", fill_type="solid")
    encabezado_font = Font(bold=True, color="FFFFFF")

    for g in grupos:
        ws.merge_cells(f"A{fila}:F{fila}")
        celda = ws[f"A{fila}"]
        celda.value = f"{g['proveedor'].name}" + (f" — RUC {g['proveedor'].ruc}" if g["proveedor"].ruc else "")
        celda.font = Font(bold=True, size=11)
        celda.fill = PatternFill(start_color="e3e8ec", end_color="e3e8ec", fill_type="solid")
        fila += 1

        columnas = ["Fecha", "Monto"]
        if ver_factura:
            columnas.append("Factura")
        if ver_referencia:
            columnas.append("Comprobante")
        if ver_metodo:
            columnas.append("Método")
        if ver_vendedor:
            columnas.append("Registrado por")
        if ver_nota:
            columnas.append("Nota")
        num_cols = len(columnas)

        for col_idx, titulo in enumerate(columnas, start=1):
            celda = ws.cell(row=fila, column=col_idx, value=titulo)
            celda.font = encabezado_font
            celda.fill = encabezado_fill
            celda.alignment = Alignment(horizontal="center")
        fila += 1

        for p in g["pagos"]:
            col = 1
            ws.cell(row=fila, column=col, value=p.payment_date.strftime("%d/%m/%Y")); col += 1
            ws.cell(row=fila, column=col, value=round(float(p.amount), 2)); col += 1
            if ver_factura:
                ws.cell(row=fila, column=col, value=f"#{p.invoice.invoice_id}" + (f" {p.invoice.invoice_number}" if p.invoice.invoice_number else "")); col += 1
            if ver_referencia:
                ws.cell(row=fila, column=col, value=p.receipt_number or ""); col += 1
            if ver_metodo:
                ws.cell(row=fila, column=col, value=p.metodo_label()); col += 1
            if ver_vendedor:
                ws.cell(row=fila, column=col, value=p.registered_by_user.full_name if p.registered_by_user else ""); col += 1
            if ver_nota:
                ws.cell(row=fila, column=col, value=p.notes or ""); col += 1
            fila += 1

        ws.cell(row=fila, column=1, value="Subtotal proveedor:").font = Font(bold=True)
        ws.cell(row=fila, column=2, value=round(g["total"], 2)).font = Font(bold=True)
        fila += 2

    ws.cell(row=fila, column=1, value="TOTAL GENERAL:").font = Font(bold=True, size=11)
    ws.cell(row=fila, column=2, value=round(grand_total, 2)).font = Font(bold=True, size=11)

    anchos = [12, 12, 14, 16, 16, 20]
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    nombre_archivo = f"pagos_proveedores_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nombre_archivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =====================================================================
# RECOMENDACIONES AL DUENO (que producto ofertar / vender mas)
# =====================================================================

@reports_bp.route("/recomendaciones")
@login_required
@role_required("administrador")
def recomendaciones():
    dias = request.args.get("dias", "30")
    try:
        dias = int(dias)
    except (TypeError, ValueError):
        dias = 30
    if dias not in (7, 15, 30, 60, 90):
        dias = 30
    desde = datetime.now() - timedelta(days=dias)

    ventas = Sale.query.filter(Sale.liquidada == True, Sale.sale_date >= desde).all()  # noqa: E712

    # Agregado por producto en el periodo
    agg = {}
    for s in ventas:
        for d in s.details:
            e = agg.setdefault(d.product_id, {"units": 0, "revenue": 0.0, "profit": 0.0})
            e["units"] += d.quantity
            e["revenue"] += float(d.unit_price) * d.quantity
            e["profit"] += (float(d.unit_price) - float(d.unit_cost)) * d.quantity

    productos = Product.query.filter_by(active=True).all()
    info = []
    for p in productos:
        a = agg.get(p.product_id, {"units": 0, "revenue": 0.0, "profit": 0.0})
        costo = float(p.cost_price or 0)
        precio = float(p.sale_price or 0)
        margen = ((precio - costo) / costo * 100) if costo > 0 else 0
        info.append({
            "product": p, "units": a["units"], "revenue": a["revenue"], "profit": a["profit"],
            "margen": margen, "stock": p.total_stock(), "min_stock": p.min_stock or 0,
            "costo": costo, "precio": precio,
        })

    n = len(info) or 1
    unidades_prom = sum(x["units"] for x in info) / n
    margen_prom = sum(x["margen"] for x in info) / n

    top_rentables = sorted(info, key=lambda x: -x["profit"])[:8]
    top_vendidos = sorted(info, key=lambda x: -x["units"])[:8]

    # Ofertar mas: buen margen y poca venta, con stock disponible
    umbral_margen = max(margen_prom, 15)
    ofertar = [x for x in info if x["stock"] > 0 and x["margen"] >= umbral_margen and x["units"] < unidades_prom]
    ofertar = sorted(ofertar, key=lambda x: (-x["margen"], x["units"]))[:8]

    # Reponer: se vende bien y el stock esta bajo
    reponer = [x for x in info if x["units"] >= unidades_prom and (x["stock"] <= x["min_stock"] or x["stock"] < x["units"])]
    reponer = sorted(reponer, key=lambda x: -x["units"])[:8]

    # Estancados: tienen stock pero no se vendieron en el periodo
    estancados = [x for x in info if x["stock"] > 0 and x["units"] == 0]
    estancados = sorted(estancados, key=lambda x: -x["stock"])[:8]

    total_ventas = sum(x["revenue"] for x in info)
    total_ganancia = sum(x["profit"] for x in info)

    # Ganancia potencial estimada si se venden los estancados (usando su margen actual)
    ganancia_potencial = sum(max(0, (x["precio"] - x["costo"])) * x["stock"] for x in estancados)
    capital_estancado = sum(x["costo"] * x["stock"] for x in estancados)

    return render_template(
        "reports_recomendaciones.html",
        dias=dias,
        num_ventas=len(ventas),
        total_ventas=total_ventas,
        total_ganancia=total_ganancia,
        top_rentables=top_rentables,
        top_vendidos=top_vendidos,
        ofertar=ofertar,
        reponer=reponer,
        estancados=estancados,
        unidades_prom=unidades_prom,
        margen_prom=margen_prom,
        capital_estancado=capital_estancado,
        ganancia_potencial=ganancia_potencial,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


# =====================================================================
# COMISIONES DE VENDEDORES
# =====================================================================

@reports_bp.route("/comisiones")
@login_required
@role_required("administrador")
def comisiones():
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()
    try:
        d = datetime.strptime(desde, "%Y-%m-%d").date() if desde else date.today().replace(day=1)
    except ValueError:
        d = date.today().replace(day=1)
    try:
        h = datetime.strptime(hasta, "%Y-%m-%d").date() if hasta else date.today()
    except ValueError:
        h = date.today()
    if h < d:
        h = d
    inicio = datetime.combine(d, datetime.min.time())
    fin = datetime.combine(h, datetime.max.time())

    sellers = Seller.query.order_by(Seller.name).all()
    filas = []
    for s in sellers:
        ventas = Sale.query.filter(Sale.liquidada == True,  # noqa: E712
                                   Sale.vendedor_id == s.seller_id,
                                   Sale.sale_date >= inicio, Sale.sale_date <= fin).all()
        total = sum(float(v.total_amount or 0) for v in ventas)
        pct = float(s.commission_percent or 0)
        comision = round(total * pct / 100.0, 2)
        pagos = CommissionPayment.query.filter(CommissionPayment.seller_id == s.seller_id,
                                               CommissionPayment.fecha >= d,
                                               CommissionPayment.fecha <= h).all()
        pagado = round(sum(float(p.amount) for p in pagos), 2)
        filas.append({
            "seller": s, "num": len(ventas), "ventas": round(total, 2),
            "pct": pct, "comision": comision, "pagado": pagado, "saldo": round(comision - pagado, 2),
        })

    totales = {
        "ventas": sum(f["ventas"] for f in filas),
        "comision": sum(f["comision"] for f in filas),
        "pagado": sum(f["pagado"] for f in filas),
        "saldo": sum(f["saldo"] for f in filas),
    }
    pagos = (CommissionPayment.query.filter(CommissionPayment.fecha >= d, CommissionPayment.fecha <= h)
             .order_by(CommissionPayment.fecha.desc()).limit(100).all())
    return render_template("reports_comisiones.html", filas=filas, pagos=pagos,
                           desde=d.isoformat(), hasta=h.isoformat(), totales=totales,
                           sellers=sellers, generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"))


@reports_bp.route("/comisiones/pagar", methods=["POST"])
@login_required
@role_required("administrador")
def comision_pagar():
    seller = Seller.query.get(request.form.get("seller_id")) if request.form.get("seller_id") else None
    try:
        fecha = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        fecha = date.today()
    try:
        monto = float(request.form.get("amount") or 0)
    except (TypeError, ValueError):
        monto = 0
    if not seller or monto <= 0:
        flash("Selecciona el vendedor y un monto mayor a cero.", "danger")
        return redirect(url_for("reports.comisiones"))
    db.session.add(CommissionPayment(
        seller_id=seller.seller_id, fecha=fecha, amount=monto,
        periodo=request.form.get("periodo", "").strip() or None,
        notas=request.form.get("notas", "").strip() or None,
        created_by=current_user.user_id,
    ))
    db.session.commit()
    flash(f"Comisión pagada a {seller.name}: ${monto:.2f}.", "success")
    return redirect(url_for("reports.comisiones"))


@reports_bp.route("/comisiones/pago/<int:payment_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def comision_pago_eliminar(payment_id):
    pago = CommissionPayment.query.get_or_404(payment_id)
    db.session.delete(pago)
    db.session.commit()
    flash("Pago de comisión eliminado.", "info")
    return redirect(url_for("reports.comisiones"))


# =====================================================================
# METAS Y OBJETIVOS DE VENTAS
# =====================================================================

MESES_NOMBRE = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
                "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _ventas_de_meta(anio, mes, seller_id, bodega):
    inicio = datetime(anio, mes, 1)
    fin = datetime(anio + 1, 1, 1) if mes == 12 else datetime(anio, mes + 1, 1)
    q = Sale.query.filter(Sale.liquidada == True,  # noqa: E712
                          Sale.sale_date >= inicio, Sale.sale_date < fin)
    if seller_id:
        q = q.filter(Sale.vendedor_id == seller_id)
    if bodega in ("local", "matriz"):
        q = q.filter(Sale.bodega == bodega)
    return sum(float(s.total_amount or 0) for s in q.all())


@reports_bp.route("/metas")
@login_required
@role_required("administrador")
def metas():
    try:
        anio = int(request.args.get("anio", date.today().year))
    except (TypeError, ValueError):
        anio = date.today().year

    hoy = date.today()
    goals = SalesGoal.query.filter_by(anio=anio).order_by(SalesGoal.mes, SalesGoal.goal_id).all()

    filas = []
    for g in goals:
        vendido = _ventas_de_meta(anio, g.mes, g.seller_id, g.bodega)
        meta = float(g.meta or 0)
        pct = round(vendido / meta * 100, 1) if meta else 0

        proyeccion = None
        if anio == hoy.year and g.mes == hoy.month and hoy.day > 0:
            dias_mes = monthrange(anio, g.mes)[1]
            proyeccion = round(vendido / hoy.day * dias_mes, 2)

        filas.append({
            "goal": g, "mes_nombre": MESES_NOMBRE[g.mes], "vendido": round(vendido, 2),
            "meta": meta, "pct": pct, "saldo": round(max(0, meta - vendido), 2),
            "proyeccion": proyeccion,
        })

    totales = {
        "meta": sum(f["meta"] for f in filas),
        "vendido": sum(f["vendido"] for f in filas),
    }
    totales["pct"] = round(totales["vendido"] / totales["meta"] * 100, 1) if totales["meta"] else 0

    return render_template("reports_metas.html", filas=filas, anio=anio, totales=totales,
                           sellers=Seller.query.order_by(Seller.name).all(),
                           meses=MESES_NOMBRE, hoy=hoy,
                           generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"))


@reports_bp.route("/metas/nueva", methods=["POST"])
@login_required
@role_required("administrador")
def meta_nueva():
    try:
        anio = int(request.form.get("anio") or date.today().year)
        mes = int(request.form.get("mes") or date.today().month)
        meta = float(request.form.get("meta") or 0)
    except (TypeError, ValueError):
        flash("Datos de la meta inválidos.", "danger")
        return redirect(url_for("reports.metas"))

    seller_id = request.form.get("seller_id") or None
    bodega = request.form.get("bodega") or None
    if bodega not in ("local", "matriz"):
        bodega = None
    if meta <= 0:
        flash("La meta debe ser mayor a cero.", "danger")
        return redirect(url_for("reports.metas", anio=anio))

    db.session.add(SalesGoal(
        anio=anio, mes=max(1, min(12, mes)), meta=meta,
        seller_id=int(seller_id) if seller_id else None,
        bodega=bodega, created_by=current_user.user_id,
    ))
    db.session.commit()
    flash(f"Meta de ${meta:.2f} registrada para {MESES_NOMBRE[max(1, min(12, mes))]} {anio}.", "success")
    return redirect(url_for("reports.metas", anio=anio))


@reports_bp.route("/metas/<int:goal_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def meta_eliminar(goal_id):
    goal = SalesGoal.query.get_or_404(goal_id)
    anio = goal.anio
    db.session.delete(goal)
    db.session.commit()
    flash("Meta eliminada.", "info")
    return redirect(url_for("reports.metas", anio=anio))


# =====================================================================
# CUENTAS POR COBRAR / PAGAR (antiguedad de saldos)
# =====================================================================

BUCKETS = ["al_dia", "d1_30", "d31_60", "d61_90", "mas90"]
BUCKET_LABELS = {
    "al_dia": "Al día",
    "d1_30": "1-30 días",
    "d31_60": "31-60 días",
    "d61_90": "61-90 días",
    "mas90": "+90 días",
}


def _bucket_de(dias):
    if dias <= 0:
        return "al_dia"
    if dias <= 30:
        return "d1_30"
    if dias <= 60:
        return "d31_60"
    if dias <= 90:
        return "d61_90"
    return "mas90"


@reports_bp.route("/cuentas")
@login_required
@role_required("administrador")
def cuentas():
    hoy = date.today()

    # --- Por cobrar (clientes) ---
    cobrar = {}
    for v in Sale.query.filter(Sale.liquidada == True, Sale.status != "pagado").all():  # noqa: E712
        saldo = v.saldo_pendiente()
        if saldo <= 0.009:
            continue
        ref = v.due_date or (v.sale_date.date() if v.sale_date else hoy)
        dias = (hoy - ref).days
        e = cobrar.setdefault(v.customer_id, {
            "nombre": v.customer.full_name if v.customer else "—",
            "total": 0.0, "vencido": 0.0, "buckets": {k: 0.0 for k in BUCKETS},
        })
        e["total"] += saldo
        e["buckets"][_bucket_de(dias)] += saldo
        if dias > 0:
            e["vencido"] += saldo
    cobrar_lista = sorted(cobrar.values(), key=lambda x: -x["total"])

    # --- Por pagar (proveedores) ---
    pagar = {}
    for p in PurchaseInvoice.query.filter(PurchaseInvoice.status != "pagado").all():
        saldo = p.saldo_pendiente()
        if saldo <= 0.009:
            continue
        ref = p.due_date or p.invoice_date or hoy
        dias = (hoy - ref).days
        e = pagar.setdefault(p.supplier_id, {
            "nombre": p.supplier.name if p.supplier else "—",
            "total": 0.0, "vencido": 0.0, "buckets": {k: 0.0 for k in BUCKETS},
        })
        e["total"] += saldo
        e["buckets"][_bucket_de(dias)] += saldo
        if dias > 0:
            e["vencido"] += saldo
    pagar_lista = sorted(pagar.values(), key=lambda x: -x["total"])

    def _totales(lista):
        return {
            "total": sum(x["total"] for x in lista),
            "vencido": sum(x["vencido"] for x in lista),
            "buckets": {k: sum(x["buckets"][k] for x in lista) for k in BUCKETS},
        }

    return render_template("reports_cuentas.html",
                           cobrar=cobrar_lista, pagar=pagar_lista,
                           totales_cobrar=_totales(cobrar_lista),
                           totales_pagar=_totales(pagar_lista),
                           buckets=BUCKETS, bucket_labels=BUCKET_LABELS,
                           generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"))


# =====================================================================
# PANEL DEL DUENO (indicadores avanzados)
# =====================================================================
def _mes_menos(n_meses, ref):
    y, m = ref.year, ref.month - n_meses
    while m <= 0:
        m += 12
        y -= 1
    return y, m


@reports_bp.route("/panel-dueno")
@login_required
@role_required("administrador")
def panel_dueno():
    hoy = date.today()

    # Ultimos 6 meses (incluyendo el actual)
    meses = []
    for i in range(5, -1, -1):
        y, m = _mes_menos(i, hoy)
        inicio = datetime(y, m, 1)
        fm = m + 1
        fy = y
        if fm > 12:
            fm = 1
            fy += 1
        fin = datetime(fy, fm, 1)

        ventas = Sale.query.filter(
            Sale.liquidada == True,  # noqa: E712
            Sale.sale_date >= inicio, Sale.sale_date < fin).all()
        tv = sum(float(s.total_amount or 0) for s in ventas)
        tc = sum(float(s.total_cost or 0) for s in ventas)
        gastos = Expense.query.filter(Expense.expense_date >= inicio.date(),
                                      Expense.expense_date < fin.date()).all()
        tg = sum(float(g.amount) for g in gastos)
        meses.append({
            "label": inicio.strftime("%b %Y"),
            "ventas": round(tv, 2),
            "costo": round(tc, 2),
            "gastos": round(tg, 2),
            "utilidad": round(tv - tc, 2),
            "neta": round(tv - tc - tg, 2),
            "num": len(ventas),
        })

    actual = meses[-1]
    anterior = meses[-2] if len(meses) >= 2 else None
    crecimiento = None
    if anterior and anterior["ventas"] > 0:
        crecimiento = (actual["ventas"] - anterior["ventas"]) / anterior["ventas"] * 100

    ticket = (actual["ventas"] / actual["num"]) if actual["num"] else 0

    # Top productos por ganancia del mes actual
    inicio_mes = datetime(hoy.year, hoy.month, 1)
    ventas_mes = Sale.query.filter(Sale.liquidada == True, Sale.sale_date >= inicio_mes).all()  # noqa: E712
    agg = {}
    for s in ventas_mes:
        for d in s.details:
            e = agg.setdefault(d.product_id, {"product": d.product, "profit": 0.0, "units": 0})
            e["profit"] += (float(d.unit_price) - float(d.unit_cost)) * d.quantity
            e["units"] += d.quantity
    top_productos = sorted(agg.values(), key=lambda x: -x["profit"])[:10]

    return render_template(
        "reports_panel_dueno.html",
        meses=meses,
        actual=actual,
        crecimiento=crecimiento,
        ticket=ticket,
        top_productos=top_productos,
        generado=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )

CATEGORIAS_GASTO = [
    ("sueldos", "Sueldos / Personal"),
    ("luz", "Luz"),
    ("arriendo", "Arriendo"),
    ("agua", "Agua"),
    ("internet", "Internet"),
    ("transporte", "Transporte"),
    ("otros", "Otros"),
]
CATEGORIA_GASTO_LABEL = dict(CATEGORIAS_GASTO)


def _filtros_gastos():
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()
    categoria = request.args.get("categoria", "").strip()

    query = Expense.query
    if categoria in CATEGORIA_GASTO_LABEL:
        query = query.filter(Expense.category == categoria)
    if desde:
        try:
            query = query.filter(Expense.expense_date >= datetime.strptime(desde, "%Y-%m-%d").date())
        except ValueError:
            pass
    if hasta:
        try:
            query = query.filter(Expense.expense_date <= datetime.strptime(hasta, "%Y-%m-%d").date())
        except ValueError:
            pass

    gastos = query.order_by(Expense.expense_date, Expense.expense_id).all()
    total = sum(float(g.amount) for g in gastos)

    # Desglose por categoria
    por_categoria = {}
    for g in gastos:
        por_categoria[g.category] = por_categoria.get(g.category, 0.0) + float(g.amount)
    desglose = sorted(por_categoria.items(), key=lambda kv: -kv[1])

    return gastos, total, desglose, desde, hasta, categoria


@reports_bp.route("/gastos")
@login_required
@role_required("administrador")
def gastos_reporte():
    gastos, total, desglose, desde, hasta, categoria = _filtros_gastos()
    return render_template(
        "reports_gastos.html",
        gastos=gastos, total=total, desglose=desglose,
        categorias=CATEGORIAS_GASTO, categoria_label=CATEGORIA_GASTO_LABEL,
        desde=desde, hasta=hasta, selected_categoria=categoria,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


@reports_bp.route("/gastos/excel")
@login_required
@role_required("administrador")
def gastos_reporte_excel():
    gastos, total, desglose, desde, hasta, categoria = _filtros_gastos()

    wb = Workbook()
    ws = wb.active
    ws.title = "Gastos"

    ws.merge_cells("A1:F1")
    ws["A1"] = "Reporte de Gastos"
    ws["A1"].font = Font(size=14, bold=True, color="145369")
    ws.merge_cells("A2:F2")
    ws["A2"] = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {current_user.full_name}"
    ws["A2"].font = Font(size=9, italic=True, color="6b7c85")

    encabezado_fill = PatternFill(start_color="145369", end_color="145369", fill_type="solid")
    encabezado_font = Font(bold=True, color="FFFFFF")
    columnas = ["Fecha", "Categoría", "Descripción", "Personal", "Forma de pago", "Monto"]
    fila = 4
    for col_idx, titulo in enumerate(columnas, start=1):
        celda = ws.cell(row=fila, column=col_idx, value=titulo)
        celda.font = encabezado_font
        celda.fill = encabezado_fill
        celda.alignment = Alignment(horizontal="center")
    fila += 1

    for g in gastos:
        ws.cell(row=fila, column=1, value=g.expense_date.strftime("%d/%m/%Y"))
        ws.cell(row=fila, column=2, value=g.category_label())
        ws.cell(row=fila, column=3, value=g.description or "")
        ws.cell(row=fila, column=4, value=g.employee.name if g.employee else "")
        ws.cell(row=fila, column=5, value=g.payment_method_label())
        ws.cell(row=fila, column=6, value=round(float(g.amount), 2))
        fila += 1

    ws.cell(row=fila, column=5, value="TOTAL:").font = Font(bold=True, size=11)
    ws.cell(row=fila, column=6, value=round(total, 2)).font = Font(bold=True, size=11)

    for i, ancho in enumerate([12, 20, 40, 24, 16, 12], start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer, as_attachment=True,
        download_name=f"gastos_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# =====================================================================
# REPORTE DE GANANCIAS (Ventas - Costo - Gastos)
# =====================================================================

def _rango_fechas_reportes():
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()
    d = h = None
    if desde:
        try:
            d = datetime.strptime(desde, "%Y-%m-%d")
        except ValueError:
            d = None
    if hasta:
        try:
            h = datetime.strptime(hasta, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except ValueError:
            h = None
    return d, h, desde, hasta


def _calcular_ganancias():
    d, h, desde, hasta = _rango_fechas_reportes()

    # Ventas reales (liquidadas) del periodo
    vq = Sale.query.filter(Sale.liquidada == True)  # noqa: E712
    if d:
        vq = vq.filter(Sale.sale_date >= d)
    if h:
        vq = vq.filter(Sale.sale_date <= h)
    ventas = vq.all()

    total_ventas = sum(float(v.total_amount or 0) for v in ventas)
    total_costo = sum(float(v.total_cost or 0) for v in ventas)
    utilidad_bruta = total_ventas - total_costo

    # Gastos del periodo
    gq = Expense.query
    if d:
        gq = gq.filter(Expense.expense_date >= d.date())
    if h:
        gq = gq.filter(Expense.expense_date <= h.date())
    gastos = gq.all()
    total_gastos = sum(float(g.amount) for g in gastos)

    por_categoria = {}
    for g in gastos:
        por_categoria[g.category] = por_categoria.get(g.category, 0.0) + float(g.amount)
    desglose = sorted(por_categoria.items(), key=lambda kv: -kv[1])

    ganancia_neta = utilidad_bruta - total_gastos

    return {
        "num_ventas": len(ventas),
        "total_ventas": total_ventas,
        "total_costo": total_costo,
        "utilidad_bruta": utilidad_bruta,
        "total_gastos": total_gastos,
        "ganancia_neta": ganancia_neta,
        "desglose": desglose,
        "desde": desde,
        "hasta": hasta,
    }


@reports_bp.route("/ganancias")
@login_required
@role_required("administrador")
def ganancias_reporte():
    datos = _calcular_ganancias()
    return render_template(
        "reports_ganancias.html",
        datos=datos,
        categoria_label=CATEGORIA_GASTO_LABEL,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )


@reports_bp.route("/ganancias/excel")
@login_required
@role_required("administrador")
def ganancias_reporte_excel():
    datos = _calcular_ganancias()

    wb = Workbook()
    ws = wb.active
    ws.title = "Ganancias"

    ws.merge_cells("A1:B1")
    ws["A1"] = "Reporte de Ganancias"
    ws["A1"].font = Font(size=14, bold=True, color="145369")
    ws.merge_cells("A2:B2")
    ws["A2"] = f"Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} por {current_user.full_name}"
    ws["A2"].font = Font(size=9, italic=True, color="6b7c85")

    fila = 4
    def add(label, valor, bold=False):
        nonlocal fila
        c1 = ws.cell(row=fila, column=1, value=label)
        c2 = ws.cell(row=fila, column=2, value=round(valor, 2))
        if bold:
            c1.font = Font(bold=True); c2.font = Font(bold=True)
        fila += 1

    add("N° de ventas", datos["num_ventas"])
    add("Ventas totales", datos["total_ventas"], True)
    add("Costo de ventas", datos["total_costo"])
    add("Utilidad bruta", datos["utilidad_bruta"], True)
    add("Gastos totales", datos["total_gastos"], True)
    add("GANANCIA NETA", datos["ganancia_neta"], True)

    fila += 1
    ws.cell(row=fila, column=1, value="Gastos por categoría").font = Font(bold=True)
    fila += 1
    for key, monto in datos["desglose"]:
        ws.cell(row=fila, column=1, value=CATEGORIA_GASTO_LABEL.get(key, key))
        ws.cell(row=fila, column=2, value=round(monto, 2))
        fila += 1

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 16

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return send_file(
        buffer, as_attachment=True,
        download_name=f"ganancias_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
