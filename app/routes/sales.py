from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Product, Customer, Sale, SaleDetail, Payment, InventoryMovement, Seller
from app.audit import registrar
from app.utils import role_required, perm_required

sales_bp = Blueprint("sales", __name__, url_prefix="/ventas")


def _productos_vendibles():
    """
    Productos activos que el usuario actual puede vender.
    El administrador y los vendedores sin restriccion ven todo.
    Un vendedor con categorias asignadas solo ve esas.
    """
    query = Product.query.filter_by(active=True)

    if not current_user.is_admin() and current_user.allowed_categories:
        categorias_permitidas = [c.category_id for c in current_user.allowed_categories]
        query = query.filter(Product.category_id.in_(categorias_permitidas))

    return query.order_by(Product.name).all()


def _bodega_label(bodega):
    return "Bodega Matriz" if bodega == "matriz" else "Bodega Local"


def _stock_bodega(product, bodega):
    """Stock del producto en la bodega indicada."""
    if bodega == "matriz":
        return product.stock_matriz or 0
    return product.current_stock or 0


def _sumar_stock_bodega(product, bodega, cantidad):
    if bodega == "matriz":
        product.stock_matriz = (product.stock_matriz or 0) + cantidad
    else:
        product.current_stock = (product.current_stock or 0) + cantidad


def _restar_stock_bodega(product, bodega, cantidad):
    if bodega == "matriz":
        product.stock_matriz = max(0, (product.stock_matriz or 0) - cantidad)
    else:
        product.current_stock = max(0, (product.current_stock or 0) - cantidad)


def _bodega_formulario():
    """Bodega con la que opera el usuario actual. El admin/sin-bodega elige; el resto, la suya."""
    if current_user.ve_todas_bodegas():
        b = request.form.get("bodega", "local")
        return b if b in ("local", "matriz") else "local"
    return current_user.bodega or "local"


def _validar_line_items(product_ids, quantities, precios, bodega="local"):
    """
    Valida stock (de la bodega indicada), permisos de categoria y precio.
    Devuelve (line_items, error) -- si hay error, line_items es None.
    """
    line_items = []
    for pid, qty, precio_str in zip(product_ids, quantities, precios):
        if not pid or not qty:
            continue
        product = Product.query.get(int(pid))
        quantity = int(qty)
        if quantity <= 0:
            continue
        if not product or not product.active:
            return None, "Uno de los productos seleccionados ya no está disponible."
        disponible = _stock_bodega(product, bodega)
        if quantity > disponible:
            return None, f"Stock insuficiente en {_bodega_label(bodega)} para '{product.name}'. Disponible: {disponible}."
        if not current_user.can_sell_category(product.category_id):
            return None, f"No tienes permiso para vender '{product.name}' (categoría restringida)."

        try:
            unit_price = float(precio_str) if precio_str else float(product.sale_price)
        except ValueError:
            unit_price = float(product.sale_price)
        if unit_price < 0:
            return None, f"El precio de '{product.name}' no puede ser negativo."

        line_items.append((product, quantity, unit_price))

    if not line_items:
        return None, "Debes agregar al menos un producto válido a la venta."

    return line_items, None


