import os
import uuid
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Supplier, Product, PurchaseInvoice, PurchaseInvoiceDetail, SupplierPayment, InventoryMovement, SupplierOrder
from app.ocr_utils import extract_text, configure_tesseract, OCRNotAvailableError
from app.utils import role_required
from app.audit import registrar

purchases_bp = Blueprint("purchases", __name__, url_prefix="/compras")


def _allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


@purchases_bp.route("/")
@login_required
@role_required("administrador")
def purchases_list():
    invoices = PurchaseInvoice.query.order_by(PurchaseInvoice.created_at.desc()).all()
    return render_template("purchases_list.html", invoices=invoices)


@purchases_bp.route("/nueva", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def purchase_new():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.name).all()

    context = {
        "suppliers": suppliers,
        "products": products,
        "ocr_text": "",
        "file_path": "",
        "source_type": "manual",
        "supplier_id": "",
        "invoice_number": "",
        "invoice_date": datetime.now().strftime("%Y-%m-%d"),
        "stage": "upload",
    }

    if request.method == "POST":
        action = request.form.get("action")

        # -----------------------------------------------------------
        # PASO 1: subir el archivo (imagen/PDF) y extraer el texto con OCR
        # -----------------------------------------------------------
        if action == "extract":
            context["supplier_id"] = request.form.get("supplier_id", "")
            context["invoice_number"] = request.form.get("invoice_number", "").strip()
            context["invoice_date"] = request.form.get("invoice_date") or context["invoice_date"]
            context["source_type"] = request.form.get("source_type", "manual")

            file = request.files.get("invoice_file")

            if context["source_type"] in ("imagen", "pdf"):
                if not file or file.filename == "":
                    flash("Debes seleccionar un archivo de imagen o PDF.", "danger")
                    return render_template("purchase_form.html", **context)

                if not _allowed_file(file.filename):
                    flash("Formato no permitido. Usa PDF, PNG o JPG.", "danger")
                    return render_template("purchase_form.html", **context)

                filename = secure_filename(file.filename)
                unique_name = f"{uuid.uuid4().hex}_{filename}"
                save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name)
                os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
                file.save(save_path)

                context["file_path"] = save_path

                try:
                    configure_tesseract(current_app.config["TESSERACT_CMD"])
                    extension = filename.rsplit(".", 1)[-1]
                    texto = extract_text(save_path, extension)
                    context["ocr_text"] = texto or "(No se pudo extraer texto legible de este archivo. Ingresa los productos manualmente abajo.)"
                    flash("Texto extraído correctamente. Revísalo y agrega los productos de la factura abajo.", "success")
                except OCRNotAvailableError as e:
                    context["ocr_text"] = ""
                    flash(str(e), "warning")
                except Exception as e:
                    context["ocr_text"] = ""
                    flash(f"No se pudo procesar el archivo: {e}", "danger")

            # Si es "manual", simplemente continua al formulario de productos sin OCR
            context["stage"] = "products"
            return render_template("purchase_form.html", **context)

        # -----------------------------------------------------------
        # PASO 2: confirmar productos, cantidades y costos -> guardar compra
        # -----------------------------------------------------------
        elif action == "confirm":
            supplier_id = request.form.get("supplier_id")
            supplier = Supplier.query.get(supplier_id) if supplier_id else None
            invoice_date_str = request.form.get("invoice_date")
            source_type = request.form.get("source_type", "manual")
            file_path = request.form.get("file_path") or None
            ocr_text = request.form.get("ocr_text") or None

            context.update({
                "supplier_id": supplier_id or "",
                "invoice_number": request.form.get("invoice_number", ""),
                "invoice_date": invoice_date_str or context["invoice_date"],
                "source_type": source_type,
                "file_path": file_path or "",
                "ocr_text": ocr_text or "",
                "bodega_destino": request.form.get("bodega_destino", "local"),
                "stage": "products",
            })

            if not supplier:
                flash("Debes seleccionar un proveedor.", "danger")
                return render_template("purchase_form.html", **context)

            product_ids = request.form.getlist("product_id[]")
            quantities = request.form.getlist("quantity[]")
            costs = request.form.getlist("unit_cost[]")

            line_items = []
            for pid, qty, cost in zip(product_ids, quantities, costs):
                if not pid or not qty or not cost:
                    continue
                product = Product.query.get(int(pid))
                quantity = int(qty)
                unit_cost = float(cost)
                if not product or quantity <= 0 or unit_cost < 0:
                    continue
                line_items.append((product, quantity, unit_cost))

            if not line_items:
                flash("Debes agregar al menos un producto con cantidad y costo válidos.", "danger")
                return render_template("purchase_form.html", **context)

            try:
                invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                invoice_date = datetime.now().date()

            # Condición de pago: efectivo (contado) o crédito. El vencimiento se
            # calcula según el plazo del proveedor si el usuario no lo especifica.
            # Si el usuario la especifica, se valida que no exceda el plazo permitido.
            payment_type = request.form.get("payment_type", "efectivo")
            if payment_type not in ("efectivo", "credito"):
                payment_type = "efectivo"

            due_date_str = request.form.get("due_date", "").strip()
            due_date = None
            if payment_type == "credito":
                # Días permitidos por el proveedor (0 = contado, en crédito se usa 30 por defecto)
                term_dias = int(supplier.credit_term_days or "0")
                if term_dias == 0:
                    term_dias = 30
                max_due = invoice_date + timedelta(days=term_dias)
                if due_date_str:
                    try:
                        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                    except ValueError:
                        flash("Fecha de vencimiento inválida.", "danger")
                        return render_template("purchase_form.html", **context)
                    if due_date < invoice_date:
                        flash("La fecha de vencimiento no puede ser anterior a la fecha de la factura.", "danger")
                        return render_template("purchase_form.html", **context)
                    if due_date > max_due:
                        flash(f"La fecha de vencimiento excede el plazo permitido para este proveedor (máx. {term_dias} días → {max_due.strftime('%d/%m/%Y')}).", "danger")
                        return render_template("purchase_form.html", **context)
                else:
                    due_date = max_due

            invoice = PurchaseInvoice(
                supplier_id=supplier.supplier_id,
                invoice_number=request.form.get("invoice_number", "").strip() or None,
                invoice_date=invoice_date,
                source_type=source_type,
                file_path=file_path,
                ocr_raw_text=ocr_text,
                registered_by=current_user.user_id,
                payment_type=payment_type,
                due_date=due_date,
                status="pendiente",
            )
            db.session.add(invoice)
            db.session.flush()

            # Bodega destino: "local" (current_stock) o "matriz" (stock_matriz)
            bodega_destino = request.form.get("bodega_destino", "local")
            if bodega_destino not in ("local", "matriz"):
                bodega_destino = "local"

            total_amount = 0
            for product, quantity, unit_cost in line_items:
                db.session.add(PurchaseInvoiceDetail(
                    invoice_id=invoice.invoice_id,
                    product_id=product.product_id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                ))

                # Actualizar stock (bodega elegida) y costo del producto (entrada de mercaderia)
                if bodega_destino == "matriz":
                    product.stock_matriz = (product.stock_matriz or 0) + quantity
                else:
                    product.current_stock += quantity
                product.cost_price = unit_cost  # actualiza al costo mas reciente

                db.session.add(InventoryMovement(
                    product_id=product.product_id,
                    movement_type="entrada",
                    quantity=quantity,
                    reference_type="compra",
                    reference_id=invoice.invoice_id,
                    user_id=current_user.user_id,
                    notes=f"Compra #{invoice.invoice_id} -> bodega {bodega_destino}",
                ))

                total_amount += quantity * unit_cost

            invoice.total_amount = total_amount

            # Registrar pago inicial si se indicó (permite dejar como Pendiente de pago o marcar como Pagada)
            registrar_pago = request.form.get("registrar_pago") == "on"
            initial_amount_str = request.form.get("initial_payment_amount", "").strip()
            initial_method = request.form.get("initial_payment_method", "efectivo")
            initial_receipt = request.form.get("initial_receipt_number", "").strip() or None

            if registrar_pago:
                if initial_amount_str:
                    try:
                        initial_amount = float(initial_amount_str)
                    except ValueError:
                        flash("Monto de pago inicial inválido.", "danger")
                        return render_template("purchase_form.html", **context)
                    if initial_amount <= 0 or initial_amount > total_amount:
                        flash(f"El monto del pago inicial debe estar entre 0.01 y {total_amount:.2f}.", "danger")
                        return render_template("purchase_form.html", **context)
                else:
                    # Si no se indica monto, se asume pago total (útil para contado pagado)
                    initial_amount = total_amount

                db.session.add(SupplierPayment(
                    invoice_id=invoice.invoice_id,
                    amount=initial_amount,
                    payment_method=initial_method,
                    receipt_number=initial_receipt,
                    registered_by=current_user.user_id,
                ))
                # Estado según si cubre el total: Pendiente si queda saldo, Pagado si cubre todo
                if total_amount - initial_amount <= 0.009:
                    invoice.status = "pagado"
                else:
                    invoice.status = "pendiente"
            else:
                # Sin pago inicial → queda Pendiente de pago (ideal para plazos 30/60/90 días / 3 meses)
                invoice.status = "pendiente"

            db.session.commit()

            estado_txt = "Pendiente de pago" if invoice.status == "pendiente" else "Pagada"
            flash(f"Factura de compra #{invoice.invoice_id} registrada ({estado_txt}, {payment_type}, vencimiento {due_date.strftime('%d/%m/%Y') if due_date else '—'}). Stock actualizado (bodega {bodega_destino}).", "success")
            registrar("compra_creada", detalle=f"Compra #{invoice.invoice_id} por ${float(invoice.total_amount or 0):.2f}", entidad="compra", entidad_id=invoice.invoice_id)
            return redirect(url_for("purchases.purchase_detail", invoice_id=invoice.invoice_id))

    return render_template("purchase_form.html", **context)


