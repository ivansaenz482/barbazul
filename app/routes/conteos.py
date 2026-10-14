"""
Inventario fisico con conteo: se crea una sesion de conteo por ubicacion,
se digita la cantidad contada de cada producto, y al finalizar el sistema
genera los ajustes (movimientos de inventario) para cuadrar el stock.
"""
from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Product, InventoryMovement, ConteoInventario, ConteoDetalle
from app.utils import perm_required
from app.audit import registrar
from app.stock import (stock_en, sumar_stock, restar_stock, etiqueta_ubicacion,
                       es_ubicacion_valida, listar_ubicaciones)

conteos_bp = Blueprint("conteos", __name__, url_prefix="/conteos")


@conteos_bp.route("/")
@login_required
@perm_required("can_view_inventario")
def conteos_list():
    conteos = ConteoInventario.query.order_by(ConteoInventario.id.desc()).all()
    return render_template("conteos_list.html", conteos=conteos,
                           ubicacion_label=etiqueta_ubicacion)


@conteos_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@perm_required("can_edit_stock")
def conteo_nuevo():
    if request.method == "POST":
        ubicacion = request.form.get("ubicacion", "local")
        if not es_ubicacion_valida(ubicacion):
            flash("Ubicación no válida.", "danger")
            return redirect(url_for("conteos.conteo_nuevo"))

        try:
            fecha = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            fecha = date.today()

        nombre = request.form.get("nombre", "").strip() or f"Conteo {fecha.strftime('%d/%m/%Y')}"
        conteo = ConteoInventario(
            nombre=nombre, ubicacion=ubicacion, fecha=fecha,
            notas=request.form.get("notas", "").strip() or None,
            user_id=current_user.user_id, estado="en_proceso",
        )
        db.session.add(conteo)
        db.session.flush()

        productos = Product.query.filter_by(active=True).order_by(Product.name).all()
        for p in productos:
            db.session.add(ConteoDetalle(
                conteo_id=conteo.id, product_id=p.product_id,
                stock_sistema=stock_en(p, ubicacion),
            ))
        db.session.commit()
        registrar("conteo_creado", detalle=f"Conteo #{conteo.id} ({etiqueta_ubicacion(ubicacion)})",
                  entidad="conteo", entidad_id=conteo.id)
        flash(f"Conteo #{conteo.id} iniciado con {len(productos)} producto(s).", "success")
        return redirect(url_for("conteos.conteo_detalle", conteo_id=conteo.id))

    return render_template("conteo_nuevo.html", ubicaciones=listar_ubicaciones(),
                           today=date.today().isoformat())


@conteos_bp.route("/<int:conteo_id>")
@login_required
@perm_required("can_view_inventario")
def conteo_detalle(conteo_id):
    conteo = ConteoInventario.query.get_or_404(conteo_id)
    q = request.args.get("q", "").strip()
    detalles = conteo.detalles
    if q:
        like = q.lower()
        detalles = [d for d in detalles if like in (d.product.name or "").lower()
                    or like in (d.product.sku or "").lower()
                    or like in (d.product.barcode or "").lower()]
    detalles = sorted(detalles, key=lambda d: (d.product.name or ""))
    return render_template("conteo_detalle.html", conteo=conteo, detalles=detalles, q=q,
                           ubicacion_label=etiqueta_ubicacion)


@conteos_bp.route("/<int:conteo_id>/guardar", methods=["POST"])
@login_required
@perm_required("can_edit_stock")
def conteo_guardar(conteo_id):
    conteo = ConteoInventario.query.get_or_404(conteo_id)
    if conteo.estado == "cerrado":
        flash("Este conteo ya está cerrado.", "warning")
        return redirect(url_for("conteos.conteo_detalle", conteo_id=conteo_id))

    for d in conteo.detalles:
        valor = request.form.get(f"cnt_{d.id}", "").strip()
        if valor == "":
            d.cantidad_contada = None
        else:
            try:
                d.cantidad_contada = max(0, int(float(valor)))
            except (ValueError, TypeError):
                d.cantidad_contada = None
    db.session.commit()
    flash("Conteo guardado. Puedes seguir contando o finalizar.", "success")
    return redirect(url_for("conteos.conteo_detalle", conteo_id=conteo_id))


@conteos_bp.route("/<int:conteo_id>/finalizar", methods=["POST"])
@login_required
@perm_required("can_edit_stock")
def conteo_finalizar(conteo_id):
    conteo = ConteoInventario.query.get_or_404(conteo_id)
    if conteo.estado == "cerrado":
        flash("Este conteo ya fue cerrado.", "warning")
        return redirect(url_for("conteos.conteo_detalle", conteo_id=conteo_id))

    ubicacion = conteo.ubicacion
    # Guardar lo digitado en el formulario antes de aplicar
    for d in conteo.detalles:
        valor = request.form.get(f"cnt_{d.id}", "").strip()
        if valor == "":
            d.cantidad_contada = None
        else:
            try:
                d.cantidad_contada = max(0, int(float(valor)))
            except (ValueError, TypeError):
                d.cantidad_contada = None

    ajustes = 0
    for d in conteo.detalles:
        if d.cantidad_contada is None:
            continue
        actual = stock_en(d.product, ubicacion)
        if d.cantidad_contada == actual:
            continue
        delta = d.cantidad_contada - actual
        if delta > 0:
            sumar_stock(d.product, ubicacion, delta)
        else:
            restar_stock(d.product, ubicacion, -delta)
        db.session.add(InventoryMovement(
            product_id=d.product_id, movement_type="ajuste", quantity=abs(delta),
            reference_type="ajuste_manual", reference_id=None,
            user_id=current_user.user_id,
            notes=f"Ajuste {etiqueta_ubicacion(ubicacion)}: {actual} -> {d.cantidad_contada} (Conteo #{conteo.id})",
        ))
        ajustes += 1

    conteo.estado = "cerrado"
    conteo.cerrado_at = datetime.now()
    db.session.commit()
    registrar("conteo_finalizado",
              detalle=f"Conteo #{conteo.id} finalizado: {ajustes} ajuste(s) ({etiqueta_ubicacion(ubicacion)})",
              entidad="conteo", entidad_id=conteo.id)
    flash(f"Conteo finalizado. Se aplicaron {ajustes} ajuste(s) de inventario.", "success")
    return redirect(url_for("conteos.conteo_detalle", conteo_id=conteo_id))


@conteos_bp.route("/<int:conteo_id>/imprimir")
@login_required
@perm_required("can_view_inventario")
def conteo_imprimir(conteo_id):
    conteo = ConteoInventario.query.get_or_404(conteo_id)
    detalles = sorted(conteo.detalles, key=lambda d: (d.product.name or ""))
    return render_template("conteo_print.html", conteo=conteo, detalles=detalles,
                           ubicacion_label=etiqueta_ubicacion)


@conteos_bp.route("/<int:conteo_id>/eliminar", methods=["POST"])
@login_required
@perm_required("can_edit_stock")
def conteo_eliminar(conteo_id):
    conteo = ConteoInventario.query.get_or_404(conteo_id)
    db.session.delete(conteo)
    db.session.commit()
    flash("Conteo eliminado. (Los ajustes ya aplicados no se revierten.)", "info")
    return redirect(url_for("conteos.conteos_list"))
