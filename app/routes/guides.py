from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import DeliveryGuide, DeliveryGuideDetail, Sale, Customer, Branch, Product
from app.utils import role_required

guides_bp = Blueprint("guides", __name__, url_prefix="/guias")


@guides_bp.route("/")
@login_required
@role_required("administrador")
def guides_list():
    guides = DeliveryGuide.query.order_by(DeliveryGuide.created_at.desc()).all()
    return render_template("guides_list.html", guides=guides)


@guides_bp.route("/nueva", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def guide_new():
    sale_id = request.args.get("sale_id", "").strip()
    sale = Sale.query.get(int(sale_id)) if sale_id else None

    customers = Customer.query.filter_by(active=True).order_by(Customer.full_name).all()
    branches = Branch.query.filter_by(active=True).order_by(Branch.name).all()
    products = Product.query.filter_by(active=True).order_by(Product.name).all()

    if request.method == "POST":
        motivo = request.form.get("motivo", "venta")
        customer_id = request.form.get("customer_id") or None
        origin_branch_id = request.form.get("origin_branch_id") or None
        destination_branch_id = request.form.get("destination_branch_id") or None
        fecha_str = request.form.get("fecha_emision") or datetime.now().strftime("%Y-%m-%d")

        try:
            fecha_emision = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            fecha_emision = datetime.now().date()

        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")

        line_items = []
        for pid, qty in zip(product_ids, quantities):
            if not pid or not qty:
                continue
            product = Product.query.get(int(pid))
            quantity = int(qty)
            if product and quantity > 0:
                line_items.append((product, quantity))

        if not line_items:
            flash("Debes agregar al menos un producto a la guía.", "danger")
            return render_template("guide_form.html", customers=customers, branches=branches,
                                    products=products, sale=sale)

        guide = DeliveryGuide(
            guide_number=request.form.get("guide_number", "").strip() or None,
            sale_id=sale.sale_id if sale else None,
            customer_id=int(customer_id) if customer_id else None,
            origin_branch_id=int(origin_branch_id) if origin_branch_id else None,
            destination_branch_id=int(destination_branch_id) if destination_branch_id else None,
            destination_address=request.form.get("destination_address", "").strip() or None,
            motivo=motivo,
            transportista_nombre=request.form.get("transportista_nombre", "").strip() or None,
            transportista_identificacion=request.form.get("transportista_identificacion", "").strip() or None,
            vehiculo_placa=request.form.get("vehiculo_placa", "").strip() or None,
            fecha_emision=fecha_emision,
            observaciones=request.form.get("observaciones", "").strip() or None,
            created_by=current_user.user_id,
        )
        db.session.add(guide)
        db.session.flush()

        for product, quantity in line_items:
            db.session.add(DeliveryGuideDetail(
                guide_id=guide.guide_id,
                product_id=product.product_id,
                quantity=quantity,
            ))

        db.session.commit()
        flash(f"Guía de Remisión #{guide.guide_id} generada correctamente.", "success")
        return redirect(url_for("guides.guide_detail", guide_id=guide.guide_id))

    return render_template("guide_form.html", customers=customers, branches=branches,
                            products=products, sale=sale)


@guides_bp.route("/<int:guide_id>")
@login_required
@role_required("administrador")
def guide_detail(guide_id):
    guide = DeliveryGuide.query.get_or_404(guide_id)
    return render_template("guide_detail.html", guide=guide)


@guides_bp.route("/<int:guide_id>/entregar", methods=["POST"])
@login_required
@role_required("administrador")
def guide_marcar_entregada(guide_id):
    from datetime import datetime
    guide = DeliveryGuide.query.get_or_404(guide_id)

    if guide.entregada:
        flash("Esta guía ya estaba marcada como entregada.", "info")
        return redirect(request.referrer or url_for("guides.guides_list"))

    guide.entregada = True
    guide.entregada_at = datetime.now()
    guide.entregada_by = current_user.user_id
    db.session.commit()
    flash(f"Guía #{guide.guide_id} marcada como entregada.", "success")
    return redirect(request.referrer or url_for("guides.guides_list"))


@guides_bp.route("/<int:guide_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def guide_delete(guide_id):
    guide = DeliveryGuide.query.get_or_404(guide_id)
    numero = guide.guide_id
    db.session.delete(guide)  # borra tambien sus detalles (cascade)
    db.session.commit()
    flash(f"Guía de Remisión #{numero} eliminada correctamente.", "info")
    return redirect(url_for("guides.guides_list"))
