from datetime import datetime, timedelta
from statistics import mean, pstdev

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required
from sqlalchemy import func

from app.extensions import db
from app.models import Sale, SaleDetail, Product, Customer
from app.alerts_utils import get_alerts_summary
from app.utils import role_required

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard/ventas")


@dashboard_bp.route("/")
@login_required
@role_required("administrador")
def index():
    return render_template("dashboard_ventas.html")


@dashboard_bp.route("/data/kpis")
@login_required
@role_required("administrador")
def data_kpis():
    total_ventas = db.session.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar()
    total_costo = db.session.query(func.coalesce(func.sum(Sale.total_cost), 0)).scalar()
    total_utilidad = float(total_ventas) - float(total_costo)
    margen = round((total_utilidad / float(total_ventas) * 100), 2) if total_ventas else 0

    num_ventas = db.session.query(func.count(Sale.sale_id)).scalar()

    hoy = datetime.utcnow().date()
    treinta_dias = hoy - timedelta(days=30)
    ventas_recientes = (
        db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(func.date(Sale.sale_date) >= treinta_dias)
        .scalar()
    )

    return jsonify({
        "total_ventas": float(total_ventas),
        "total_costo": float(total_costo),
        "total_utilidad": total_utilidad,
        "margen_pct": margen,
        "num_ventas": num_ventas,
        "ventas_ultimos_30_dias": float(ventas_recientes),
    })


@dashboard_bp.route("/data/kpis-extra")
@login_required
@role_required("administrador")
def data_kpis_extra():
    """KPIs adicionales: comparativa dia a dia, ticket promedio, valor de inventario, mejor cliente"""
    hoy = datetime.utcnow().date()
    ayer = hoy - timedelta(days=1)

    ventas_hoy = float(
        db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(func.date(Sale.sale_date) == hoy).scalar()
    )
    ventas_ayer = float(
        db.session.query(func.coalesce(func.sum(Sale.total_amount), 0))
        .filter(func.date(Sale.sale_date) == ayer).scalar()
    )

    if ventas_ayer > 0:
        variacion_pct = round((ventas_hoy - ventas_ayer) / ventas_ayer * 100, 1)
    elif ventas_hoy > 0:
        variacion_pct = 100.0
    else:
        variacion_pct = 0.0

    num_ventas = db.session.query(func.count(Sale.sale_id)).scalar()
    total_ventas = float(db.session.query(func.coalesce(func.sum(Sale.total_amount), 0)).scalar())
    ticket_promedio = round(total_ventas / num_ventas, 2) if num_ventas else 0

    # Valor del inventario actual, a precio de costo
    valor_inventario = float(
        db.session.query(func.coalesce(func.sum(Product.current_stock * Product.cost_price), 0))
        .filter(Product.active == True)  # noqa: E712
        .scalar()
    )

    # Cliente con mayores compras historicas
    top_cliente_row = (
        db.session.query(Customer.full_name, func.coalesce(func.sum(Sale.total_amount), 0).label("total"))
        .join(Sale, Sale.customer_id == Customer.customer_id)
        .group_by(Customer.customer_id, Customer.full_name)
        .order_by(func.sum(Sale.total_amount).desc())
        .first()
    )
    top_cliente = {
        "nombre": top_cliente_row[0] if top_cliente_row else "—",
        "total": float(top_cliente_row[1]) if top_cliente_row else 0,
    }

    alertas = get_alerts_summary()
    alertas_activas = alertas["bajo_stock"] + alertas["sobre_stock"] + alertas["creditos_vencidos"]

    return jsonify({
        "ventas_hoy": ventas_hoy,
        "ventas_ayer": ventas_ayer,
        "variacion_pct": variacion_pct,
        "ticket_promedio": ticket_promedio,
        "valor_inventario": valor_inventario,
        "top_cliente": top_cliente,
        "alertas_activas": alertas_activas,
    })


