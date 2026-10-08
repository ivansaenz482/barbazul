import os
import uuid
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (Supplier, Product, SupplierOrder, SupplierOrderDetail,
                        InventoryMovement, PurchaseInvoice, PurchaseInvoiceDetail)
from app.utils import role_required
from app.audit import registrar

supplier_orders_bp = Blueprint("supplier_orders", __name__, url_prefix="/pedidos-proveedor")


def _line_items_desde_form():
    """Lee los productos del formulario y devuelve (line_items, error)."""
    product_ids = request.form.getlist("product_id[]")
    quantities = request.form.getlist("quantity[]")
    costs = request.form.getlist("unit_cost[]")

    line_items = []
    for pid, qty, cost in zip(product_ids, quantities, costs):
        if not pid or not qty or not cost:
            continue
        product = Product.query.get(int(pid))
        try:
            quantity = int(qty)
            unit_cost = float(cost)
        except (TypeError, ValueError):
            continue
        if not product or quantity <= 0 or unit_cost < 0:
            continue
        line_items.append((product, quantity, unit_cost))

    if not line_items:
        return None, "Debes agregar al menos un producto con cantidad y costo válidos."
    return line_items, None


def _aplicar_stock(order, line_items, accion="creado"):
    """Suma el stock de cada linea a la bodega destino y registra movimientos."""
    for product, quantity, unit_cost in line_items:
        if order.bodega_destino == "matriz":
            product.stock_matriz = (product.stock_matriz or 0) + quantity
        else:
            product.current_stock = (product.current_stock or 0) + quantity
        product.cost_price = unit_cost
        db.session.add(InventoryMovement(
            product_id=product.product_id,
            movement_type="entrada",
            quantity=quantity,
            reference_type="pedido_proveedor",
            reference_id=order.order_id,
            user_id=current_user.user_id,
            notes=f"Pedido a proveedor {order.codigo()} -> {order.bodega_label()} ({accion})",
        ))


def _revertir_stock(order):
    """Devuelve el stock sumado por este pedido y borra sus movimientos."""
    for detalle in list(order.details):
        prod = detalle.product
        if prod:
            if order.bodega_destino == "matriz":
                prod.stock_matriz = max(0, (prod.stock_matriz or 0) - detalle.quantity)
            else:
                prod.current_stock = max(0, (prod.current_stock or 0) - detalle.quantity)
    for m in InventoryMovement.query.filter_by(
            reference_type="pedido_proveedor", reference_id=order.order_id).all():
        db.session.delete(m)


def _stock_aplicado(order):
    """True si el pedido ya tiene su stock sumado (existen movimientos de pedido)."""
    return InventoryMovement.query.filter_by(
        reference_type="pedido_proveedor", reference_id=order.order_id).count() > 0


@supplier_orders_bp.route("/")
@login_required
@role_required("administrador")
def orders_list():
    q = request.args.get("q", "").strip()
    query = SupplierOrder.query
    if q:
        like = f"%{q}%"
        query = query.join(Supplier).filter(
            db.or_(
                Supplier.name.ilike(like),
                SupplierOrder.order_number.ilike(like),
                db.cast(SupplierOrder.order_id, db.String).ilike(like),
            )
        )
    orders = query.order_by(SupplierOrder.order_id.desc()).all()
    return render_template("supplier_orders_list.html", orders=orders, q=q)


