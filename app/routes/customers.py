from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required
from app.extensions import db
from app.models import Customer, Branch
from app.utils import role_required, perm_required
from app.geo_data import PROVINCIAS_ECUADOR, CIUDADES_PRINCIPALES

customers_bp = Blueprint("customers", __name__, url_prefix="/clientes")


# =====================================================================
# BODEGAS / LOCALES (sucursales)
# =====================================================================

def _usuarios_asignables():
    """Usuarios activos (no administradores) que pueden ser encargados de una bodega."""
    from app.models import User, Role
    return (User.query.join(Role)
            .filter(User.active.is_(True), Role.role_name != "administrador")
            .order_by(User.full_name).all())


def _clave_branch(branch_id):
    from app.stock import clave_sucursal
    return clave_sucursal(branch_id)


def _encargado_de(branch_id):
    from app.models import User
    return User.query.filter_by(bodega=_clave_branch(branch_id)).first()


def _asignar_encargado(branch, encargado_id):
    """Deja a un solo usuario como encargado de la bodega (los demas se desasignan)."""
    from app.models import User
    clave = _clave_branch(branch.branch_id)
    for u in User.query.filter_by(bodega=clave).all():
        u.bodega = None
    if encargado_id and str(encargado_id).isdigit():
        u = User.query.get(int(encargado_id))
        if u:
            u.bodega = clave


@customers_bp.route("/locales")
@login_required
@perm_required("can_view_clientes")
def branches_list():
    branches = Branch.query.order_by(Branch.name).all()
    encargados = {b.branch_id: _encargado_de(b.branch_id) for b in branches}
    return render_template("branches_list.html", branches=branches, encargados=encargados)


