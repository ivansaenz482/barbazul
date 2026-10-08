from datetime import datetime, date, time, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import (Product, Sale, SaleDetail, Branch,
                        DispatchGuide, DispatchGuideDetail)
from app.utils import role_required

despachos_bp = Blueprint("despachos", __name__, url_prefix="/despachos")


def _rango_filtro():
    """Rango de fechas para filtrar pedidos. Soporta desde/hasta y legacy 'fecha'."""
    desde_str = request.args.get("desde", "").strip() or request.args.get("fecha", "").strip()
    hasta_str = request.args.get("hasta", "").strip() or desde_str
    try:
        desde = datetime.strptime(desde_str, "%Y-%m-%d").date() if desde_str else date.today()
    except ValueError:
        desde = date.today()
    try:
        hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date() if hasta_str else desde
    except ValueError:
        hasta = desde
    if hasta < desde:
        hasta = desde
    return desde, hasta


def _ventas_del_dia(fecha):
    """Ventas liquidadas de ese dia que todavia no han sido despachadas."""
    inicio = datetime.combine(fecha, time.min)
    fin = datetime.combine(fecha + timedelta(days=1), time.min)
    return (Sale.query
            .filter(Sale.liquidada.is_(True))
            .filter(Sale.dispatch_id.is_(None))
            .filter(Sale.sale_date >= inicio, Sale.sale_date < fin)
            .order_by(Sale.sale_id)
            .all())


def _ventas_por_rango(desde, hasta):
    """Ventas liquidadas en el rango [desde, hasta] sin despachar, incluso pendientes de pago."""
    inicio = datetime.combine(desde, time.min)
    fin = datetime.combine(hasta + timedelta(days=1), time.min)
    # No se filtra por estado de pago: todos los pedidos liquidados aparecen para elegir cuál entregar
    return (Sale.query
            .filter(Sale.liquidada.is_(True))
            .filter(Sale.dispatch_id.is_(None))
            .filter(Sale.sale_date >= inicio, Sale.sale_date < fin)
            .order_by(Sale.sale_date, Sale.sale_id)
            .all())


def _consolidar_sales(sale_ids):
    """
    Suma los productos de las ventas seleccionadas en un solo dict
    {product_id: {'product': Product, 'quantity': int}}.
    """
    consolidado = {}
    for sid in sale_ids:
        sale = Sale.query.get(sid)
        if not sale or sale.dispatch_id is not None or not sale.liquidada:
            continue
        for detalle in sale.details:
            prod = detalle.product
            if not prod:
                continue
            entry = consolidado.setdefault(
                prod.product_id, {"product": prod, "quantity": 0})
            entry["quantity"] += detalle.quantity
    return consolidado


def _info_producto(product):
    return {
        "product_id": product.product_id,
        "sku": product.sku or "",
        "name": product.name,
        "presentacion": product.presentacion or product.unit_measure or "unidad",
        "unit_measure": product.unit_measure or "unidad",
    }


@despachos_bp.route("/")
@login_required
@role_required("administrador")
def despachos_list():
    q = request.args.get("q", "").strip()
    query = DispatchGuide.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                DispatchGuide.transportista_nombre.ilike(like),
                DispatchGuide.dispatch_number.ilike(like),
                db.cast(DispatchGuide.dispatch_id, db.String).ilike(like),
            )
        )
    guias = query.order_by(DispatchGuide.dispatch_id.desc()).all()
    return render_template("dispatch_list.html", guias=guias, q=q)