@purchases_bp.route("/<int:invoice_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def purchase_edit(invoice_id):
    invoice = PurchaseInvoice.query.get_or_404(invoice_id)
    suppliers = Supplier.query.order_by(Supplier.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.name).all()

    # Determinar bodega destino original a partir de los movimientos (si existe)
    movements = InventoryMovement.query.filter_by(reference_type="compra", reference_id=invoice.invoice_id).all()
    bodega_actual = "local"
    if movements and any("matriz" in (m.notes or "").lower() for m in movements):
        bodega_actual = "matriz"

    if request.method == "POST":
        supplier_id = request.form.get("supplier_id")
        supplier = Supplier.query.get(supplier_id) if supplier_id else None
        invoice_number = request.form.get("invoice_number", "").strip() or None
        invoice_date_str = request.form.get("invoice_date")
        payment_type = request.form.get("payment_type", "efectivo")
        if payment_type not in ("efectivo", "credito"):
            payment_type = "efectivo"
        due_date_str = request.form.get("due_date", "").strip()
        bodega_destino = request.form.get("bodega_destino", bodega_actual)
        if bodega_destino not in ("local", "matriz"):
            bodega_destino = bodega_actual

        if not supplier:
            flash("Debes seleccionar un proveedor.", "danger")
            return render_template("purchase_edit.html", invoice=invoice, suppliers=suppliers, products=products, bodega_actual=bodega_destino)

        try:
            invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            flash("Fecha de la factura inválida.", "danger")
            return render_template("purchase_edit.html", invoice=invoice, suppliers=suppliers, products=products, bodega_actual=bodega_destino)

        # Validar fecha de vencimiento dentro del plazo del proveedor
        due_date = None
        if payment_type == "credito":
            term_dias = int(supplier.credit_term_days or "0")
            if term_dias == 0:
                term_dias = 30
            max_due = invoice_date + timedelta(days=term_dias)
            if due_date_str:
                try:
                    due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                except ValueError:
                    flash("Fecha de vencimiento inválida.", "danger")
                    return render_template("purchase_edit.html", invoice=invoice, suppliers=suppliers, products=products, bodega_actual=bodega_destino)
                if due_date < invoice_date:
                    flash("La fecha de vencimiento no puede ser anterior a la fecha de la factura.", "danger")
                    return render_template("purchase_edit.html", invoice=invoice, suppliers=suppliers, products=products, bodega_actual=bodega_destino)
                if due_date > max_due:
                    flash(f"La fecha de vencimiento excede el plazo permitido para este proveedor (máx. {term_dias} días → {max_due.strftime('%d/%m/%Y')}).", "danger")
                    return render_template("purchase_edit.html", invoice=invoice, suppliers=suppliers, products=products, bodega_actual=bodega_destino)
            else:
                due_date = max_due

        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        costs = request.form.getlist("unit_cost[]")

        line_items = []
        for pid, qty, cost in zip(product_ids, quantities, costs):
            if not pid or not qty or not cost:
                continue
            product = Product.query.get(int(pid))
            quantity = int(qty)
            unit_cost = float(cost)
            if not product or quantity <= 0 or unit_cost < 0:
                continue
            line_items.append((product, quantity, unit_cost))

        if not line_items:
            flash("Debes agregar al menos un producto con cantidad y costo válidos.", "danger")
            return render_template("purchase_edit.html", invoice=invoice, suppliers=suppliers, products=products, bodega_actual=bodega_destino)

        # Revertir stock anterior (usando los movimientos para saber la bodega)
        for detalle in list(invoice.details):
            mv_list = InventoryMovement.query.filter_by(reference_type="compra", reference_id=invoice.invoice_id, product_id=detalle.product_id).all()
            is_matriz = any("matriz" in (m.notes or "").lower() for m in mv_list) if mv_list else (bodega_actual == "matriz")
            prod = detalle.product
            if prod:
                if is_matriz:
                    prod.stock_matriz = max(0, (prod.stock_matriz or 0) - detalle.quantity)
                else:
                    prod.current_stock = max(0, (prod.current_stock or 0) - detalle.quantity)
            for m in mv_list:
                db.session.delete(m)
            db.session.delete(detalle)
        db.session.flush()

        # Actualizar cabecera
        invoice.supplier_id = supplier.supplier_id
        invoice.invoice_number = invoice_number
        invoice.invoice_date = invoice_date
        invoice.payment_type = payment_type
        invoice.due_date = due_date

        total_amount = 0
        for product, quantity, unit_cost in line_items:
            db.session.add(PurchaseInvoiceDetail(
                invoice_id=invoice.invoice_id,
                product_id=product.product_id,
                quantity=quantity,
                unit_cost=unit_cost,
            ))
            if bodega_destino == "matriz":
                product.stock_matriz = (product.stock_matriz or 0) + quantity
            else:
                product.current_stock = (product.current_stock or 0) + quantity
            product.cost_price = unit_cost
            db.session.add(InventoryMovement(
                product_id=product.product_id,
                movement_type="entrada",
                quantity=quantity,
                reference_type="compra",
                reference_id=invoice.invoice_id,
                user_id=current_user.user_id,
                notes=f"Compra #{invoice.invoice_id} -> bodega {bodega_destino} (editada)",
            ))
            total_amount += quantity * unit_cost

        invoice.total_amount = total_amount
        # Actualizar estado según pagos existentes
        if invoice.saldo_pendiente() <= 0.009 and invoice.total_amount > 0:
            # Si ya estaba pagada o los pagos cubren el nuevo total, mantener pagado
            if invoice.payments:
                invoice.status = "pagado"
            else:
                invoice.status = "pendiente"
        else:
            invoice.status = "pendiente"
        # Si ya está pagada y ahora tiene saldo, volver a pendiente
        if invoice.payments and invoice.saldo_pendiente() > 0.009:
            invoice.status = "pendiente"

        db.session.commit()
        flash(f"Factura de compra #{invoice.invoice_id} actualizada correctamente.", "success")
        return redirect(url_for("purchases.purchase_detail", invoice_id=invoice.invoice_id))

    return render_template("purchase_edit.html", invoice=invoice, suppliers=suppliers, products=products, bodega_actual=bodega_actual)


@purchases_bp.route("/<int:invoice_id>")
@login_required
@role_required("administrador")
def purchase_detail(invoice_id):
    invoice = PurchaseInvoice.query.get_or_404(invoice_id)
    origen_order = SupplierOrder.query.filter_by(purchase_invoice_id=invoice.invoice_id).first()
    return render_template("purchase_detail.html", invoice=invoice, origen_order=origen_order)


@purchases_bp.route("/<int:invoice_id>/archivo")
@login_required
@role_required("administrador")
def purchase_file(invoice_id):
    invoice = PurchaseInvoice.query.get_or_404(invoice_id)
    if not invoice.file_path or not os.path.isfile(invoice.file_path):
        abort(404)
    return send_file(invoice.file_path)


@purchases_bp.route("/<int:invoice_id>/pago", methods=["POST"])
@login_required
@role_required("administrador")
def purchase_add_payment(invoice_id):
    invoice = PurchaseInvoice.query.get_or_404(invoice_id)

    amount = request.form.get("amount", "").strip()
    method = request.form.get("payment_method", "efectivo")
    receipt = request.form.get("receipt_number", "").strip() or None
    notes = request.form.get("notes", "").strip() or None

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        amount = 0

    if amount <= 0:
        flash("El monto del pago debe ser mayor a cero.", "danger")
        return redirect(url_for("purchases.purchase_detail", invoice_id=invoice.invoice_id))

    saldo = invoice.saldo_pendiente()
    if amount > saldo:
        flash(f"El pago supera el saldo pendiente (${saldo:.2f}).", "danger")
        return redirect(url_for("purchases.purchase_detail", invoice_id=invoice.invoice_id))

    db.session.add(SupplierPayment(
        invoice_id=invoice.invoice_id,
        amount=amount,
        payment_method=method,
        receipt_number=receipt,
        notes=notes,
        registered_by=current_user.user_id,
    ))

    if invoice.saldo_pendiente() - amount <= 0.009:
        invoice.status = "pagado"
    db.session.commit()

    flash(f"Pago de ${amount:.2f} registrado para la factura #{invoice.invoice_id}.", "success")
    return redirect(url_for("purchases.purchase_detail", invoice_id=invoice.invoice_id))


@purchases_bp.route("/<int:invoice_id>/pago/<int:payment_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def purchase_delete_payment(invoice_id, payment_id):
    invoice = PurchaseInvoice.query.get_or_404(invoice_id)
    payment = SupplierPayment.query.get_or_404(payment_id)
    if payment.invoice_id != invoice.invoice_id:
        abort(404)
    monto = float(payment.amount)
    db.session.delete(payment)
    db.session.flush()
    # Recalcular estado: pendiente si queda saldo, pagado si se cubre y aún hay pagos
    if invoice.saldo_pendiente() <= 0.009 and invoice.payments:
        invoice.status = "pagado"
    else:
        invoice.status = "pendiente"
    db.session.commit()
    flash(f"Pago de ${monto:.2f} eliminado. Saldo actual: ${invoice.saldo_pendiente():.2f}.", "info")
    return redirect(url_for("purchases.purchase_detail", invoice_id=invoice.invoice_id))


@purchases_bp.route("/<int:invoice_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def purchase_delete(invoice_id):
    invoice = PurchaseInvoice.query.get_or_404(invoice_id)
    # Revertir stock según la bodega real de cada movimiento
    for detalle in list(invoice.details):
        mv_list = InventoryMovement.query.filter_by(reference_type="compra", reference_id=invoice.invoice_id, product_id=detalle.product_id).all()
        is_matriz = any("matriz" in (m.notes or "").lower() for m in mv_list) if mv_list else False
        prod = detalle.product
        if prod:
            if is_matriz:
                prod.stock_matriz = max(0, (prod.stock_matriz or 0) - detalle.quantity)
            else:
                prod.current_stock = max(0, (prod.current_stock or 0) - detalle.quantity)
        for m in mv_list:
            db.session.delete(m)
    # Los pagos y detalles se borran por cascade al eliminar la factura,
    # pero borramos movimientos restantes por si acaso
    for m in InventoryMovement.query.filter_by(reference_type="compra", reference_id=invoice.invoice_id).all():
        db.session.delete(m)
    db.session.delete(invoice)
    db.session.commit()
    flash(f"Factura de compra #{invoice.invoice_id} eliminada. Stock revertido.", "info")
    registrar("compra_eliminada", detalle=f"Compra #{invoice_id} eliminada", entidad="compra", entidad_id=invoice_id)
    return redirect(url_for("purchases.purchases_list"))


@purchases_bp.route("/pagos")
@login_required
@role_required("administrador")
def purchases_payments_list():
    """Vista rápida de todos los pagos a proveedores con filtros + enlace al reporte."""
    supplier_id = request.args.get("supplier_id", "").strip()
    metodo = request.args.get("metodo", "").strip()
    desde = request.args.get("desde", "").strip()
    hasta = request.args.get("hasta", "").strip()

    query = SupplierPayment.query.join(PurchaseInvoice)
    if supplier_id:
        query = query.filter(PurchaseInvoice.supplier_id == int(supplier_id))
    if metodo in ("efectivo", "cheque", "transferencia", "tarjeta", "otro"):
        query = query.filter(SupplierPayment.payment_method == metodo)
    if desde:
        query = query.filter(SupplierPayment.payment_date >= datetime.strptime(desde, "%Y-%m-%d"))
    if hasta:
        query = query.filter(SupplierPayment.payment_date < datetime.strptime(hasta, "%Y-%m-%d").replace(hour=23, minute=59, second=59))

    pagos = query.order_by(SupplierPayment.payment_date.desc()).limit(200).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("purchases_pagos.html", pagos=pagos, suppliers=suppliers,
                           selected_supplier=supplier_id, selected_metodo=metodo, desde=desde, hasta=hasta)
