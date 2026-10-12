from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Product, InventoryMovement, StockTransfer, StockTransferDetail
from app.utils import perm_required
from app.audit import registrar
from app.routes.sales import _stock_bodega, _restar_stock_bodega, _sumar_stock_bodega, _bodega_label

transfers_bp = Blueprint("transfers", __name__, url_prefix="/transferencias")

BODEGAS = ("local", "matriz")


@transfers_bp.route("/")
@login_required
@perm_required("can_view_inventario")
def transfers_list():
    transferencias = (StockTransfer.query
                      .order_by(StockTransfer.fecha.desc(), StockTransfer.transfer_id.desc())
                      .all())
    return render_template("transfers_list.html", transferencias=transferencias)


@transfers_bp.route("/nueva", methods=["GET", "POST"])
@login_required
@perm_required("can_edit_stock")
def transfer_new():
    products = Product.query.filter_by(active=True).order_by(Product.name).all()

    if request.method == "POST":
        origen = request.form.get("bodega_origen", "local")
        destino = request.form.get("bodega_destino", "matriz")
        if origen not in BODEGAS or destino not in BODEGAS:
            flash("Bodega no válida.", "danger")
            return render_template("transfer_form.html", products=products)

        if origen == destino:
            flash("La bodega de origen y la de destino deben ser diferentes.", "danger")
            return render_template("transfer_form.html", products=products)

        motivo = request.form.get("motivo", "").strip() or None
        product_ids = request.form.getlist("product_id[]")
        cantidades = request.form.getlist("quantity[]")

        lineas = []
        for pid, cant in zip(product_ids, cantidades):
            if not pid or not cant:
                continue
            product = Product.query.get(int(pid))
            if not product or not product.active:
                flash("Uno de los productos ya no está disponible.", "danger")
                return render_template("transfer_form.html", products=products)
            try:
                qty = int(cant)
            except ValueError:
                qty = 0
            if qty <= 0:
                continue
            disponible = _stock_bodega(product, origen)
            if qty > disponible:
                flash(f"Stock insuficiente en {_bodega_label(origen)} para '{product.name}'. Disponible: {disponible}.", "danger")
                return render_template("transfer_form.html", products=products)
            lineas.append((product, qty))

        if not lineas:
            flash("Debes agregar al menos un producto con cantidad mayor a 0.", "danger")
            return render_template("transfer_form.html", products=products)

        transfer = StockTransfer(
            bodega_origen=origen,
            bodega_destino=destino,
            motivo=motivo,
            user_id=current_user.user_id,
        )
        db.session.add(transfer)
        db.session.flush()

        for product, qty in lineas:
            db.session.add(StockTransferDetail(
                transfer_id=transfer.transfer_id,
                product_id=product.product_id,
                quantity=qty,
            ))
            _restar_stock_bodega(product, origen, qty)
            _sumar_stock_bodega(product, destino, qty)
            nota = f"Transferencia #{transfer.transfer_id}: {_bodega_label(origen)} -> {_bodega_label(destino)}"
            db.session.add(InventoryMovement(
                product_id=product.product_id, movement_type="salida", quantity=qty,
                reference_type="transferencia", reference_id=transfer.transfer_id,
                user_id=current_user.user_id, notes=nota,
            ))
            db.session.add(InventoryMovement(
                product_id=product.product_id, movement_type="entrada", quantity=qty,
                reference_type="transferencia", reference_id=transfer.transfer_id,
                user_id=current_user.user_id, notes=nota,
            ))

        db.session.commit()
        flash(f"Transferencia #{transfer.transfer_id} registrada: {transfer.total_unidades()} unidad(es) de {_bodega_label(origen)} a {_bodega_label(destino)}.", "success")
        registrar("transferencia_creada",
                  detalle=f"Transferencia #{transfer.transfer_id}: {_bodega_label(origen)} -> {_bodega_label(destino)} ({transfer.total_unidades()} und.)",
                  entidad="transferencia", entidad_id=transfer.transfer_id)
        return redirect(url_for("transfers.transfer_detail", transfer_id=transfer.transfer_id))

    return render_template("transfer_form.html", products=products)


@transfers_bp.route("/<int:transfer_id>")
@login_required
@perm_required("can_view_inventario")
def transfer_detail(transfer_id):
    transfer = StockTransfer.query.get_or_404(transfer_id)
    return render_template("transfer_detail.html", transfer=transfer)


@transfers_bp.route("/<int:transfer_id>/eliminar", methods=["POST"])
@login_required
@perm_required("can_edit_stock")
def transfer_delete(transfer_id):
    transfer = StockTransfer.query.get_or_404(transfer_id)
    origen = transfer.bodega_origen
    destino = transfer.bodega_destino

    for detalle in list(transfer.details):
        product = detalle.product
        if product:
            _sumar_stock_bodega(product, origen, detalle.quantity)
            _restar_stock_bodega(product, destino, detalle.quantity)
            db.session.add(InventoryMovement(
                product_id=product.product_id, movement_type="ajuste", quantity=detalle.quantity,
                reference_type="transferencia", reference_id=transfer.transfer_id,
                user_id=current_user.user_id,
                notes=f"Anula transferencia #{transfer.transfer_id}: {_bodega_label(destino)} -> {_bodega_label(origen)}",
            ))

    numero = transfer.transfer_id
    db.session.delete(transfer)
    db.session.commit()
    flash(f"Transferencia #{numero} eliminada y stock devuelto a su origen.", "info")
    registrar("transferencia_eliminada", detalle=f"Transferencia #{numero} anulada", entidad="transferencia", entidad_id=numero)
    return redirect(url_for("transfers.transfers_list"))