@despachos_bp.route("/nueva", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def despacho_nueva():
    branches = Branch.query.filter_by(active=True).order_by(Branch.name).all()
    productos = Product.query.filter_by(active=True).order_by(Product.name).all()

    if request.method == "POST":
        desde, hasta = _rango_filtro()
        # Fecha de emisión de la guía elegida por el usuario (independiente del filtro)
        try:
            fecha = datetime.strptime(request.form.get("dispatch_date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            fecha = date.today()

        sale_ids = [int(s) for s in request.form.getlist("sale_ids[]") if s.strip().isdigit()]

        # Consolidar las ventas seleccionadas
        consolidado = _consolidar_sales(sale_ids)

        # Agregar productos manuales (por codigo) al consolidado
        manual_ids = request.form.getlist("manual_product_id[]")
        manual_qty = request.form.getlist("manual_quantity[]")
        errores = []
        for pid, qty in zip(manual_ids, manual_qty):
            if not pid or not pid.isdigit():
                continue
            product = Product.query.get(int(pid))
            try:
                cantidad = int(float(qty))
            except (TypeError, ValueError):
                cantidad = 0
            if not product:
                errores.append("Uno de los productos manuales ya no existe.")
                continue
            if cantidad <= 0:
                errores.append(f"La cantidad de '{product.name}' debe ser mayor a cero.")
                continue
            entry = consolidado.setdefault(product.product_id, {"product": product, "quantity": 0})
            entry["quantity"] += cantidad

        if errores:
            for e in errores:
                flash(e, "danger")
            return redirect(url_for("despachos.despacho_nueva", desde=desde.isoformat(), hasta=hasta.isoformat()))

        if not consolidado:
            flash("Debes seleccionar al menos un pedido o agregar un producto por código.", "danger")
            return redirect(url_for("despachos.despacho_nueva", desde=desde.isoformat(), hasta=hasta.isoformat()))

        guia = DispatchGuide(
            dispatch_number=request.form.get("dispatch_number", "").strip() or None,
            dispatch_date=fecha,
            origin_branch_id=int(request.form.get("origin_branch_id")) if request.form.get("origin_branch_id") else None,
            transportista_nombre=request.form.get("transportista_nombre", "").strip() or None,
            transportista_identificacion=request.form.get("transportista_identificacion", "").strip() or None,
            vehiculo_placa=request.form.get("vehiculo_placa", "").strip() or None,
            observaciones=request.form.get("observaciones", "").strip() or None,
            created_by=current_user.user_id,
        )
        db.session.add(guia)
        db.session.flush()

        for info in consolidado.values():
            product = info["product"]
            db.session.add(DispatchGuideDetail(
                dispatch_id=guia.dispatch_id,
                product_id=product.product_id,
                quantity=info["quantity"],
                presentacion_snapshot=product.presentacion or product.unit_measure,
                unit_measure_snapshot=product.unit_measure,
            ))

        for sid in sale_ids:
            sale = Sale.query.get(sid)
            if sale and sale.dispatch_id is None:
                sale.dispatch_id = guia.dispatch_id

        db.session.commit()
        flash(f"Guía de Despacho #{guia.dispatch_id} generada con {sum(i['quantity'] for i in consolidado.values())} unidades.", "success")
        return redirect(url_for("despachos.despacho_detail", dispatch_id=guia.dispatch_id))

    desde, hasta = _rango_filtro()
    ventas = _ventas_por_rango(desde, hasta)
    productos_data = [
        {
            "product_id": p.product_id,
            "sku": p.sku or "",
            "name": p.name,
            "presentacion": p.presentacion or p.unit_measure or "unidad",
            "unit_measure": p.unit_measure or "unidad",
        }
        for p in productos
    ]
    return render_template("dispatch_form.html", fecha=desde, desde=desde, hasta=hasta, ventas=ventas,
                           branches=branches, productos=productos_data)


@despachos_bp.route("/api/producto")
@login_required
@role_required("administrador")
def api_producto():
    codigo = request.args.get("codigo", "").strip()
    if not codigo:
        return jsonify({"error": "Código vacío"}), 400

    producto = None
    if codigo.isdigit():
        producto = Product.query.filter_by(product_id=int(codigo)).first() or \
                   Product.query.filter(Product.sku == codigo).first()
    else:
        producto = Product.query.filter(db.func.lower(Product.sku) == codigo.lower()).first()

    if not producto:
        return jsonify({"error": "Producto no encontrado"}), 404
    return jsonify(_info_producto(producto))


@despachos_bp.route("/api/consolidar")
@login_required
@role_required("administrador")
def api_consolidar():
    sale_ids = [int(s) for s in request.args.get("sale_ids", "").split(",") if s.strip().isdigit()]
    consolidado = _consolidar_sales(sale_ids)
    items = [{
        **_info_producto(info["product"]),
        "quantity": info["quantity"],
    } for info in consolidado.values()]
    items.sort(key=lambda i: i["name"].lower())
    return jsonify({"items": items, "total_unidades": sum(i["quantity"] for i in items)})


@despachos_bp.route("/<int:dispatch_id>")
@login_required
@role_required("administrador")
def despacho_detail(dispatch_id):
    guia = DispatchGuide.query.get_or_404(dispatch_id)
    return render_template("dispatch_detail.html", guia=guia)


@despachos_bp.route("/<int:dispatch_id>/entregar", methods=["POST"])
@login_required
@role_required("administrador")
def despacho_entregar(dispatch_id):
    guia = DispatchGuide.query.get_or_404(dispatch_id)
    if guia.entregada:
        flash("Esta guía ya estaba marcada como entregada.", "info")
        return redirect(request.referrer or url_for("despachos.despachos_list"))
    guia.entregada = True
    guia.entregada_at = datetime.now()
    guia.entregada_by = current_user.user_id
    db.session.commit()
    flash(f"Guía de Despacho #{guia.dispatch_id} marcada como entregada.", "success")
    return redirect(request.referrer or url_for("despachos.despachos_list"))


@despachos_bp.route("/<int:dispatch_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def despacho_delete(dispatch_id):
    guia = DispatchGuide.query.get_or_404(dispatch_id)
    numero = guia.dispatch_id
    # Liberar los pedidos para que puedan despacharse de nuevo
    for sale in guia.sales.all():
        sale.dispatch_id = None
    db.session.delete(guia)  # borra tambien sus detalles (cascade)
    db.session.commit()
    flash(f"Guía de Despacho #{numero} eliminada. Los pedidos quedaron disponibles para despachar.", "info")
    return redirect(url_for("despachos.despachos_list"))