def _ejecutar_entrega(sale, descontar_stock=True, marcar_pagada=True, payment_method="efectivo", receipt_number=None):
    """
    Descuenta stock, registra movimientos de inventario y, si corresponde,
    marca la venta como pagada de inmediato. Se usa tanto al crear una
    Factura/Nota de Venta directa como al liquidar una Proforma aceptada.

    marcar_pagada: si es False y el pago es en efectivo, la venta queda
    'pendiente' igual que una venta a credito, para poder registrar el
    pago mas tarde (ej. "fio" del dia, o el cliente paga en la semana).
    """
    total_amount = 0
    total_cost = 0
    bodega = sale.bodega or "local"

    for detail in sale.details:
        product = detail.product

        if descontar_stock:
            if detail.quantity > _stock_bodega(product, bodega):
                return False, f"Stock insuficiente en {_bodega_label(bodega)} para '{product.name}'. Disponible: {_stock_bodega(product, bodega)}."

        total_amount += float(detail.unit_price) * detail.quantity
        total_cost += float(detail.unit_cost) * detail.quantity

    if descontar_stock:
        for detail in sale.details:
            product = detail.product
            _restar_stock_bodega(product, bodega, detail.quantity)
            db.session.add(InventoryMovement(
                product_id=product.product_id,
                movement_type="salida",
                quantity=detail.quantity,
                reference_type="venta",
                reference_id=sale.sale_id,
                user_id=current_user.user_id,
                notes=f"Venta #{sale.sale_id} ({sale.document_type_label()}) — {_bodega_label(bodega)}",
            ))

    sale.total_amount = total_amount
    sale.total_cost = total_cost

    if sale.payment_type == "credito":
        days = int(sale.customer.credit_term_days) if sale.customer.credit_term_days and sale.customer.credit_term_days != "0" else 30
        sale.due_date = (datetime.now() + timedelta(days=days)).date()
        sale.status = "pendiente"
    elif marcar_pagada:
        sale.status = "pagado"
        db.session.add(Payment(
            sale_id=sale.sale_id,
            amount=total_amount,
            payment_method=payment_method,
            receipt_number=receipt_number,
            registered_by=current_user.user_id,
        ))
    else:
        # Efectivo, pero pendiente de cobro (ej. se entrega hoy, se cobra en la semana)
        sale.status = "pendiente"

    sale.liquidada = True
    sale.liquidated_by = current_user.user_id
    sale.liquidated_at = datetime.now()
    return True, None


@sales_bp.route("/")
@login_required
@perm_required("can_view_ventas")
def sales_list():
    status = request.args.get("status", "").strip()
    q = request.args.get("q", "").strip()
    query = Sale.query
    if status in ("pendiente", "pagado", "vencido"):
        query = query.filter(Sale.status == status)
    if q:
        like = f"%{q}%"
        query = query.join(Customer).filter(
            db.or_(
                Customer.full_name.ilike(like),
                db.cast(Sale.sale_id, db.String).ilike(like),
            )
        )
    sales = query.order_by(Sale.sale_date.desc()).all()
    return render_template("sales_list.html", sales=sales, status=status, q=q)


