from datetime import datetime, date, time, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Product, Customer, Sale, SaleDetail, Branch
from app.routes.sales import _validar_line_items, _ejecutar_entrega
from app.utils import generar_barcode_svg, role_required, perm_required

caja_bp = Blueprint("caja", __name__, url_prefix="/caja")

NOMBRE_CLIENTE_MOSTRADOR = "Venta de Mostrador"
NOMBRE_CLIENTE_CONSUMIDOR = "Consumidor Final"
TIPO_DOCUMENTOS = ("factura", "nota_venta_autorizada", "nota_pedido")


def _productos_vendibles():
    """Productos activos que el usuario puede vender (respeta categorias asignadas)."""
    query = Product.query.filter_by(active=True)
    if not current_user.is_admin() and current_user.allowed_categories:
        categorias_permitidas = [c.category_id for c in current_user.allowed_categories]
        query = query.filter(Product.category_id.in_(categorias_permitidas))
    return query.order_by(Product.name).all()


def _cliente_mostrador():
    """Devuelve (o crea la primera vez) el cliente generico 'Venta de Mostrador'."""
    cliente = Customer.query.filter_by(full_name=NOMBRE_CLIENTE_MOSTRADOR).first()
    if not cliente:
        cliente = Customer(
            full_name=NOMBRE_CLIENTE_MOSTRADOR,
            cedula="9999999999",
            customer_type="efectivo",
            active=True,
        )
        db.session.add(cliente)
        db.session.commit()
    return cliente


def _cliente_consumidor_final():
    """Devuelve (o crea la primera vez) el cliente generico 'Consumidor Final'."""
    cliente = Customer.query.filter_by(full_name=NOMBRE_CLIENTE_CONSUMIDOR).first()
    if not cliente:
        cliente = Customer(
            full_name=NOMBRE_CLIENTE_CONSUMIDOR,
            cedula="9999999998",
            customer_type="efectivo",
            active=True,
        )
        db.session.add(cliente)
        db.session.commit()
    return cliente


def _bodega_caja():
    """Bodega con la que opera el usuario en la caja."""
    if current_user.ve_todas_bodegas():
        b = request.values.get("bodega", "local")
        return b if b in ("local", "matriz") else "local"
    return current_user.bodega or "local"


def _info_producto(product):
    bodega = _bodega_caja()
    stock = (product.stock_matriz or 0) if bodega == "matriz" else (product.current_stock or 0)
    return {
        "product_id": product.product_id,
        "sku": product.sku or "",
        "barcode": product.barcode or "",
        "name": product.name,
        "presentacion": product.presentacion or product.unit_measure or "unidad",
        "sale_price": float(product.sale_price),
        "price": float(product.sale_price),
        "cost_price": float(product.cost_price),
        "current_stock": stock,
        "stock_local": product.current_stock or 0,
        "stock_matriz": product.stock_matriz or 0,
        "bodega": bodega,
        "image_url": url_for("products.product_image", product_id=product.product_id) if product.image_path else None,
    }


@caja_bp.route("/")
@login_required
@perm_required("can_view_ventas")
def caja_index():
    productos = _productos_vendibles()
    clientes = Customer.query.filter_by(active=True).order_by(Customer.full_name).all()
    hoy = date.today()
    inicio = datetime.combine(hoy, time.min)
    fin = datetime.combine(hoy + timedelta(days=1), time.min)
    ventas_hoy = (Sale.query
                  .filter(Sale.sale_date >= inicio, Sale.sale_date < fin)
                  .order_by(Sale.sale_date.desc()).all())
    total_hoy = sum(float(s.total_amount or 0) for s in ventas_hoy)
    productos_data = [_info_producto(p) for p in productos]
    ultima_venta_id = request.args.get("imprimir", type=int)
    return render_template("caja_index.html", productos=productos_data, clientes=clientes,
                           ventas_hoy=ventas_hoy, total_hoy=total_hoy,
                           ultima_venta_id=ultima_venta_id, bodega=_bodega_caja())


@caja_bp.route("/recibo/<int:sale_id>")
@login_required
@perm_required("can_view_ventas")
def caja_recibo(sale_id):
    """Recibo de la venta de caja, listo para imprimir."""
    sale = Sale.query.get_or_404(sale_id)
    return render_template("caja_recibo.html", sale=sale)


@caja_bp.route("/api/producto")
@login_required
@perm_required("can_view_ventas")
def caja_api_producto():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Búsqueda vacía"}), 400

    # Busqueda exacta: codigo de barras, luego SKU, luego id numerico
    producto = Product.query.filter_by(active=True, barcode=q).first()
    if not producto:
        producto = Product.query.filter(db.func.lower(Product.sku) == q.lower()).first()
    if not producto and q.isdigit():
        producto = Product.query.filter_by(active=True, product_id=int(q)).first()

    if not producto:
        return jsonify({"error": "Producto no encontrado"}), 404
    return jsonify(_info_producto(producto))