@supplier_orders_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def order_new():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.name).all()

    if request.method == "POST":
        supplier_id = request.form.get("supplier_id")
        supplier = Supplier.query.get(supplier_id) if supplier_id else None
        if not supplier:
            flash("Debes seleccionar un proveedor.", "danger")
            return render_template("supplier_order_form.html", suppliers=suppliers, products=products, today=date.today().isoformat())

        line_items, error = _line_items_desde_form()
        if error:
            flash(error, "danger")
            return render_template("supplier_order_form.html", suppliers=suppliers, products=products, today=date.today().isoformat())

        try:
            order_date = datetime.strptime(request.form.get("order_date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            order_date = date.today()

        bodega_destino = request.form.get("bodega_destino", "local")
        if bodega_destino not in ("local", "matriz"):
            bodega_destino = "local"

        order = SupplierOrder(
            order_number=request.form.get("order_number", "").strip() or None,
            supplier_id=supplier.supplier_id,
            order_date=order_date,
            bodega_destino=bodega_destino,
            status="borrador",
            notes=request.form.get("notes", "").strip() or None,
            created_by=current_user.user_id,
        )
        db.session.add(order)
        db.session.flush()

        # Codigo generado si no se indico uno
        if not order.order_number:
            order.order_number = f"PED-{order.order_id:05d}"

        total = 0
        for product, quantity, unit_cost in line_items:
            db.session.add(SupplierOrderDetail(
                order_id=order.order_id,
                product_id=product.product_id,
                quantity=quantity,
                unit_cost=unit_cost,
            ))
            total += quantity * unit_cost

        order.total_amount = total
        _aplicar_stock(order, line_items, accion="creado")

        # Control anti-duplicado: avisar si algun producto ya esta en otro pedido
        # pendiente del mismo proveedor (para no pedir lo mismo dos veces).
        pids = [p.product_id for p, _, _ in line_items]
        repetidos = []
        for o in SupplierOrder.query.filter(
                SupplierOrder.supplier_id == supplier.supplier_id,
                SupplierOrder.order_id != order.order_id,
                SupplierOrder.purchase_invoice_id.is_(None),
                SupplierOrder.status != "anulado").all():
            for d in o.details:
                if d.product_id in pids and d.product.name not in repetidos:
                    repetidos.append(d.product.name)
        if repetidos:
            flash("Aviso anti-duplicado: este proveedor ya tiene un pedido pendiente con: "
                  + ", ".join(repetidos) + ". Revisa que no estés duplicando el pedido.", "warning")

        db.session.commit()
        flash(f"Pedido a proveedor {order.codigo()} creado. Stock sumado a {order.bodega_label()}.", "success")
        registrar("pedido_creado", detalle=f"Pedido {order.codigo()} por ${float(order.total_amount or 0):.2f}", entidad="pedido", entidad_id=order.order_id)
        return redirect(url_for("supplier_orders.order_detail", order_id=order.order_id))

    return render_template("supplier_order_form.html", suppliers=suppliers, products=products, today=date.today().isoformat())


@supplier_orders_bp.route("/<int:order_id>")
@login_required
@role_required("administrador")
def order_detail(order_id):
    order = SupplierOrder.query.get_or_404(order_id)
    return render_template("supplier_order_detail.html", order=order)


@supplier_orders_bp.route("/<int:order_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def order_edit(order_id):
    order = SupplierOrder.query.get_or_404(order_id)
    if order.convertido():
        flash("Este pedido ya fue convertido en Compra. Edítalo desde el módulo Compras.", "warning")
        return redirect(url_for("supplier_orders.order_detail", order_id=order.order_id))
    suppliers = Supplier.query.order_by(Supplier.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.name).all()

    if request.method == "POST":
        supplier_id = request.form.get("supplier_id")
        supplier = Supplier.query.get(supplier_id) if supplier_id else None
        if not supplier:
            flash("Debes seleccionar un proveedor.", "danger")
            return render_template("supplier_order_form.html", order=order, suppliers=suppliers, products=products, today=date.today().isoformat())

        line_items, error = _line_items_desde_form()
        if error:
            flash(error, "danger")
            return render_template("supplier_order_form.html", order=order, suppliers=suppliers, products=products, today=date.today().isoformat())

        try:
            order_date = datetime.strptime(request.form.get("order_date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            order_date = order.order_date

        bodega_destino = request.form.get("bodega_destino", order.bodega_destino)
        if bodega_destino not in ("local", "matriz"):
            bodega_destino = order.bodega_destino

        # Revertir stock y movimientos anteriores antes de re-aplicar
        _revertir_stock(order)
        for detalle in list(order.details):
            db.session.delete(detalle)
        db.session.flush()

        order.supplier_id = supplier.supplier_id
        order.order_date = order_date
        order.bodega_destino = bodega_destino
        order.order_number = request.form.get("order_number", "").strip() or order.order_number
        order.notes = request.form.get("notes", "").strip() or None
        status = request.form.get("status", order.status)
        if status in ("borrador", "enviado", "recibido", "anulado"):
            order.status = status

        total = 0
        for product, quantity, unit_cost in line_items:
            db.session.add(SupplierOrderDetail(
                order_id=order.order_id,
                product_id=product.product_id,
                quantity=quantity,
                unit_cost=unit_cost,
            ))
            total += quantity * unit_cost

        order.total_amount = total
        _aplicar_stock(order, line_items, accion="editado")

        db.session.commit()
        flash(f"Pedido a proveedor {order.codigo()} actualizado. Stock recalculado.", "success")
        return redirect(url_for("supplier_orders.order_detail", order_id=order.order_id))

    return render_template("supplier_order_form.html", order=order, suppliers=suppliers, products=products, today=date.today().isoformat())


@supplier_orders_bp.route("/<int:order_id>/marcar", methods=["POST"])
@login_required
@role_required("administrador")
def order_marcar(order_id):
    order = SupplierOrder.query.get_or_404(order_id)
    nuevo = request.form.get("status", "")
    if nuevo in ("borrador", "enviado", "recibido", "anulado"):
        order.status = nuevo
        db.session.commit()
        flash(f"Pedido {order.codigo()} marcado como {order.status_label()}.", "success")
    return redirect(url_for("supplier_orders.order_detail", order_id=order.order_id))


@supplier_orders_bp.route("/<int:order_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def order_delete(order_id):
    order = SupplierOrder.query.get_or_404(order_id)
    if order.convertido():
        flash("Este pedido ya fue convertido en Compra. No se puede eliminar; gestiona la factura desde Compras.", "warning")
        return redirect(url_for("supplier_orders.order_detail", order_id=order.order_id))
    codigo = order.codigo()
    _revertir_stock(order)
    db.session.delete(order)
    db.session.commit()
    flash(f"Pedido a proveedor {codigo} eliminado. Stock devuelto.", "info")
    registrar("pedido_eliminado", detalle=f"Pedido {codigo} eliminado", entidad="pedido", entidad_id=order_id)
    return redirect(url_for("supplier_orders.orders_list"))


@supplier_orders_bp.route("/<int:order_id>/convertir", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def order_convert(order_id):
    """
    Convierte un pedido a proveedor en una Factura de Compra (cuando la
    mercaderia ya llego). Se quita el stock que sumo el pedido y la compra
    lo vuelve a registrar, quedando todo bajo el modulo Compras con su plazo.
    """
    order = SupplierOrder.query.get_or_404(order_id)

    if order.convertido():
        flash("Este pedido ya fue convertido en compra.", "info")
        return redirect(url_for("supplier_orders.order_detail", order_id=order.order_id))
    if not order.details:
        flash("El pedido no tiene productos para convertir.", "danger")
        return redirect(url_for("supplier_orders.order_detail", order_id=order.order_id))

    stock_ya_aplicado = _stock_aplicado(order)

    if request.method == "POST":
        # Control anti-duplicado: si el pedido ya sumo stock, exigir confirmacion
        # (asi se traspasa el inventario una sola vez, sin duplicar).
        if stock_ya_aplicado and request.form.get("confirmar_stock") != "1":
            flash("Este pedido ya sumó stock. Marca la casilla de confirmación para convertir sin duplicar.", "warning")
            return render_template("supplier_order_convert.html", order=order,
                                   today=date.today().isoformat(), stock_aplicado=True)

        try:
            invoice_date = datetime.strptime(request.form.get("invoice_date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            invoice_date = date.today()

        payment_type = request.form.get("payment_type", "credito")
        if payment_type not in ("efectivo", "credito"):
            payment_type = "credito"

        term = request.form.get("credit_term_days", order.supplier.credit_term_days or "0")
        if term not in ("0", "30", "60", "90"):
            term = "0"

        bodega = request.form.get("bodega_destino", order.bodega_destino)
        if bodega not in ("local", "matriz"):
            bodega = order.bodega_destino

        due_date = None
        if payment_type == "credito":
            dias = int(term) if int(term) > 0 else 30
            due_date = invoice_date + timedelta(days=dias)

        # 1) Quitar el stock que habia sumado el pedido
        _revertir_stock(order)
        db.session.flush()

        # 2) Crear la factura de compra con el plazo del proveedor
        invoice = PurchaseInvoice(
            supplier_id=order.supplier_id,
            invoice_number=request.form.get("invoice_number", "").strip() or None,
            invoice_date=invoice_date,
            source_type="manual",
            registered_by=current_user.user_id,
            payment_type=payment_type,
            due_date=due_date,
            status="pendiente",
        )
        db.session.add(invoice)
        db.session.flush()

        # Adjuntar imagen/PDF de la factura del proveedor (opcional)
        archivo = request.files.get("factura_imagen")
        if archivo and archivo.filename:
            ext = archivo.filename.rsplit(".", 1)[-1].lower() if "." in archivo.filename else ""
            if ext in ("png", "jpg", "jpeg", "webp", "gif", "pdf"):
                os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
                fname = secure_filename(archivo.filename)
                unique = f"{uuid.uuid4().hex}_{fname}"
                save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique)
                archivo.save(save_path)
                invoice.file_path = save_path
                invoice.source_type = "pdf" if ext == "pdf" else "imagen"

        total = 0
        for detalle in order.details:
            db.session.add(PurchaseInvoiceDetail(
                invoice_id=invoice.invoice_id,
                product_id=detalle.product_id,
                quantity=detalle.quantity,
                unit_cost=detalle.unit_cost,
            ))
            product = detalle.product
            if product:
                if bodega == "matriz":
                    product.stock_matriz = (product.stock_matriz or 0) + detalle.quantity
                else:
                    product.current_stock = (product.current_stock or 0) + detalle.quantity
                product.cost_price = detalle.unit_cost
                db.session.add(InventoryMovement(
                    product_id=product.product_id,
                    movement_type="entrada",
                    quantity=detalle.quantity,
                    reference_type="compra",
                    reference_id=invoice.invoice_id,
                    user_id=current_user.user_id,
                    notes=f"Compra #{invoice.invoice_id} desde pedido {order.codigo()} -> bodega {bodega}",
                ))
            total += detalle.quantity * float(detalle.unit_cost)

        invoice.total_amount = total
        order.purchase_invoice_id = invoice.invoice_id
        order.status = "recibido"

        db.session.commit()
        flash(f"Pedido {order.codigo()} convertido en Compra #{invoice.invoice_id}. "
              f"Stock registrado en bodega {bodega}.", "success")
        registrar("pedido_convertido", detalle=f"Pedido {order.codigo()} -> Compra #{invoice.invoice_id}", entidad="pedido", entidad_id=order.order_id)
        return redirect(url_for("purchases.purchase_detail", invoice_id=invoice.invoice_id))

    return render_template("supplier_order_convert.html", order=order,
                           today=date.today().isoformat(), stock_aplicado=stock_ya_aplicado)