@dashboard_bp.route("/data/tendencia")
@login_required
@role_required("administrador")
def data_tendencia():
    """Ventas agrupadas por dia, para grafico de linea. Rango configurable via ?dias=7|30|90"""
    dias = request.args.get("dias", 30, type=int)
    if dias not in (7, 30, 90):
        dias = 30

    hoy = datetime.utcnow().date()
    desde = hoy - timedelta(days=dias - 1)

    resultados = (
        db.session.query(
            func.date(Sale.sale_date).label("fecha"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total")
        )
        .filter(func.date(Sale.sale_date) >= desde)
        .group_by(func.date(Sale.sale_date))
        .all()
    )

    ventas_por_dia = {str(r.fecha): float(r.total) for r in resultados}

    labels, valores = [], []
    for i in range(dias):
        fecha = desde + timedelta(days=i)
        labels.append(fecha.strftime("%d/%m"))
        valores.append(ventas_por_dia.get(str(fecha), 0))

    return jsonify({"labels": labels, "valores": valores})


@dashboard_bp.route("/data/top-productos")
@login_required
@role_required("administrador")
def data_top_productos():
    """Top 8 productos por utilidad generada"""
    resultados = (
        db.session.query(
            Product.name,
            func.coalesce(func.sum(SaleDetail.quantity * SaleDetail.unit_price), 0).label("ingresos"),
            func.coalesce(func.sum(SaleDetail.quantity * SaleDetail.unit_cost), 0).label("costo"),
        )
        .join(SaleDetail, SaleDetail.product_id == Product.product_id)
        .group_by(Product.product_id, Product.name)
        .all()
    )

    productos = []
    for r in resultados:
        ingresos = float(r.ingresos)
        costo = float(r.costo)
        productos.append({
            "nombre": r.name,
            "ingresos": ingresos,
            "utilidad": ingresos - costo,
            "margen_pct": round((ingresos - costo) / ingresos * 100, 1) if ingresos else 0,
        })

    productos.sort(key=lambda p: p["utilidad"], reverse=True)
    return jsonify(productos[:8])


@dashboard_bp.route("/data/cuentas-por-cobrar")
@login_required
@role_required("administrador")
def data_cuentas_por_cobrar():
    """Ventas a credito pendientes de cobro, marcando vencidas"""
    hoy = datetime.utcnow().date()

    ventas_credito = (
        Sale.query
        .filter(Sale.payment_type == "credito", Sale.status != "pagado")
        .order_by(Sale.due_date)
        .all()
    )

    cuentas = []
    for s in ventas_credito:
        vencido = s.due_date is not None and s.due_date < hoy
        cuentas.append({
            "sale_id": s.sale_id,
            "cliente": s.customer.full_name,
            "fecha_venta": s.sale_date.strftime("%d/%m/%Y"),
            "fecha_vencimiento": s.due_date.strftime("%d/%m/%Y") if s.due_date else "—",
            "total": float(s.total_amount),
            "saldo_pendiente": s.saldo_pendiente(),
            "vencido": vencido,
        })

    return jsonify(cuentas)


@dashboard_bp.route("/data/anomalias")
@login_required
@role_required("administrador")
def data_anomalias():
    """
    Deteccion simple de anomalias: ventas cuyo monto total se aleja
    significativamente del promedio historico (mas de 2 desviaciones estandar).
    """
    montos = [float(s.total_amount) for s in Sale.query.all()]

    if len(montos) < 5:
        return jsonify({"anomalias": [], "mensaje": "Aún no hay suficientes ventas para detectar anomalías."})

    promedio = mean(montos)
    desviacion = pstdev(montos)
    umbral = promedio + 2 * desviacion

    if desviacion == 0:
        return jsonify({"anomalias": [], "mensaje": "No se detectaron anomalías."})

    ventas_atipicas = Sale.query.filter(Sale.total_amount >= umbral).order_by(Sale.sale_date.desc()).all()

    anomalias = [{
        "sale_id": s.sale_id,
        "cliente": s.customer.full_name,
        "fecha": s.sale_date.strftime("%d/%m/%Y %H:%M"),
        "total": float(s.total_amount),
        "motivo": f"Monto muy superior al promedio histórico (${promedio:.2f})"
    } for s in ventas_atipicas]

    return jsonify({"anomalias": anomalias, "promedio_historico": round(promedio, 2)})


@dashboard_bp.route("/data/por-provincia")
@login_required
@role_required("administrador")
def data_por_provincia():
    """Ventas y clientes agrupados por provincia, para ver donde se vende mas"""
    resultados = (
        db.session.query(
            Customer.province,
            func.count(func.distinct(Customer.customer_id)).label("num_clientes"),
            func.coalesce(func.sum(Sale.total_amount), 0).label("total_ventas"),
        )
        .join(Sale, Sale.customer_id == Customer.customer_id)
        .filter(Customer.province.isnot(None))
        .group_by(Customer.province)
        .order_by(func.sum(Sale.total_amount).desc())
        .all()
    )

    datos = [{
        "provincia": r.province,
        "num_clientes": r.num_clientes,
        "total_ventas": float(r.total_ventas),
    } for r in resultados]

    return jsonify(datos)