@caja_bp.route("/barcode/<codigo>")
@login_required
@perm_required("can_view_ventas")
def caja_barcode(codigo):
    """Devuelve la imagen SVG del codigo de barras para mostrarla en <img>."""
    svg = generar_barcode_svg(codigo)
    if not svg:
        abort(404)
    respuesta = Response(svg, mimetype="image/svg+xml")
    respuesta.headers["Cache-Control"] = "public, max-age=86400"
    return respuesta


@caja_bp.route("/registrar", methods=["POST"])
@login_required
@perm_required("can_view_ventas")
def caja_registrar():
    clientes = Customer.query.filter_by(active=True).order_by(Customer.full_name).all()
    productos = _productos_vendibles()
    productos_data = [_info_producto(p) for p in productos]

    product_ids = request.form.getlist("product_id[]")
    quantities = request.form.getlist("quantity[]")
    precios = request.form.getlist("unit_price[]")

    if not product_ids or all(not pid for pid in product_ids):
        flash("Agrega al menos un producto a la venta.", "danger")
        return redirect(url_for("caja.caja_index"))

    line_items, error = _validar_line_items(product_ids, quantities, precios, _bodega_caja())
    if error:
        flash(error, "danger")
        return redirect(url_for("caja.caja_index"))

    customer_id = request.form.get("customer_id", "").strip()
    payment_type = request.form.get("payment_type", "efectivo")
    if payment_type not in ("efectivo", "credito"):
        payment_type = "efectivo"

    if customer_id == "consumidor_final":
        customer = _cliente_consumidor_final()
    elif customer_id and customer_id.isdigit():
        customer = Customer.query.get(int(customer_id))
    else:
        customer = _cliente_mostrador()

    if payment_type == "credito" and customer.full_name in (NOMBRE_CLIENTE_MOSTRADOR, NOMBRE_CLIENTE_CONSUMIDOR):
        flash("Para una venta a crédito debes seleccionar un cliente registrado.", "danger")
        return redirect(url_for("caja.caja_index"))

    document_type = request.form.get("document_type", "nota_venta_autorizada")
    if document_type not in TIPO_DOCUMENTOS:
        document_type = "nota_venta_autorizada"

    marcar_pagada = request.form.get("marcar_pagada") == "on"
    payment_method = request.form.get("payment_method", "efectivo")
    receipt_number = request.form.get("receipt_number", "").strip() or None

    sale = Sale(
        customer_id=customer.customer_id,
        user_id=current_user.user_id,
        bodega=_bodega_caja(),
        payment_type=payment_type,
        document_type=document_type,
        status="pendiente",
    )
    db.session.add(sale)
    db.session.flush()

    for product, quantity, unit_price in line_items:
        db.session.add(SaleDetail(
            sale_id=sale.sale_id,
            product_id=product.product_id,
            quantity=quantity,
            unit_price=unit_price,
            unit_cost=float(product.cost_price),
        ))
    db.session.flush()

    if document_type == "nota_pedido":
        # Nota de Pedido: solo se registra el pedido, NO descuenta stock ni
        # cobra todavia. Cuando se autorice se convertira en Nota de Venta
        # Autorizada o Factura (ver "sale_liquidar").
        sale.total_amount = sum(unit_price * quantity for _, quantity, unit_price in line_items)
        sale.total_cost = sum(float(product.cost_price) * quantity for product, quantity, _ in line_items)
        sale.liquidada = False
        sale.status = "pendiente"
        db.session.commit()
        flash(f"Nota de Pedido #{sale.sale_id} registrada por ${sale.total_amount:.2f}. Pendiente de autorizar.", "info")
        return redirect(url_for("caja.caja_index", imprimir=sale.sale_id))

    ok, error = _ejecutar_entrega(sale, marcar_pagada=marcar_pagada,
                                   payment_method=payment_method, receipt_number=receipt_number)
    if not ok:
        db.session.rollback()
        flash(error, "danger")
        return redirect(url_for("caja.caja_index"))

    db.session.commit()
    if marcar_pagada:
        flash(f"Venta de caja #{sale.sale_id} registrada por ${sale.total_amount:.2f}.", "success")
    else:
        flash(f"Venta de caja #{sale.sale_id} registrada (fiada) por ${sale.total_amount:.2f}.", "success")
    return redirect(url_for("caja.caja_index", imprimir=sale.sale_id))


@caja_bp.route("/etiquetas")
@login_required
@role_required("administrador")
def caja_etiquetas():
    productos = Product.query.filter_by(active=True).order_by(Product.name).all()
    return render_template("caja_etiquetas.html", productos=productos)


@caja_bp.route("/etiquetas/imprimir")
@login_required
@role_required("administrador")
def caja_etiquetas_imprimir():
    items = []
    for item in request.args.get("items", "").split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        pid, qty = item.split(":")
        if not pid.isdigit():
            continue
        product = Product.query.get(int(pid))
        if not product:
            continue
        try:
            qty = max(1, min(int(qty), 200))
        except ValueError:
            qty = 1
        codigo = product.barcode or product.sku or str(product.product_id)
        items.append({
            "product": product,
            "qty": qty,
            "codigo": codigo,
            "svg": generar_barcode_svg(codigo, incluir_texto=False),
        })
    return render_template("caja_etiquetas_print.html", items=items)