@customers_bp.route("/locales/nuevo", methods=["GET", "POST"])
@login_required
@perm_required("can_view_clientes")
def branch_new():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("El nombre de la bodega/local es obligatorio.", "danger")
            return render_template("branch_form.html", branch=None, usuarios=_usuarios_asignables(), encargado=None)

        branch = Branch(
            name=name,
            address=request.form.get("address", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            active=(request.form.get("active", "on") == "on"),
        )
        db.session.add(branch)
        db.session.flush()
        _asignar_encargado(branch, request.form.get("encargado_id"))
        db.session.commit()
        flash("Bodega/local creada correctamente.", "success")
        return redirect(url_for("customers.branches_list"))

    return render_template("branch_form.html", branch=None, usuarios=_usuarios_asignables(), encargado=None)


@customers_bp.route("/locales/<int:branch_id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("can_view_clientes")
def branch_edit(branch_id):
    branch = Branch.query.get_or_404(branch_id)

    if request.method == "POST":
        branch.name = request.form.get("name", "").strip()
        branch.address = request.form.get("address", "").strip() or None
        branch.phone = request.form.get("phone", "").strip() or None
        branch.active = (request.form.get("active", "on") == "on")
        _asignar_encargado(branch, request.form.get("encargado_id"))
        db.session.commit()
        flash("Bodega/local actualizada.", "success")
        return redirect(url_for("customers.branches_list"))

    return render_template("branch_form.html", branch=branch, usuarios=_usuarios_asignables(),
                           encargado=_encargado_de(branch.branch_id))


@customers_bp.route("/locales/<int:branch_id>/eliminar", methods=["POST"])
@login_required
@perm_required("can_view_clientes")
def branch_delete(branch_id):
    branch = Branch.query.get_or_404(branch_id)
    from app.models import BranchStock, User
    tiene_stock = BranchStock.query.filter(BranchStock.branch_id == branch_id, BranchStock.quantity > 0).count() > 0
    if branch.customers:
        flash("No puedes eliminar una bodega/local que tiene clientes asociados.", "danger")
    elif tiene_stock:
        flash("No puedes eliminar una bodega/local que todavía tiene stock. Transfiere el stock primero.", "danger")
    else:
        for u in User.query.filter_by(bodega=_clave_branch(branch_id)).all():
            u.bodega = None
        BranchStock.query.filter_by(branch_id=branch_id).delete()
        db.session.delete(branch)
        db.session.commit()
        flash("Bodega/local eliminada.", "info")
    return redirect(url_for("customers.branches_list"))


# =====================================================================
# CLIENTES
# =====================================================================
@customers_bp.route("/")
@login_required
@perm_required("can_view_clientes")
def customers_list():
    search = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    branch_id = request.args.get("branch_id", "").strip()

    query = Customer.query
    if search:
        query = query.filter(
            (Customer.full_name.ilike(f"%{search}%")) | (Customer.cedula.ilike(f"%{search}%"))
        )
    if tipo in ("efectivo", "credito"):
        query = query.filter(Customer.customer_type == tipo)
    if branch_id:
        query = query.filter(Customer.branch_id == int(branch_id))

    customers = query.order_by(Customer.full_name).all()
    branches = Branch.query.filter_by(active=True).order_by(Branch.name).all()
    return render_template("customers_list.html", customers=customers, search=search, tipo=tipo,
                            branches=branches, branch_id=branch_id)


@customers_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@perm_required("can_view_clientes")
def customer_new():
    branches = Branch.query.filter_by(active=True).order_by(Branch.name).all()

    if request.method == "POST":
        cedula = request.form.get("cedula", "").strip() or None
        full_name = request.form.get("full_name", "").strip()

        if not full_name:
            flash("El nombre del cliente es obligatorio.", "danger")
            return render_template("customer_form.html", customer=None, branches=branches,
                                    provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)

        if cedula and Customer.query.filter_by(cedula=cedula).first():
            flash(f"Ya existe un cliente con la cédula '{cedula}'.", "danger")
            return render_template("customer_form.html", customer=None, branches=branches,
                                    provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)

        customer_type = request.form.get("customer_type", "efectivo")
        credit_term_days = request.form.get("credit_term_days", "0") if customer_type == "credito" else "0"
        price_list = request.form.get("price_list", "contado")
        if price_list not in ("contado", "credito", "mayorista"):
            price_list = "contado"

        customer = Customer(
            cedula=cedula,
            full_name=full_name,
            business_name=request.form.get("business_name", "").strip() or None,
            phone=request.form.get("phone", "").strip() or None,
            email=request.form.get("email", "").strip() or None,
            address=request.form.get("address", "").strip() or None,
            province=request.form.get("province", "").strip() or None,
            city=request.form.get("city", "").strip() or None,
            customer_type=customer_type,
            price_list=price_list,
            credit_limit=float(request.form.get("credit_limit") or 0) if customer_type == "credito" else 0,
            credit_term_days=credit_term_days,
            branch_id=request.form.get("branch_id") or None,
            active=True,
        )
        db.session.add(customer)
        db.session.commit()
        flash(f"Cliente '{full_name}' registrado correctamente.", "success")
        return redirect(url_for("customers.customers_list"))

    return render_template("customer_form.html", customer=None, branches=branches,
                            provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)


@customers_bp.route("/<int:customer_id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("can_view_clientes")
def customer_edit(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    branches = Branch.query.filter_by(active=True).order_by(Branch.name).all()

    if request.method == "POST":
        cedula = request.form.get("cedula", "").strip() or None
        if cedula and cedula != customer.cedula and Customer.query.filter_by(cedula=cedula).first():
            flash(f"Ya existe otro cliente con la cédula '{cedula}'.", "danger")
            return render_template("customer_form.html", customer=customer, branches=branches,
                                    provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)

        customer_type = request.form.get("customer_type", "efectivo")

        customer.cedula = cedula
        customer.full_name = request.form.get("full_name", "").strip()
        customer.business_name = request.form.get("business_name", "").strip() or None
        customer.phone = request.form.get("phone", "").strip() or None
        customer.email = request.form.get("email", "").strip() or None
        customer.address = request.form.get("address", "").strip() or None
        customer.province = request.form.get("province", "").strip() or None
        customer.city = request.form.get("city", "").strip() or None
        customer.customer_type = customer_type
        price_list = request.form.get("price_list", "contado")
        if price_list not in ("contado", "credito", "mayorista"):
            price_list = "contado"
        customer.price_list = price_list
        customer.credit_limit = float(request.form.get("credit_limit") or 0) if customer_type == "credito" else 0
        customer.credit_term_days = request.form.get("credit_term_days", "0") if customer_type == "credito" else "0"
        customer.branch_id = request.form.get("branch_id") or None
        db.session.commit()
        flash("Cliente actualizado.", "success")
        return redirect(url_for("customers.customers_list"))

    return render_template("customer_form.html", customer=customer, branches=branches,
                            provincias=PROVINCIAS_ECUADOR, ciudades=CIUDADES_PRINCIPALES)


@customers_bp.route("/<int:customer_id>/eliminar", methods=["POST"])
@login_required
@perm_required("can_view_clientes")
def customer_delete(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.active = False  # borrado logico: conserva historial de ventas
    db.session.commit()
    flash(f"Cliente '{customer.full_name}' desactivado.", "info")
    return redirect(url_for("customers.customers_list"))


# =====================================================================
# VALIDACION / CONSULTA DE CEDULA Y RUC (Ecuador)
# =====================================================================

def validar_identificacion(valor):
    """Valida cedula (10) o RUC (13) de Ecuador con el algoritmo modulo 10/11.
    Devuelve (valido: bool, mensaje: str)."""
    s = "".join(ch for ch in str(valor or "") if ch.isdigit())
    if len(s) not in (10, 13):
        return False, "Debe tener 10 (cédula) o 13 (RUC) dígitos."
    if len(set(s)) == 1:
        return False, "Número no válido (dígitos repetidos)."

    provincia = int(s[:2])
    if provincia < 1 or (provincia > 24 and provincia != 30):
        return False, "Código de provincia no válido."

    if len(s) == 10:
        if s[2] == "9":  # persona juridica no es cedula
            return False, "Una cédula no puede empezar con 9 en el 3.er dígito."
        return _modulo10(s), "Cédula válida." if _modulo10(s) else "Cédula incorrecta (dígito verificador)."

    # RUC: 13 digitos
    if s[2] == "9":  # juridico
        ok = _modulo11(s[:9], s[9])
        return ok, "RUC (jurídico) válido." if ok else "RUC jurídico incorrecto."
    if s[2] == "6":  # publico
        ok = _modulo11(s[:8], s[8])
        return ok, "RUC (público) válido." if ok else "RUC público incorrecto."
    # natural: primeros 10 = cedula, luego 001
    ok = _modulo10(s[:10]) and s[10:] == "001"
    return ok, "RUC (natural) válido." if ok else "RUC natural incorrecto."


def _modulo10(ced):
    coef = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for i in range(9):
        v = int(ced[i]) * coef[i]
        if v > 9:
            v -= 9
        total += v
    dig = (10 - (total % 10)) % 10
    return dig == int(ced[9])


def _modulo11(base, verificador):
    coef = [4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(base[i]) * coef[i] for i in range(min(9, len(base))))
    residuo = total % 11
    dig = 11 - residuo
    if dig == 11:
        dig = 0
    if dig == 10:
        dig = 1
    return dig == int(verificador)


def _extraer_datos_api(data):
    """Saca (nombre, razon_social, direccion) de una respuesta JSON de varias formas posibles."""
    nombre = razon = direccion = None
    if not isinstance(data, dict):
        return nombre, razon, direccion

    def _buscar(d):
        nonlocal nombre, razon, direccion
        if not isinstance(d, dict):
            return
        # nombre (persona)
        if not nombre:
            n = (d.get("nombre") or d.get("nombres") or d.get("name")
                 or d.get("nombreCompleto") or d.get("nombre_completo"))
            if n:
                nombre = str(n).strip()
        # apellidos -> completar nombre
        if nombre and (d.get("apellidos") or d.get("apellido")):
            nombre = f"{nombre} {d.get('apellidos') or d.get('apellido')}".strip()
        # razon social (empresa)
        if not razon:
            r = (d.get("razonSocial") or d.get("razon_social") or d.get("RazonSocial")
                 or d.get("contribuyente") or d.get("empresa"))
            if r:
                razon = str(r).strip()
        if not direccion:
            dr = (d.get("direccion") or d.get("address") or d.get("Direccion")
                  or d.get("direccionCompleta"))
            if dr:
                direccion = str(dr).strip()

    _buscar(data)
    # respuestas anidadas comunes
    for key in ("data", "result", "resultado", "contribuyente", "datos"):
        _buscar(data.get(key))
    return (nombre or None), (razon or None), (direccion or None)


@customers_bp.route("/consultar-cedula")
@login_required
def consultar_cedula():
    """Valida cedula/RUC y, si hay una API configurada (CEDULA_API_URL), la consulta."""
    cedula = request.args.get("cedula", "").strip()
    valido, mensaje = validar_identificacion(cedula)
    resultado = {"cedula": cedula, "valido": valido, "mensaje": mensaje,
                 "nombre": None, "razon_social": None, "direccion": None, "api": False}

    api = current_app.config.get("CEDULA_API_URL", "").strip()
    if api and valido:
        try:
            import requests
            url = api.replace("{cedula}", cedula).replace("{ruc}", cedula)
            headers = {"Accept": "application/json"}
            token = current_app.config.get("CEDULA_API_TOKEN", "").strip()
            if token:
                headers[current_app.config.get("CEDULA_API_HEADER", "Authorization")] = token
            resp = requests.get(url, timeout=8, headers=headers)
            data = resp.json()
            nombre, razon, direccion = _extraer_datos_api(data)
            resultado["nombre"] = nombre
            resultado["razon_social"] = razon
            resultado["direccion"] = direccion
            resultado["api"] = True
            if not (nombre or razon):
                resultado["mensaje"] += " (La API respondió pero sin nombre.)"
        except Exception:
            resultado["mensaje"] += " (No se pudo consultar la API; solo se validó localmente.)"
    elif valido and not api:
        resultado["mensaje"] += " — Para traer el nombre automáticamente configura una API (CEDULA_API_URL)."

    return jsonify(resultado)