@sales_bp.route("/nueva", methods=["GET", "POST"])
@login_required
@perm_required("can_view_ventas")
def sale_new():
    customers = Customer.query.filter_by(active=True).order_by(Customer.full_name).all()
    products = _productos_vendibles()
    sellers = Seller.query.filter_by(active=True).order_by(Seller.name).all()
    bodega = current_user.bodega or "local"

    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        customer = Customer.query.get(customer_id) if customer_id else None

        if not customer:
            flash("Debes seleccionar un cliente.", "danger")
            return render_template("sale_form.html", customers=customers, products=products, sellers=sellers, bodega=bodega)

        payment_type = request.form.get("payment_type", "efectivo")
        document_type = request.form.get("document_type", "nota_venta_autorizada")
        if document_type not in ("factura", "nota_venta_autorizada", "nota_pedido", "proforma"):
            document_type = "nota_venta_autorizada"
        marcar_pagada = request.form.get("marcar_pagada") == "on"
        payment_method_inicial = request.form.get("initial_payment_method", "efectivo")
        receipt_number_inicial = request.form.get("initial_receipt_number", "").strip() or None
        vendedor_id = request.form.get("vendedor_id") or None
        bodega = _bodega_formulario()

        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        precios = request.form.getlist("unit_price[]")

        if not product_ids or all(not pid for pid in product_ids):
            flash("Debes agregar al menos un producto a la venta.", "danger")
            return render_template("sale_form.html", customers=customers, products=products, sellers=sellers, bodega=bodega)

        line_items, error = _validar_line_items(product_ids, quantities, precios, bodega)
        if error:
            flash(error, "danger")
            return render_template("sale_form.html", customers=customers, products=products, sellers=sellers, bodega=bodega)

        sale = Sale(
            customer_id=customer.customer_id,
            user_id=current_user.user_id,
            vendedor_id=int(vendedor_id) if vendedor_id else None,
            bodega=bodega,
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

        if document_type in ("proforma", "nota_pedido"):
            # Es solo un pedido/cotizacion: se calculan totales de referencia,
            # pero NO se descuenta stock ni se registra pago todavia.
            sale.total_amount = sum(unit_price * quantity for _, quantity, unit_price in line_items)
            sale.total_cost = sum(float(product.cost_price) * quantity for product, quantity, _ in line_items)
            sale.liquidada = False
            db.session.commit()
            flash(f"{sale.document_type_label()} #{sale.sale_id} guardada. Aún no afecta el inventario hasta que se autorice.", "info")
            registrar("venta_creada", detalle=f"{sale.document_type_label()} #{sale.sale_id} por ${float(sale.total_amount):.2f}", entidad="venta", entidad_id=sale.sale_id)
        else:
            ok, error = _ejecutar_entrega(sale, marcar_pagada=marcar_pagada,
                                           payment_method=payment_method_inicial, receipt_number=receipt_number_inicial)
            if not ok:
                db.session.rollback()
                flash(error, "danger")
                return render_template("sale_form.html", customers=customers, products=products, sellers=sellers, bodega=bodega)
            db.session.commit()
            flash(f"{sale.document_type_label()} #{sale.sale_id} registrada correctamente por ${sale.total_amount:.2f}.", "success")
            registrar("venta_creada", detalle=f"{sale.document_type_label()} #{sale.sale_id} por ${float(sale.total_amount):.2f}", entidad="venta", entidad_id=sale.sale_id)

        return redirect(url_for("sales.sale_detail", sale_id=sale.sale_id))

    return render_template("sale_form.html", customers=customers, products=products, sellers=sellers)


@sales_bp.route("/<int:sale_id>")
@login_required
@perm_required("can_view_ventas")
def sale_detail(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    return render_template("sale_detail.html", sale=sale)


def _revertir_stock_venta(sale):
    """Devuelve el stock de una venta liquidada y borra sus movimientos de inventario."""
    if not sale.liquidada:
        return
    bodega = sale.bodega or "local"
    for detalle in sale.details:
        product = detalle.product
        if product:
            _sumar_stock_bodega(product, bodega, detalle.quantity)
        for mv in InventoryMovement.query.filter_by(
            reference_type="venta", reference_id=sale.sale_id, product_id=detalle.product_id
        ).all():
            db.session.delete(mv)


@sales_bp.route("/<int:sale_id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("can_edit_pedidos")
def sale_edit(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    customers = Customer.query.filter_by(active=True).order_by(Customer.full_name).all()
    products = _productos_vendibles()
    sellers = Seller.query.filter_by(active=True).order_by(Seller.name).all()
    bodega = sale.bodega or "local"

    if request.method == "POST":
        customer_id = request.form.get("customer_id")
        customer = Customer.query.get(customer_id) if customer_id else None

        if not customer:
            flash("Debes seleccionar un cliente.", "danger")
            return render_template("sale_form.html", sale=sale, customers=customers, products=products, sellers=sellers, bodega=bodega)

        payment_type = request.form.get("payment_type", "efectivo")
        document_type = request.form.get("document_type", "nota_venta_autorizada")
        if document_type not in ("factura", "nota_venta_autorizada", "nota_pedido", "proforma"):
            document_type = "nota_venta_autorizada"

        # Si la venta ya estaba liquidada, primero devolvemos su stock y limpiamos
        # los movimientos anteriores para poder re-descontar con los nuevos datos.
        _revertir_stock_venta(sale)
        bodega = _bodega_formulario()

        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        precios = request.form.getlist("unit_price[]")

        line_items, error = _validar_line_items(product_ids, quantities, precios, bodega)
        if error:
            db.session.rollback()  # deshace la devolución de stock anterior
            flash(error, "danger")
            return render_template("sale_form.html", sale=sale, customers=customers, products=products, sellers=sellers, bodega=bodega)

        # Reemplazar los detalles de la venta
        for detalle in list(sale.details):
            db.session.delete(detalle)

        sale.customer_id = customer.customer_id
        sale.payment_type = payment_type
        sale.document_type = document_type
        sale.bodega = bodega
        vendedor_id = request.form.get("vendedor_id") or None
        sale.vendedor_id = int(vendedor_id) if vendedor_id else None

        total_amount = 0
        total_cost = 0
        for product, quantity, unit_price in line_items:
            db.session.add(SaleDetail(
                sale_id=sale.sale_id,
                product_id=product.product_id,
                quantity=quantity,
                unit_price=unit_price,
                unit_cost=float(product.cost_price),
            ))
            total_amount += unit_price * quantity
            total_cost += float(product.cost_price) * quantity
            if sale.liquidada:
                _restar_stock_bodega(product, bodega, quantity)
                db.session.add(InventoryMovement(
                    product_id=product.product_id,
                    movement_type="salida",
                    quantity=quantity,
                    reference_type="venta",
                    reference_id=sale.sale_id,
                    user_id=current_user.user_id,
                    notes=f"Venta #{sale.sale_id} ({sale.document_type_label()}) — {_bodega_label(bodega)}",
                ))

        sale.total_amount = total_amount
        sale.total_cost = total_cost

        # Recalcular estado de pago según los pagos ya registrados
        if sale.liquidada:
            if sale.payment_type == "credito":
                days = int(sale.customer.credit_term_days) if sale.customer.credit_term_days and sale.customer.credit_term_days != "0" else 30
                sale.due_date = (datetime.now() + timedelta(days=days)).date()
                sale.status = "pendiente"
            else:
                sale.due_date = None
                sale.status = "pagado" if sale.pagado_total() >= sale.total_amount - 0.009 else "pendiente"
        else:
            sale.due_date = None
            sale.status = "pendiente"

        db.session.commit()
        flash(f"Venta #{sale.sale_id} actualizada correctamente.", "success")
        registrar("venta_editada", detalle=f"Venta #{sale.sale_id} por ${float(sale.total_amount):.2f}", entidad="venta", entidad_id=sale.sale_id)
        return redirect(url_for("sales.sale_detail", sale_id=sale.sale_id))

    return render_template("sale_form.html", sale=sale, customers=customers, products=products, sellers=sellers, bodega=bodega)


@sales_bp.route("/<int:sale_id>/eliminar", methods=["POST"])
@login_required
@perm_required("can_edit_pedidos")
def sale_delete(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    _revertir_stock_venta(sale)
    db.session.delete(sale)  # borra tambien detalles y pagos (cascade)
    db.session.commit()
    flash(f"Venta #{sale.sale_id} eliminada correctamente. Stock devuelto a inventario.", "info")
    registrar("venta_eliminada", detalle=f"Venta #{sale_id} eliminada", entidad="venta", entidad_id=sale_id)
    return redirect(url_for("sales.sales_list"))


@sales_bp.route("/<int:sale_id>/liquidar", methods=["POST"])
@login_required
@perm_required("can_edit_pedidos")
def sale_liquidar(sale_id):
    """
    Autoriza una Nota de Pedido o confirma que una Proforma se ejecuto de verdad
    (entrega/venta aceptada). Aqui recien se descuenta el stock y se convierte
    en Nota de Venta Autorizada o Factura.
    """
    sale = Sale.query.get_or_404(sale_id)

    if sale.liquidada:
        flash("Esta venta ya fue liquidada.", "warning")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    final_document_type = request.form.get("document_type", "nota_venta_autorizada")
    if final_document_type not in ("factura", "nota_venta_autorizada"):
        final_document_type = "nota_venta_autorizada"

    final_payment_type = request.form.get("payment_type", sale.payment_type)
    if final_payment_type not in ("efectivo", "credito"):
        final_payment_type = sale.payment_type

    sale.document_type = final_document_type
    sale.payment_type = final_payment_type
    marcar_pagada = request.form.get("marcar_pagada") == "on"
    payment_method_inicial = request.form.get("initial_payment_method", "efectivo")
    receipt_number_inicial = request.form.get("initial_receipt_number", "").strip() or None

    ok, error = _ejecutar_entrega(sale, marcar_pagada=marcar_pagada,
                                   payment_method=payment_method_inicial, receipt_number=receipt_number_inicial)
    if not ok:
        db.session.rollback()
        flash(error, "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    db.session.commit()
    flash(f"Venta #{sale.sale_id} liquidada correctamente como {sale.document_type_label()}. Stock actualizado.", "success")
    return redirect(url_for("sales.sale_detail", sale_id=sale_id))


DIAS_LIMITE_EDICION = 7


def _dentro_de_plazo_edicion(sale):
    """El personal solo puede editar el pago dentro de los primeros dias; el admin siempre puede."""
    if current_user.is_admin():
        return True
    referencia = sale.liquidated_at or sale.sale_date
    return (datetime.now() - referencia).days <= DIAS_LIMITE_EDICION


@sales_bp.route("/<int:sale_id>/estado-pago", methods=["POST"])
@login_required
@perm_required("can_edit_pedidos")
def sale_edit_payment_status(sale_id):
    """
    Permite marcar una venta como Cancelada (pagada completa) de un clic,
    o revertirla a Pendiente si se marcó por error. Respeta el plazo de edicion.
    """
    sale = Sale.query.get_or_404(sale_id)

    if not sale.liquidada:
        flash("Esta proforma todavía no ha sido liquidada.", "warning")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    if not _dentro_de_plazo_edicion(sale):
        flash(f"Ya pasaron más de {DIAS_LIMITE_EDICION} días desde esta venta. "
              f"Solo un administrador puede editar el estado de pago a estas alturas.", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    nueva_accion = request.form.get("accion")

    if nueva_accion == "marcar_cancelada":
        saldo = sale.saldo_pendiente()
        if saldo > 0:
            db.session.add(Payment(
                sale_id=sale.sale_id,
                amount=saldo,
                payment_method=request.form.get("payment_method", "efectivo"),
                receipt_number=request.form.get("receipt_number", "").strip() or None,
                registered_by=current_user.user_id,
            ))
        sale.status = "pagado"
        db.session.commit()
        flash(f"Venta #{sale.sale_id} marcada como Cancelada.", "success")

    elif nueva_accion == "revertir_pendiente":
        if not current_user.is_admin():
            flash("Solo un administrador puede revertir una venta ya cancelada.", "danger")
            return redirect(url_for("sales.sale_detail", sale_id=sale_id))
        # Elimina los pagos registrados para dejarla en pendiente otra vez
        for p in list(sale.payments):
            db.session.delete(p)
        sale.status = "pendiente"
        db.session.commit()
        flash(f"Venta #{sale.sale_id} revertida a Pendiente.", "info")

    return redirect(url_for("sales.sale_detail", sale_id=sale_id))


@sales_bp.route("/<int:sale_id>/pago", methods=["POST"])
@login_required
@perm_required("can_edit_pedidos")
def sale_add_payment(sale_id):
    sale = Sale.query.get_or_404(sale_id)

    if not sale.liquidada:
        flash("Esta proforma todavía no ha sido liquidada.", "warning")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    if sale.status == "pagado":
        flash("Esta venta ya está cancelada (pagada en su totalidad).", "info")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    if not _dentro_de_plazo_edicion(sale):
        flash(f"Ya pasaron más de {DIAS_LIMITE_EDICION} días desde esta venta. "
              f"Solo un administrador puede editar el pago a estas alturas.", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    amount = float(request.form.get("amount") or 0)
    saldo = sale.saldo_pendiente()

    if amount <= 0:
        flash("El monto del pago debe ser mayor a cero.", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    if amount > saldo:
        flash(f"El pago (${amount:.2f}) es mayor al saldo pendiente (${saldo:.2f}).", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale_id))

    db.session.add(Payment(
        sale_id=sale.sale_id,
        amount=amount,
        payment_method=request.form.get("payment_method", "efectivo"),
        receipt_number=request.form.get("receipt_number", "").strip() or None,
        registered_by=current_user.user_id,
    ))

    nuevo_saldo = saldo - amount
    if nuevo_saldo <= 0:
        sale.status = "pagado"

    db.session.commit()
    flash(f"Pago de ${amount:.2f} registrado correctamente.", "success")
    return redirect(url_for("sales.sale_detail", sale_id=sale_id))


@sales_bp.route("/liquidacion-diaria")
@login_required
def liquidacion_diaria():
    """
    Liquidacion diaria: muestra las ventas del dia (o de una fecha elegida)
    y los totales facturado, cobrado y pendiente por cobrar.
    """
    fecha_param = request.args.get("fecha")
    try:
        fecha = datetime.strptime(fecha_param, "%Y-%m-%d") if fecha_param else datetime.now()
    except ValueError:
        fecha = datetime.now()

    inicio = fecha.replace(hour=0, minute=0, second=0, microsecond=0)
    fin = inicio + timedelta(days=1)

    ventas_dia = Sale.query.filter(
        Sale.sale_date >= inicio,
        Sale.sale_date < fin,
    ).order_by(Sale.sale_date).all()

    total_dia = sum(s.total_amount or 0 for s in ventas_dia)
    cobrado_dia = sum(s.pagado_total() for s in ventas_dia)
    pendiente_dia = sum(s.saldo_pendiente() for s in ventas_dia)

    return render_template(
        "liquidacion_diaria.html",
        fecha=fecha,
        ventas_dia=ventas_dia,
        total_dia=total_dia,
        cobrado_dia=cobrado_dia,
        pendiente_dia=pendiente_dia,
    )
