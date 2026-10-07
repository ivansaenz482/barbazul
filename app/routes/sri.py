import os
import uuid
from datetime import datetime, date

from flask import (Blueprint, render_template, request, redirect, url_for, flash,
                   Response, current_app)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (Sale, SriConfig, PurchaseInvoice, Retencion, Supplier, Customer,
                        NotaCredito, NotaCreditoDetail, InventoryMovement)
from app.utils import role_required
from app.routes.sales import _sumar_stock_bodega, _restar_stock_bodega
from app.sri_utils import (generar_xml_factura, firmar_xml, generar_clave_acceso,
                           enviar_al_sri, consultar_autorizacion,
                           generar_xml_retencion, generar_xml_ats, dia_vencimiento,
                           generar_xml_nota_credito)

sri_bp = Blueprint("sri", __name__, url_prefix="/sri")


# =====================================================================
# CONFIGURACION DEL SRI
# =====================================================================

@sri_bp.route("/config", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def sri_config():
    cfg = SriConfig.actual()

    if request.method == "POST":
        if not cfg:
            cfg = SriConfig()
            db.session.add(cfg)

        cfg.ruc = request.form.get("ruc", "").strip() or None
        cfg.razon_social = request.form.get("razon_social", "").strip() or None
        cfg.nombre_comercial = request.form.get("nombre_comercial", "").strip() or None
        cfg.direccion_matriz = request.form.get("direccion_matriz", "").strip() or None
        cfg.establecimiento = (request.form.get("establecimiento", "001").strip() or "001")[:3]
        cfg.punto_emision = (request.form.get("punto_emision", "001").strip() or "001")[:3]
        cfg.telefono = request.form.get("telefono", "").strip() or None
        cfg.email = request.form.get("email", "").strip() or None
        cfg.regimen = request.form.get("regimen", "").strip() or None
        cfg.contribuyente_especial = request.form.get("contribuyente_especial", "").strip() or None
        cfg.obligado_contabilidad = request.form.get("obligado_contabilidad") == "on"
        try:
            cfg.iva_porcentaje = int(request.form.get("iva_porcentaje") or 15)
        except (TypeError, ValueError):
            cfg.iva_porcentaje = 15
        cfg.ambiente = request.form.get("ambiente", "1") if request.form.get("ambiente") in ("1", "2") else "1"

        # Certificado .p12 / .pfx
        archivo = request.files.get("certificado")
        if archivo and archivo.filename:
            if archivo.filename.lower().endswith((".p12", ".pfx")):
                os.makedirs(current_app.config["SRI_CERT_FOLDER"], exist_ok=True)
                nombre = f"cert_{uuid.uuid4().hex}_{secure_filename(archivo.filename)}"
                ruta = os.path.join(current_app.config["SRI_CERT_FOLDER"], nombre)
                archivo.save(ruta)
                if cfg.cert_path and os.path.exists(cfg.cert_path):
                    try:
                        os.remove(cfg.cert_path)
                    except OSError:
                        pass
                cfg.cert_path = ruta
            else:
                flash("El certificado debe ser un archivo .p12 o .pfx.", "danger")

        pwd = request.form.get("cert_password", "").strip()
        if pwd:
            cfg.cert_password = pwd

        db.session.commit()
        flash("Configuración del SRI guardada.", "success")
        return redirect(url_for("sri.sri_config"))

    return render_template("sri_config.html", cfg=cfg)


# =====================================================================
# FACTURAS
# =====================================================================

@sri_bp.route("/facturas")
@login_required
@role_required("administrador")
def facturas_sri():
    estado = request.args.get("estado", "").strip()

    query = Sale.query.filter(Sale.document_type == "factura", Sale.liquidada == True)  # noqa: E712
    if estado in ("pendiente", "autorizada", "rechazada"):
        query = query.filter(Sale.sri_status == estado)

    facturas = query.order_by(Sale.sale_date.desc()).all()
    totales = {
        "todas": len(facturas),
        "pendiente": sum(1 for f in facturas if f.sri_status == "pendiente"),
        "autorizada": sum(1 for f in facturas if f.sri_status == "autorizada"),
        "rechazada": sum(1 for f in facturas if f.sri_status == "rechazada"),
    }
    cfg = SriConfig.actual()
    return render_template(
        "sri_facturas.html",
        facturas=facturas,
        selected_estado=estado,
        totales=totales,
        cfg=cfg,
    )


@sri_bp.route("/facturas/<int:sale_id>/xml")
@login_required
@role_required("administrador")
def factura_xml(sale_id):
    """Genera (y firma si hay certificado) el XML del comprobante y lo descarga."""
    sale = Sale.query.get_or_404(sale_id)
    if sale.document_type != "factura":
        flash("Solo las facturas generan XML del SRI.", "danger")
        return redirect(url_for("sri.facturas_sri"))

    cfg = SriConfig.actual()
    if not cfg or not cfg.ruc or not cfg.razon_social:
        flash("Primero configura los datos del SRI (RUC y razón social) en SRI → Configuración.", "danger")
        return redirect(url_for("sri.sri_config"))

    clave, xml = generar_xml_factura(sale, cfg, secuencial=sale.sale_id)
    sale.sri_clave_acceso = clave

    firmado_ok = False
    if cfg.cert_path:
        firmado, error = firmar_xml(xml, cfg)
        if firmado:
            xml = firmado
            firmado_ok = True
        else:
            flash(error, "warning")

    db.session.commit()

    if not firmado_ok:
        flash("El XML se generó SIN firmar (falta el certificado .p12 o las librerías de firma).", "info")

    nombre = f"factura_{sale.sale_id}.xml"
    return Response(xml, mimetype="application/xml",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


@sri_bp.route("/facturas/<int:sale_id>/autorizar", methods=["POST"])
@login_required
@role_required("administrador")
def factura_autorizar(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    if sale.document_type != "factura":
        flash("Solo las facturas pueden autorizarse para el SRI.", "danger")
        return redirect(url_for("sri.facturas_sri"))

    clave = request.form.get("clave_acceso", "").strip() or sale.sri_clave_acceso
    sale.sri_status = "autorizada"
    sale.sri_clave_acceso = clave
    sale.sri_autorizado_at = datetime.utcnow()
    sale.sri_autorizado_by = current_user.user_id
    db.session.commit()
    flash(f"Factura #{sale.sale_id} marcada como AUTORIZADA para el SRI.", "success")
    return redirect(url_for("sri.facturas_sri", estado=request.args.get("estado", "")))


@sri_bp.route("/facturas/<int:sale_id>/rechazar", methods=["POST"])
@login_required
@role_required("administrador")
def factura_rechazar(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    sale.sri_status = "rechazada"
    sale.sri_autorizado_at = datetime.utcnow()
    sale.sri_autorizado_by = current_user.user_id
    db.session.commit()
    flash(f"Factura #{sale.sale_id} marcada como RECHAZADA.", "warning")
    return redirect(url_for("sri.facturas_sri", estado=request.args.get("estado", "")))


@sri_bp.route("/facturas/<int:sale_id>/revertir", methods=["POST"])
@login_required
@role_required("administrador")
def factura_revertir(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    sale.sri_status = "pendiente"
    sale.sri_clave_acceso = None
    sale.sri_autorizado_at = None
    sale.sri_autorizado_by = None
    db.session.commit()
    flash(f"Factura #{sale.sale_id} vuelta a PENDIENTE de autorización.", "info")
    return redirect(url_for("sri.facturas_sri", estado=request.args.get("estado", "")))


@sri_bp.route("/facturas/<int:sale_id>/enviar", methods=["POST"])
@login_required
@role_required("administrador")
def factura_enviar(sale_id):
    """Firma (si hay certificado), envía al SRI y consulta la autorización."""
    sale = Sale.query.get_or_404(sale_id)
    if sale.document_type != "factura":
        flash("Solo las facturas se envían al SRI.", "danger")
        return redirect(url_for("sri.facturas_sri"))

    cfg = SriConfig.actual()
    if not cfg or not cfg.ruc or not cfg.razon_social:
        flash("Configura primero los datos del emisor en SRI → Configuración.", "danger")
        return redirect(url_for("sri.sri_config"))
    if not cfg.cert_path:
        flash("Para ENVIAR al SRI necesitas subir tu certificado digital (.p12). "
              "Mientras tanto, puedes generar el XML con el botón 'XML'.", "warning")
        return redirect(url_for("sri.sri_config"))

    clave, xml = generar_xml_factura(sale, cfg, secuencial=sale.sale_id)
    sale.sri_clave_acceso = clave

    firmado, error = firmar_xml(xml, cfg)
    if not firmado:
        db.session.commit()
        flash(error, "danger")
        return redirect(url_for("sri.facturas_sri"))

    estado, mensajes = enviar_al_sri(firmado, cfg)
    if estado == "RECIBIDA":
        estado_a, numero, fecha_a, mensajes_a = consultar_autorizacion(clave, cfg)
        if estado_a == "AUTORIZADO":
            sale.sri_status = "autorizada"
            sale.sri_autorizado_at = datetime.utcnow()
            sale.sri_autorizado_by = current_user.user_id
            flash(f"✅ Factura #{sale.sale_id} AUTORIZADA por el SRI. N° {numero or ''}", "success")
        else:
            sale.sri_status = "pendiente"
            detalle = "; ".join([m for m in mensajes_a if m][:3])
            flash(f"Recibida por el SRI pero aún no autorizada. {detalle}", "warning")
    else:
        sale.sri_status = "rechazada"
        detalle = "; ".join([m for m in mensajes if m][:3])
        flash(f"El SRI DEVOLVIÓ el comprobante: {detalle}", "danger")

    db.session.commit()
    return redirect(url_for("sri.facturas_sri"))


@sri_bp.route("/facturas/<int:sale_id>/ride")
@login_required
@role_required("administrador")
def factura_ride(sale_id):
    """RIDE imprimible de la factura (con clave de acceso y código de barras)."""
    sale = Sale.query.get_or_404(sale_id)
    cfg = SriConfig.actual()
    iva = int(cfg.iva_porcentaje) if cfg and cfg.iva_porcentaje else 15
    base = round(float(sale.total_amount or 0) / (1 + iva / 100.0), 2)
    return render_template("sri_ride.html", sale=sale, cfg=cfg, iva=iva,
                           base=base, valor_iva=round(float(sale.total_amount or 0) - base, 2))


# =====================================================================
# DECLARACIONES DE IMPUESTOS (IVA mensual - Formulario 104)
# =====================================================================

@sri_bp.route("/declaraciones")
@login_required
@role_required("administrador")
def declaraciones():
    try:
        anio = int(request.args.get("anio", date.today().year))
    except (TypeError, ValueError):
        anio = date.today().year

    cfg = SriConfig.actual()
    iva_pct = int(cfg.iva_porcentaje) if cfg and cfg.iva_porcentaje else 15
    factor = 1 + iva_pct / 100.0

    meses = []
    for m in range(1, 13):
        inicio = datetime(anio, m, 1)
        fin = datetime(anio + 1, 1, 1) if m == 12 else datetime(anio, m + 1, 1)

        ventas = Sale.query.filter(Sale.liquidada == True,  # noqa: E712
                                   Sale.sale_date >= inicio, Sale.sale_date < fin).all()
        total_ventas = sum(float(s.total_amount or 0) for s in ventas)
        ncs = NotaCredito.query.filter(NotaCredito.fecha >= inicio.date(),
                                       NotaCredito.fecha < fin.date()).all()
        nc_total = sum(float(n.total or 0) for n in ncs)
        nc_iva = sum(float(n.valor_iva or 0) for n in ncs)
        ventas_netas = total_ventas - nc_total
        base_ventas = round(ventas_netas / factor, 2)
        iva_ventas = round(ventas_netas - base_ventas, 2)
        facturas = sum(1 for s in ventas if s.document_type == "factura")
        otras = len(ventas) - facturas

        compras = PurchaseInvoice.query.filter(PurchaseInvoice.invoice_date >= inicio.date(),
                                               PurchaseInvoice.invoice_date < fin.date()).all()
        total_compras = sum(float(p.total_amount or 0) for p in compras)
        base_compras = round(total_compras / factor, 2)
        iva_compras = round(total_compras - base_compras, 2)

        ret_rec = Retencion.query.filter(Retencion.tipo == "recibida",
                                         Retencion.fecha >= inicio.date(), Retencion.fecha < fin.date()).all()
        ret_emit = Retencion.query.filter(Retencion.tipo == "emitida",
                                          Retencion.fecha >= inicio.date(), Retencion.fecha < fin.date()).all()
        ret_iva_rec = round(sum(float(r.valor_iva_retenido or 0) for r in ret_rec), 2)
        ret_iva_emit = round(sum(float(r.valor_iva_retenido or 0) for r in ret_emit), 2)

        meses.append({
            "mes": m,
            "nombre": ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
                       "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][m],
            "num_ventas": len(ventas),
            "facturas": facturas,
            "otras": otras,
            "total_ventas": total_ventas,
            "nc_total": nc_total,
            "base_ventas": base_ventas,
            "iva_ventas": iva_ventas,
            "total_compras": total_compras,
            "base_compras": base_compras,
            "iva_compras": iva_compras,
            "ret_iva_rec": ret_iva_rec,
            "ret_iva_emit": ret_iva_emit,
            "iva_pagar": round(iva_ventas - iva_compras - ret_iva_rec, 2),
        })

    totales = {
        "ventas": sum(x["total_ventas"] for x in meses),
        "iva_ventas": sum(x["iva_ventas"] for x in meses),
        "compras": sum(x["total_compras"] for x in meses),
        "iva_compras": sum(x["iva_compras"] for x in meses),
        "ret_iva_rec": sum(x["ret_iva_rec"] for x in meses),
        "ret_iva_emit": sum(x["ret_iva_emit"] for x in meses),
        "iva_pagar": sum(x["iva_pagar"] for x in meses),
    }

    return render_template("sri_declaraciones.html", meses=meses, anio=anio,
                           iva_pct=iva_pct, cfg=cfg, totales=totales,
                           generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"))


@sri_bp.route("/sin-factura")
@login_required
@role_required("administrador")
def sin_factura():
    """Comprobantes que NO son factura (notas de venta/pedido) para revisar declaraciones."""
    try:
        anio = int(request.args.get("anio", date.today().year))
        mes = int(request.args.get("mes", date.today().month))
    except (TypeError, ValueError):
        anio, mes = date.today().year, date.today().month
    mes = max(1, min(12, mes))

    inicio = datetime(anio, mes, 1)
    fin = datetime(anio + 1, 1, 1) if mes == 12 else datetime(anio, mes + 1, 1)
    ventas = (Sale.query
              .filter(Sale.liquidada == True,  # noqa: E712
                      Sale.document_type != "factura",
                      Sale.sale_date >= inicio, Sale.sale_date < fin)
              .order_by(Sale.sale_date).all())
    total = sum(float(s.total_amount or 0) for s in ventas)
    return render_template("sri_sin_factura.html", ventas=ventas, total=total,
                           anio=anio, mes=mes)


# =====================================================================
# RETENCIONES (comprobante de retencion, codDoc 07)
# =====================================================================

@sri_bp.route("/retenciones")
@login_required
@role_required("administrador")
def retenciones():
    tipo = request.args.get("tipo", "").strip()
    query = Retencion.query
    if tipo in ("emitida", "recibida"):
        query = query.filter(Retencion.tipo == tipo)
    rets = query.order_by(Retencion.fecha.desc(), Retencion.retencion_id.desc()).limit(300).all()
    total = sum(float(r.total_retenido or 0) for r in rets)
    return render_template("retenciones_list.html", retenciones=rets, tipo=tipo, total=total,
                           suppliers=Supplier.query.order_by(Supplier.name).all(),
                           customers=Customer.query.filter_by(active=True).order_by(Customer.full_name).all(),
                           today=date.today().isoformat())


@sri_bp.route("/retenciones/nueva", methods=["POST"])
@login_required
@role_required("administrador")
def retencion_nueva():
    tipo = request.form.get("tipo", "emitida")
    if tipo not in ("emitida", "recibida"):
        tipo = "emitida"
    try:
        fecha = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        fecha = date.today()

    def _f(campo):
        try:
            return round(float(request.form.get(campo) or 0), 2)
        except (TypeError, ValueError):
            return 0.0

    base = _f("base_imponible")
    p_iva = _f("porcentaje_iva")
    p_renta = _f("porcentaje_renta")
    v_iva = round(base * p_iva / 100.0, 2)
    v_renta = round(base * p_renta / 100.0, 2)

    supplier_id = request.form.get("supplier_id") or None
    customer_id = request.form.get("customer_id") or None

    ret = Retencion(
        tipo=tipo, fecha=fecha,
        periodo_fiscal=request.form.get("periodo_fiscal", "").strip() or fecha.strftime("%m/%Y"),
        supplier_id=int(supplier_id) if (tipo == "emitida" and supplier_id) else None,
        customer_id=int(customer_id) if (tipo == "recibida" and customer_id) else None,
        base_imponible=base, porcentaje_iva=p_iva, valor_iva_retenido=v_iva,
        porcentaje_renta=p_renta, valor_renta_retenido=v_renta,
        total_retenido=round(v_iva + v_renta, 2),
        codigo_renta=request.form.get("codigo_renta", "").strip() or None,
        observaciones=request.form.get("observaciones", "").strip() or None,
        ambiente=(SriConfig.actual().ambiente if SriConfig.actual() else "1"),
        created_by=current_user.user_id,
    )
    if not ret.numero:
        ret.numero = f"{fecha.strftime('%Y%m%d')}-{tipo[:3].upper()}"
    db.session.add(ret)
    db.session.commit()
    flash(f"Retención #{ret.retencion_id} registrada (total retenido ${ret.total_retenido}).", "success")
    return redirect(url_for("sri.retenciones"))


@sri_bp.route("/retenciones/<int:ret_id>/ride")
@login_required
@role_required("administrador")
def retencion_ride(ret_id):
    ret = Retencion.query.get_or_404(ret_id)
    cfg = SriConfig.actual()
    return render_template("retencion_ride.html", ret=ret, cfg=cfg)


@sri_bp.route("/retenciones/<int:ret_id>/xml")
@login_required
@role_required("administrador")
def retencion_xml(ret_id):
    ret = Retencion.query.get_or_404(ret_id)
    cfg = SriConfig.actual()
    if not cfg or not cfg.ruc or not cfg.razon_social:
        flash("Configura primero los datos del SRI.", "danger")
        return redirect(url_for("sri.sri_config"))
    clave, xml = generar_xml_retencion(ret, cfg, secuencial=ret.retencion_id)
    ret.clave_acceso = clave
    db.session.commit()
    return Response(xml, mimetype="application/xml",
                    headers={"Content-Disposition": f"attachment; filename=retencion_{ret.retencion_id}.xml"})


@sri_bp.route("/retenciones/<int:ret_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def retencion_eliminar(ret_id):
    ret = Retencion.query.get_or_404(ret_id)
    db.session.delete(ret)
    db.session.commit()
    flash("Retención eliminada.", "info")
    return redirect(url_for("sri.retenciones"))


@sri_bp.route("/retenciones/<int:ret_id>/enviar", methods=["POST"])
@login_required
@role_required("administrador")
def retencion_enviar(ret_id):
    """Firma y envía el comprobante de retención al SRI, y consulta la autorización."""
    ret = Retencion.query.get_or_404(ret_id)
    cfg = SriConfig.actual()
    if not cfg or not cfg.ruc or not cfg.razon_social:
        flash("Configura primero los datos del emisor en SRI → Configuración.", "danger")
        return redirect(url_for("sri.sri_config"))
    if not cfg.cert_path:
        flash("Para ENVIAR necesitas subir tu certificado digital (.p12). Mientras tanto, genera el XML.", "warning")
        return redirect(url_for("sri.sri_config"))

    clave, xml = generar_xml_retencion(ret, cfg, secuencial=ret.retencion_id)
    ret.clave_acceso = clave
    firmado, error = firmar_xml(xml, cfg)
    if not firmado:
        db.session.commit()
        flash(error, "danger")
        return redirect(url_for("sri.retenciones"))

    estado, mensajes = enviar_al_sri(firmado, cfg)
    if estado == "RECIBIDA":
        estado_a, numero, fecha_a, mensajes_a = consultar_autorizacion(clave, cfg)
        if estado_a == "AUTORIZADO":
            ret.estado = "autorizada"
            flash(f"✅ Retención #{ret.retencion_id} AUTORIZADA por el SRI.", "success")
        else:
            ret.estado = "borrador"
            flash(f"Recibida por el SRI pero aún no autorizada. {'; '.join([m for m in mensajes_a if m][:3])}", "warning")
    else:
        ret.estado = "borrador"
        flash(f"El SRI DEVOLVIÓ la retención: {'; '.join([m for m in mensajes if m][:3])}", "danger")

    db.session.commit()
    return redirect(url_for("sri.retenciones"))


# =====================================================================
# ATS (Anexo Transaccional Simplificado)
# =====================================================================

def _datos_ats(anio, mes):
    inicio = datetime(anio, mes, 1)
    fin = datetime(anio + 1, 1, 1) if mes == 12 else datetime(anio, mes + 1, 1)
    ventas = (Sale.query.filter(Sale.liquidada == True,  # noqa: E712
                                Sale.sale_date >= inicio, Sale.sale_date < fin).all())
    compras = (PurchaseInvoice.query.filter(PurchaseInvoice.invoice_date >= inicio.date(),
                                            PurchaseInvoice.invoice_date < fin.date()).all())
    ret_emit = (Retencion.query.filter(Retencion.tipo == "emitida",
                                       Retencion.fecha >= inicio.date(), Retencion.fecha < fin.date()).all())
    ret_rec = (Retencion.query.filter(Retencion.tipo == "recibida",
                                      Retencion.fecha >= inicio.date(), Retencion.fecha < fin.date()).all())
    return ventas, compras, ret_emit, ret_rec


@sri_bp.route("/ats")
@login_required
@role_required("administrador")
def ats():
    try:
        anio = int(request.args.get("anio", date.today().year))
        mes = int(request.args.get("mes", date.today().month))
    except (TypeError, ValueError):
        anio, mes = date.today().year, date.today().month
    mes = max(1, min(12, mes))
    ventas, compras, ret_emit, ret_rec = _datos_ats(anio, mes)
    return render_template("sri_ats.html", anio=anio, mes=mes,
                           num_ventas=len(ventas), total_ventas=sum(float(v.total_amount or 0) for v in ventas),
                           num_compras=len(compras), total_compras=sum(float(p.total_amount or 0) for p in compras),
                           num_ret_emit=len(ret_emit), num_ret_rec=len(ret_rec),
                           cfg=SriConfig.actual())


@sri_bp.route("/ats/xml")
@login_required
@role_required("administrador")
def ats_xml():
    try:
        anio = int(request.args.get("anio", date.today().year))
        mes = int(request.args.get("mes", date.today().month))
    except (TypeError, ValueError):
        anio, mes = date.today().year, date.today().month
    mes = max(1, min(12, mes))
    cfg = SriConfig.actual()
    if not cfg or not cfg.ruc or not cfg.razon_social:
        flash("Configura primero los datos del SRI.", "danger")
        return redirect(url_for("sri.sri_config"))
    ventas, compras, ret_emit, ret_rec = _datos_ats(anio, mes)
    xml = generar_xml_ats(anio, mes, cfg, ventas, compras, ret_emit, ret_rec)
    return Response(xml, mimetype="application/xml",
                    headers={"Content-Disposition": f"attachment; filename=ATS_{anio}_{str(mes).zfill(2)}.xml"})


# =====================================================================
# VENCIMIENTOS DE IMPUESTOS (recordatorios)
# =====================================================================

@sri_bp.route("/vencimientos")
@login_required
@role_required("administrador")
def vencimientos():
    try:
        anio = int(request.args.get("anio", date.today().year))
    except (TypeError, ValueError):
        anio = date.today().year

    cfg = SriConfig.actual()
    ruc = cfg.ruc if cfg else ""
    dia = dia_vencimiento(ruc)
    iva_pct = int(cfg.iva_porcentaje) if cfg and cfg.iva_porcentaje else 15
    factor = 1 + iva_pct / 100.0
    hoy = date.today()

    filas = []
    for m in range(1, 13):
        inicio = datetime(anio, m, 1)
        fin = datetime(anio + 1, 1, 1) if m == 12 else datetime(anio, m + 1, 1)

        ventas = Sale.query.filter(Sale.liquidada == True,  # noqa: E712
                                   Sale.sale_date >= inicio, Sale.sale_date < fin).all()
        total_ventas = sum(float(s.total_amount or 0) for s in ventas)
        iva_ventas = round(total_ventas - total_ventas / factor, 2)

        compras = PurchaseInvoice.query.filter(PurchaseInvoice.invoice_date >= inicio.date(),
                                               PurchaseInvoice.invoice_date < fin.date()).all()
        iva_compras = round(sum(float(p.total_amount or 0) for p in compras) * (1 - 1 / factor), 2)

        ret_rec = Retencion.query.filter(Retencion.tipo == "recibida",
                                         Retencion.fecha >= inicio.date(), Retencion.fecha < fin.date()).all()
        ret_iva_rec = round(sum(float(r.valor_iva_retenido or 0) for r in ret_rec), 2)

        iva_pagar = round(iva_ventas - iva_compras - ret_iva_rec, 2)

        vy, vm = (anio + 1, 1) if m == 12 else (anio, m + 1)
        venc = date(vy, vm, dia)
        dias = (venc - hoy).days
        if venc < hoy:
            estado = "vencido"
        elif dias <= 7:
            estado = "proximo"
        else:
            estado = "pendiente"

        filas.append({
            "mes": m,
            "nombre": ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
                       "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"][m],
            "vence": venc,
            "iva_pagar": iva_pagar,
            "estado": estado,
            "dias": dias,
            "vencido": venc < hoy,
        })

    return render_template("sri_vencimientos.html", filas=filas, anio=anio, dia=dia,
                           ruc=ruc, hoy=hoy, cfg=cfg,
                           generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"))


# =====================================================================
# NOTAS DE CREDITO / DEVOLUCIONES (codDoc 04)
# =====================================================================

@sri_bp.route("/notas-credito")
@login_required
@role_required("administrador")
def notas_credito_list():
    ncs = NotaCredito.query.order_by(NotaCredito.fecha.desc(), NotaCredito.nc_id.desc()).limit(300).all()
    total = sum(float(n.total or 0) for n in ncs)
    return render_template("notas_credito_list.html", notas=ncs, total=total)


@sri_bp.route("/notas-credito/nueva/<int:sale_id>", methods=["GET", "POST"])
@login_required
@role_required("administrador")
def nota_credito_nueva(sale_id):
    sale = Sale.query.get_or_404(sale_id)
    cfg = SriConfig.actual()

    if request.method == "POST":
        try:
            fecha = datetime.strptime(request.form.get("fecha", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            fecha = date.today()
        motivo = request.form.get("motivo", "devolucion")
        if motivo not in ("devolucion", "descuento", "error", "otro"):
            motivo = "devolucion"

        lineas = []
        for d in sale.details:
            try:
                q = int(request.form.get(f"qty_{d.detail_id}") or 0)
            except (TypeError, ValueError):
                q = 0
            if q > 0:
                lineas.append((d, min(q, d.quantity)))

        if not lineas:
            flash("Selecciona al menos una cantidad a devolver.", "danger")
            return render_template("nota_credito_form.html", sale=sale, cfg=cfg)

        bodega = sale.bodega or "local"
        nc = NotaCredito(
            numero=f"{fecha.strftime('%Y%m%d')}-NC",
            fecha=fecha, sale_id=sale.sale_id, customer_id=sale.customer_id,
            motivo=motivo, bodega=bodega,
            observaciones=request.form.get("observaciones", "").strip() or None,
            created_by=current_user.user_id,
        )
        db.session.add(nc)
        db.session.flush()

        total = 0.0
        for d, q in lineas:
            db.session.add(NotaCreditoDetail(
                nc_id=nc.nc_id, product_id=d.product_id, quantity=q,
                unit_price=d.unit_price, unit_cost=d.unit_cost,
            ))
            if d.product:
                _sumar_stock_bodega(d.product, bodega, q)
            db.session.add(InventoryMovement(
                product_id=d.product_id, movement_type="entrada", quantity=q,
                reference_type="nota_credito", reference_id=nc.nc_id,
                user_id=current_user.user_id,
                notes=f"Nota de crédito #{nc.nc_id} (venta #{sale.sale_id}) — {bodega}",
            ))
            total += float(d.unit_price) * q

        iva = int(cfg.iva_porcentaje) if cfg and cfg.iva_porcentaje else 15
        nc.total = round(total, 2)
        nc.subtotal = round(total / (1 + iva / 100.0), 2)
        nc.valor_iva = round(nc.total - nc.subtotal, 2)
        db.session.commit()
        flash(f"Nota de crédito #{nc.nc_id} emitida por ${nc.total:.2f}. Stock devuelto.", "success")
        return redirect(url_for("sri.nota_credito_ride", nc_id=nc.nc_id))

    return render_template("nota_credito_form.html", sale=sale, cfg=cfg)


@sri_bp.route("/notas-credito/<int:nc_id>")
@login_required
@role_required("administrador")
def nota_credito_ride(nc_id):
    nc = NotaCredito.query.get_or_404(nc_id)
    return render_template("nota_credito_ride.html", nc=nc, cfg=SriConfig.actual())


@sri_bp.route("/notas-credito/<int:nc_id>/xml")
@login_required
@role_required("administrador")
def nota_credito_xml(nc_id):
    nc = NotaCredito.query.get_or_404(nc_id)
    cfg = SriConfig.actual()
    if not cfg or not cfg.ruc or not cfg.razon_social:
        flash("Configura primero los datos del SRI.", "danger")
        return redirect(url_for("sri.sri_config"))
    clave, xml = generar_xml_nota_credito(nc, cfg, secuencial=nc.nc_id)
    nc.sri_clave_acceso = clave
    db.session.commit()
    return Response(xml, mimetype="application/xml",
                    headers={"Content-Disposition": f"attachment; filename=nota_credito_{nc.nc_id}.xml"})


@sri_bp.route("/notas-credito/<int:nc_id>/eliminar", methods=["POST"])
@login_required
@role_required("administrador")
def nota_credito_eliminar(nc_id):
    nc = NotaCredito.query.get_or_404(nc_id)
    bodega = nc.bodega or "local"
    for d in nc.details:
        if d.product:
            _restar_stock_bodega(d.product, bodega, d.quantity)
    for m in InventoryMovement.query.filter_by(reference_type="nota_credito", reference_id=nc.nc_id).all():
        db.session.delete(m)
    db.session.delete(nc)
    db.session.commit()
    flash("Nota de crédito eliminada. Stock revertido.", "info")
    return redirect(url_for("sri.notas_credito_list"))
