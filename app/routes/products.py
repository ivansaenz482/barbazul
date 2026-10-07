import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, abort, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import Product, Category, Supplier, InventoryMovement
from app.utils import role_required, perm_required, generar_ean13, resolver_ruta_upload

products_bp = Blueprint("products", __name__, url_prefix="/productos")


# =====================================================================
# CATEGORÍAS
# =====================================================================

@products_bp.route("/categorias")
@login_required
@perm_required("can_view_inventario")
def categories_list():
    categories = Category.query.order_by(Category.name).all()
    return render_template("categories_list.html", categories=categories)


@products_bp.route("/categorias/nueva", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def category_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("El nombre de la categoría es obligatorio.", "danger")
            return render_template("category_form.html", category=None)

        db.session.add(Category(name=name, description=description or None))
        db.session.commit()
        flash("Categoría creada correctamente.", "success")
        return redirect(url_for("products.categories_list"))

    return render_template("category_form.html", category=None)


@products_bp.route("/categorias/<int:category_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def category_edit(category_id):
    category = Category.query.get_or_404(category_id)

    if request.method == "POST":
        category.name = request.form.get("name", "").strip()
        category.description = request.form.get("description", "").strip() or None
        db.session.commit()
        flash("Categoría actualizada.", "success")
        return redirect(url_for("products.categories_list"))

    return render_template("category_form.html", category=category)


@products_bp.route("/categorias/<int:category_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def category_delete(category_id):
    category = Category.query.get_or_404(category_id)
    if category.products:
        flash("No puedes eliminar una categoría que tiene productos asociados.", "danger")
    else:
        db.session.delete(category)
        db.session.commit()
        flash("Categoría eliminada.", "info")
    return redirect(url_for("products.categories_list"))


# =====================================================================
# PROVEEDORES
# =====================================================================

@products_bp.route("/proveedores")
@login_required
@perm_required("can_view_inventario")
def suppliers_list():
    suppliers = Supplier.query.order_by(Supplier.name).all()
    return render_template("suppliers_list.html", suppliers=suppliers)


@products_bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def supplier_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre del proveedor es obligatorio.", "danger")
            return render_template("supplier_form.html", supplier=None)

        supplier = Supplier(
            name=name,
            ruc=request.form.get("ruc", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            address=request.form.get("address", "").strip() or None,
            credit_term_days=request.form.get("credit_term_days", "0") or "0",
        )
        db.session.add(supplier)
        db.session.commit()
        flash("Proveedor creado correctamente.", "success")
        return redirect(url_for("products.suppliers_list"))

    return render_template("supplier_form.html", supplier=None)


@products_bp.route("/proveedores/<int:supplier_id>/editar", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def supplier_edit(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)

    if request.method == "POST":
        supplier.name = request.form.get("name", "").strip()
        supplier.ruc = request.form.get("ruc", "").strip() or None
        supplier.phone = request.form.get("phone", "").strip() or None
        supplier.email = request.form.get("email", "").strip() or None
        supplier.address = request.form.get("address", "").strip() or None
        supplier.credit_term_days = request.form.get("credit_term_days", "0") or "0"
        db.session.commit()
        flash("Proveedor actualizado.", "success")
        return redirect(url_for("products.suppliers_list"))

    return render_template("supplier_form.html", supplier=supplier)


@products_bp.route("/proveedores/<int:supplier_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def supplier_delete(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if supplier.products:
        flash("No puedes eliminar un proveedor que tiene productos asociados.", "danger")
    else:
        db.session.delete(supplier)
        db.session.commit()
        flash("Proveedor eliminado.", "info")
    return redirect(url_for("products.suppliers_list"))


# =====================================================================
# PRODUCTOS
# =====================================================================

def _barcode_unico(base=None):
    """Genera un EAN-13 unico que no este en uso. Base = product_id o el siguiente id."""
    usados = {p.barcode for p in Product.query.all() if p.barcode}
    base = base or ((Product.query.order_by(Product.product_id.desc()).first().product_id if Product.query.first() else 0) + 1)
    codigo = generar_ean13(base)
    intento = base
    while codigo in usados:
        intento += 1
        codigo = generar_ean13(intento)
    return codigo


def _allowed_product_image(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_PRODUCT_IMAGE_EXTENSIONS"]


def _guardar_imagen_producto(product, file):
    """Guarda (o reemplaza) la imagen de un producto y actualiza product.image_path."""
    if not file or not file.filename:
        return False
    if not _allowed_product_image(file.filename):
        flash("Formato de imagen no permitido. Usa PNG, JPG, JPEG, WEBP o GIF.", "danger")
        return False

    os.makedirs(current_app.config["PRODUCT_IMAGE_FOLDER"], exist_ok=True)
    filename = secure_filename(file.filename)
    unique_name = f"prod{product.product_id}_{uuid.uuid4().hex}_{filename}"
    save_path = os.path.join(current_app.config["PRODUCT_IMAGE_FOLDER"], unique_name)
    file.save(save_path)

    # Borra la imagen anterior para no acumular archivos
    if product.image_path and os.path.exists(product.image_path):
        try:
            os.remove(product.image_path)
        except OSError:
            pass

    product.image_path = save_path
    return True


@products_bp.route("/<int:product_id>/imagen")
@login_required
def product_image(product_id):
    product = Product.query.get_or_404(product_id)
    ruta = resolver_ruta_upload(product.image_path, current_app.config["PRODUCT_IMAGE_FOLDER"])
    if not ruta:
        abort(404)
    return send_file(ruta)


@products_bp.route("/<int:product_id>/imagen/eliminar", methods=["POST"])
@login_required
@perm_required("can_edit_stock")
def product_image_delete(product_id):
    product = Product.query.get_or_404(product_id)
    if product.image_path and os.path.exists(product.image_path):
        try:
            os.remove(product.image_path)
        except OSError:
            pass
    product.image_path = None
    db.session.commit()
    flash("Imagen del producto eliminada.", "info")
    return redirect(url_for("products.product_edit", product_id=product_id))


@products_bp.route("/api/generar-barcode")
@login_required
@perm_required("can_edit_stock")
def api_generar_barcode():
    product_id = request.args.get("product_id", "").strip()
    base = int(product_id) if product_id.isdigit() else None
    return jsonify({"barcode": _barcode_unico(base)})


@products_bp.route("/")
@login_required
@perm_required("can_view_inventario")
def products_list():
    search = request.args.get("q", "").strip()
    query = Product.query
    if search:
        # Busqueda por nombre, SKU o codigo de barras (permite ingresar por codigo)
        query = query.filter(
            (Product.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.barcode.ilike(f"%{search}%"))
        )
    products = query.order_by(Product.name).all()
    return render_template("products_list.html", products=products, search=search)


@products_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@perm_required("can_edit_stock")
def product_new():
    categories = Category.query.order_by(Category.name).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        sku = request.form.get("sku", "").strip() or None

        if not name:
            flash("El nombre del producto es obligatorio.", "danger")
            return render_template("product_form.html", product=None, categories=categories, suppliers=suppliers)

        if sku and Product.query.filter_by(sku=sku).first():
            flash(f"Ya existe un producto con el SKU '{sku}'.", "danger")
            return render_template("product_form.html", product=None, categories=categories, suppliers=suppliers)

        product = Product(
            name=name,
            sku=sku,
            barcode=request.form.get("barcode", "").strip() or None,
            category_id=request.form.get("category_id") or None,
            supplier_id=request.form.get("supplier_id") or None,
            unit_measure=request.form.get("unit_measure", "unidad").strip() or "unidad",
            presentacion=request.form.get("presentacion", "").strip() or "unidad",
            cost_price=float(request.form.get("cost_price") or 0),
            sale_price=float(request.form.get("sale_price") or 0),
            price_credito=float(request.form.get("price_credito") or 0),
            price_mayorista=float(request.form.get("price_mayorista") or 0),
            min_stock=int(request.form.get("min_stock") or 0),
            max_stock=int(request.form.get("max_stock") or 0),
            current_stock=int(request.form.get("current_stock") or 0),
            stock_matriz=int(request.form.get("stock_matriz") or 0),
            active=True,
        )
        db.session.add(product)
        db.session.flush()
        if not product.barcode:
            product.barcode = _barcode_unico(product.product_id)
        _guardar_imagen_producto(product, request.files.get("imagen"))
        db.session.commit()
        flash(f"Producto '{name}' creado correctamente.", "success")
        return redirect(url_for("products.products_list"))

    return render_template("product_form.html", product=None, categories=categories, suppliers=suppliers)


@products_bp.route("/<int:product_id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("can_edit_stock")
def product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    categories = Category.query.order_by(Category.name).all()
    suppliers = Supplier.query.order_by(Supplier.name).all()

    if request.method == "POST":
        sku = request.form.get("sku", "").strip() or None
        if sku and sku != product.sku and Product.query.filter_by(sku=sku).first():
            flash(f"Ya existe otro producto con el SKU '{sku}'.", "danger")
            return render_template("product_form.html", product=product, categories=categories, suppliers=suppliers)

        product.name = request.form.get("name", "").strip()
        product.sku = sku
        product.barcode = request.form.get("barcode", "").strip() or None
        if not product.barcode:
            product.barcode = _barcode_unico(product.product_id)
        product.category_id = request.form.get("category_id") or None
        product.supplier_id = request.form.get("supplier_id") or None
        product.unit_measure = request.form.get("unit_measure", "unidad").strip() or "unidad"
        product.presentacion = request.form.get("presentacion", "").strip() or "unidad"
        product.cost_price = float(request.form.get("cost_price") or 0)
        product.sale_price = float(request.form.get("sale_price") or 0)
        product.price_credito = float(request.form.get("price_credito") or 0)
        product.price_mayorista = float(request.form.get("price_mayorista") or 0)
        product.min_stock = int(request.form.get("min_stock") or 0)
        product.max_stock = int(request.form.get("max_stock") or 0)
        product.current_stock = int(request.form.get("current_stock") or 0)
        product.stock_matriz = int(request.form.get("stock_matriz") or 0)
        _guardar_imagen_producto(product, request.files.get("imagen"))
        db.session.commit()
        flash("Producto actualizado.", "success")
        return redirect(url_for("products.products_list"))

    return render_template("product_form.html", product=product, categories=categories, suppliers=suppliers)


@products_bp.route("/<int:product_id>/eliminar", methods=["POST"])
@login_required
@perm_required("can_edit_stock")
def product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    product.active = False  # borrado logico: conserva historial de ventas/compras
    db.session.commit()
    flash(f"Producto '{product.name}' desactivado.", "info")
    return redirect(url_for("products.products_list"))


# =====================================================================
# AJUSTE DE STOCK (corregir errores de inventario)
# =====================================================================

def _historial_ajustes(limit=30):
    return (InventoryMovement.query
            .filter(InventoryMovement.reference_type == "ajuste_manual")
            .order_by(InventoryMovement.movement_id.desc())
            .limit(limit).all())


@products_bp.route("/ajuste", methods=["GET", "POST"])
@login_required
@perm_required("can_edit_stock")
def stock_adjust():
    products = Product.query.filter_by(active=True).order_by(Product.name).all()

    if request.method == "POST":
        product = Product.query.get(request.form.get("product_id")) if request.form.get("product_id") else None
        if not product:
            flash("Selecciona un producto.", "danger")
            return render_template("products_ajuste.html", products=products, historial=_historial_ajustes())

        bodega = request.form.get("bodega", "local")
        if bodega not in ("local", "matriz"):
            bodega = "local"

        try:
            nuevo = int(request.form.get("nuevo_stock") or 0)
        except (ValueError, TypeError):
            nuevo = 0
        nuevo = max(0, nuevo)

        actual = (product.current_stock if bodega == "local" else product.stock_matriz) or 0
        delta = nuevo - actual
        if delta == 0:
            flash("El stock no cambió (ya estaba en ese valor).", "info")
            return redirect(url_for("products.stock_adjust"))

        motivo = request.form.get("motivo", "").strip() or "Ajuste manual"

        if bodega == "local":
            product.current_stock = nuevo
        else:
            product.stock_matriz = nuevo

        db.session.add(InventoryMovement(
            product_id=product.product_id,
            movement_type="ajuste",
            quantity=abs(delta),
            reference_type="ajuste_manual",
            reference_id=None,
            user_id=current_user.user_id,
            notes=f"Ajuste {bodega}: {actual} -> {nuevo} ({motivo})",
        ))
        db.session.commit()
        signo = "+" if delta > 0 else ""
        flash(f"Stock de '{product.name}' ajustado ({signo}{delta}) a {nuevo} en bodega {bodega}.", "success")
        return redirect(url_for("products.stock_adjust"))

    return render_template("products_ajuste.html", products=products, historial=_historial_ajustes())
