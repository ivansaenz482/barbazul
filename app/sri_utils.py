"""
Utilidades para facturacion electronica del SRI (Ecuador).

Incluye:
  - Calculo de la clave de acceso (49 digitos, modulo 11).
  - Generacion del XML de la FACTURA (ficha tecnica v1.1.0).
  - Punto de entrada para FIRMAR (XAdES-BES) y ENVIAR al SRI, que se activan
    cuando exista el certificado digital (.p12/.pfx).

Firma: usa 'signxml' si esta instalado. Si no, devuelve un mensaje claro.
Envio: usa 'requests' contra los WebServices del SRI (pruebas/produccion).
"""
from datetime import datetime
from xml.sax.saxutils import escape

IVA_DEFAULT = 15


def modulo11(clave48):
    """Digito verificador (modulo 11) para la clave de acceso del SRI."""
    pesos = [2, 3, 4, 5, 6, 7]
    suma = 0
    for i, c in enumerate(reversed(str(clave48))):
        suma += int(c) * pesos[i % 6]
    resto = suma % 11
    dv = 11 - resto
    if dv == 11:
        return 0
    if dv == 10:
        return 1
    return dv


def generar_clave_acceso(fecha_emision, ruc, ambiente, estab, pto_emi, secuencial,
                         tipo_comprobante="01", tipo_emision="1", codigo_numerico=None):
    """Devuelve la clave de acceso de 49 digitos."""
    fecha = fecha_emision.strftime("%d%m%Y")
    serie = f"{str(estab).zfill(3)}{str(pto_emi).zfill(3)}"
    sec = str(secuencial).zfill(9)
    codigo = codigo_numerico or datetime.now().strftime("%H%M%S%f")[:8].ljust(8, "0")
    clave48 = f"{fecha}{tipo_comprobante}{ruc}{ambiente}{serie}{sec}{codigo}{tipo_emision}"
    return clave48 + str(modulo11(clave48))


def tipo_identificacion(cliente):
    """(codigo, numero) de identificacion del comprador."""
    if not cliente:
        return "07", "9999999999999"
    if cliente.full_name in ("Consumidor Final", "Venta de Mostrador") or not cliente.cedula:
        return "07", "9999999999999"
    c = cliente.cedula.strip()
    if len(c) == 13:
        return "04", c   # RUC
    if len(c) == 10:
        return "05", c   # Cedula
    return "06", c       # Pasaporte


def _e(valor):
    return escape(str(valor if valor is not None else ""))


def generar_xml_factura(sale, config, secuencial):
    """
    Genera el XML de la factura (sin firmar) segun la ficha tecnica del SRI.
    Se asume que los precios del sistema INCLUYEN IVA; el total sin impuestos
    se calcula dividiendo para (1 + iva).
    """
    iva = int(config.iva_porcentaje or IVA_DEFAULT)
    factor = 1 + (iva / 100.0)

    importe_total = float(sale.total_amount or 0)
    total_sin_imp = round(importe_total / factor, 2)
    valor_iva = round(importe_total - total_sin_imp, 2)

    clave = generar_clave_acceso(
        sale.sale_date.date() if sale.sale_date else datetime.now().date(),
        config.ruc, config.ambiente, config.establecimiento, config.punto_emision,
        secuencial, tipo_comprobante="01", tipo_emision=config.tipo_emision or "1",
    )

    tipo_id, num_id = tipo_identificacion(sale.customer)
    obligado = "SI" if config.obligado_contabilidad else "NO"
    fecha = (sale.sale_date or datetime.now()).strftime("%d/%m/%Y")

    # Detalles
    lineas = []
    for d in sale.details:
        p = d.product
        base_linea = round((float(d.unit_price) * d.quantity) / factor, 2)
        pu_sin_iva = round(float(d.unit_price) / factor, 4)
        lineas.append(
            "    <detalle>\n"
            f"      <codigoPrincipal>{_e(p.sku or p.product_id) if p else d.product_id}</codigoPrincipal>\n"
            f"      <descripcion>{_e(p.name if p else 'Producto')}</descripcion>\n"
            f"      <cantidad>{d.quantity}</cantidad>\n"
            f"      <precioUnitario>{pu_sin_iva:.4f}</precioUnitario>\n"
            "      <descuento>0.00</descuento>\n"
            f"      <precioTotalSinImpuesto>{base_linea:.2f}</precioTotalSinImpuesto>\n"
            "      <impuestos>\n"
            "        <impuesto>\n"
            "          <codigo>2</codigo>\n"
            "          <codigoPorcentaje>4</codigoPorcentaje>\n"
            f"          <tarifa>{iva}</tarifa>\n"
            f"          <baseImponible>{base_linea:.2f}</baseImponible>\n"
            f"          <valor>{round(base_linea * iva / 100.0, 2):.2f}</valor>\n"
            "        </impuesto>\n"
            "      </impuestos>\n"
            "    </detalle>"
        )

    forma_pago = "01" if sale.payment_type != "credito" else "19"

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<factura id="comprobante" version="1.1.0">\n'
        "  <infoTributaria>\n"
        f"    <ambiente>{_e(config.ambiente)}</ambiente>\n"
        f"    <tipoEmision>{_e(config.tipo_emision or '1')}</tipoEmision>\n"
        f"    <razonSocial>{_e(config.razon_social)}</razonSocial>\n"
        f"    <nombreComercial>{_e(config.nombre_comercial or config.razon_social)}</nombreComercial>\n"
        f"    <ruc>{_e(config.ruc)}</ruc>\n"
        f"    <claveAcceso>{clave}</claveAcceso>\n"
        "    <codDoc>01</codDoc>\n"
        f"    <estab>{_e(str(config.establecimiento).zfill(3))}</estab>\n"
        f"    <ptoEmi>{_e(str(config.punto_emision).zfill(3))}</ptoEmi>\n"
        f"    <secuencial>{str(secuencial).zfill(9)}</secuencial>\n"
        f"    <dirMatriz>{_e(config.direccion_matriz)}</dirMatriz>\n"
        "  </infoTributaria>\n"
        "  <infoFactura>\n"
        f"    <fechaEmision>{fecha}</fechaEmision>\n"
        f"    <dirEstablecimiento>{_e(config.direccion_matriz)}</dirEstablecimiento>\n"
        f"    <obligadoContabilidad>{obligado}</obligadoContabilidad>\n"
        f"    <tipoIdentificacionComprador>{tipo_id}</tipoIdentificacionComprador>\n"
        f"    <razonSocialComprador>{_e(sale.customer.full_name if sale.customer else 'CONSUMIDOR FINAL')}</razonSocialComprador>\n"
        f"    <identificacionComprador>{num_id}</identificacionComprador>\n"
        f"    <totalSinImpuestos>{total_sin_imp:.2f}</totalSinImpuestos>\n"
        "    <totalDescuento>0.00</totalDescuento>\n"
        "    <totalConImpuestos>\n"
        "      <totalImpuesto>\n"
        "        <codigo>2</codigo>\n"
        "        <codigoPorcentaje>4</codigoPorcentaje>\n"
        f"        <baseImponible>{total_sin_imp:.2f}</baseImponible>\n"
        f"        <valor>{valor_iva:.2f}</valor>\n"
        "      </totalImpuesto>\n"
        "    </totalConImpuestos>\n"
        "    <propina>0.00</propina>\n"
        f"    <importeTotal>{importe_total:.2f}</importeTotal>\n"
        "    <moneda>DOLAR</moneda>\n"
        "    <pagos>\n"
        "      <pago>\n"
        f"        <formaPago>{forma_pago}</formaPago>\n"
        f"        <total>{importe_total:.2f}</total>\n"
        "      </pago>\n"
        "    </pagos>\n"
        "  </infoFactura>\n"
        "  <detalles>\n"
        + "\n".join(lineas) + "\n"
        "  </detalles>\n"
        "  <infoAdicional>\n"
        f"    <campoAdicional nombre=\"Email\">{_e(sale.customer.email) if sale.customer and sale.customer.email else ''}</campoAdicional>\n"
        f"    <campoAdicional nombre=\"Telefono\">{_e(sale.customer.phone) if sale.customer and sale.customer.phone else ''}</campoAdicional>\n"
        "  </infoAdicional>\n"
        "</factura>\n"
    )
    return clave, xml


def firmar_xml(xml, config):
    """
    Firma el XML con el certificado (.p12). Requiere 'signxml' instalado.
    Devuelve (xml_firmado, error).
    """
    try:
        from signxml import XMLSigner, methods
        from cryptography.hazmat.primitives.serialization import pkcs12
    except Exception:
        return None, ("Para firmar se necesitan las librerías 'signxml' y 'cryptography' y "
                      "el certificado .p12. Ejecuta: pip install signxml")

    import os
    if not config.cert_path or not os.path.isfile(config.cert_path):
        return None, "No hay certificado cargado en la configuración del SRI."

    try:
        with open(config.cert_path, "rb") as f:
            p12 = f.read()
        password = (config.cert_password or "").encode()
        key, cert, _ = pkcs12.load_key_and_certificates(p12, password)
        if key is None or cert is None:
            return None, "No se pudo leer la clave/certificado del .p12 (¿contraseña incorrecta?)."
        signer = XMLSigner(method=methods.enveloped, signature_algorithm="rsa-sha1",
                           digest_algorithm="sha1", c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315")
        firmado = signer.sign(xml.encode("utf-8"), key=key, cert=cert)
        return firmado.decode("utf-8"), None
    except Exception as e:
        return None, f"No se pudo firmar el XML: {e}"


# =====================================================================
# ENVIO Y AUTORIZACION (WebServices del SRI)
# =====================================================================

SRI_URLS = {
    "1": {  # Pruebas
        "recepcion": "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline",
        "autorizacion": "https://celcer.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline",
    },
    "2": {  # Produccion
        "recepcion": "https://cel.sri.gob.ec/comprobantes-electronicos-ws/RecepcionComprobantesOffline",
        "autorizacion": "https://cel.sri.gob.ec/comprobantes-electronicos-ws/AutorizacionComprobantesOffline",
    },
}

SOAP_RECEPCION = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:ec="http://ec.gob.sri.ws.recepcion">'
    "<soapenv:Header/><soapenv:Body>"
    "<ec:validarComprobante><xml>{xml}</xml></ec:validarComprobante>"
    "</soapenv:Body></soapenv:Envelope>"
)

SOAP_AUTORIZACION = (
    '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
    'xmlns:ec="http://ec.gob.sri.ws.autorizacion">'
    "<soapenv:Header/><soapenv:Body>"
    "<ec:autorizacionComprobante><claveAccesoComprobante>{clave}</claveAccesoComprobante>"
    "</ec:autorizacionComprobante>"
    "</soapenv:Body></soapenv:Envelope>"
)


def _tag(elem):
    return elem.tag.split("}")[-1]


def _buscar(root, nombre):
    for e in root.iter():
        if _tag(e) == nombre:
            return e
    return None


def enviar_al_sri(xml_firmado, config):
    """
    Envia el comprobante firmado al WebService de Recepcion.
    Devuelve (estado, mensajes) donde estado es 'RECIBIDA', 'DEVUELTA' o 'ERROR'.
    """
    try:
        import base64
        import requests
    except Exception:
        return "ERROR", ["Falta la librería 'requests'. Ejecuta: pip install requests"]

    import xml.etree.ElementTree as ET
    url = SRI_URLS.get(config.ambiente or "1", SRI_URLS["1"])["recepcion"]
    xml_b64 = base64.b64encode(xml_firmado.encode("utf-8")).decode("ascii")
    body = SOAP_RECEPCION.format(xml=xml_b64)
    try:
        resp = requests.post(url, data=body.encode("utf-8"),
                             headers={"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": ""},
                             timeout=30, verify=True)
    except Exception as e:
        return "ERROR", [f"No se pudo conectar con el SRI: {e}"]

    try:
        root = ET.fromstring(resp.content)
    except Exception:
        return "ERROR", [f"Respuesta no válida del SRI (HTTP {resp.status_code})."]

    estado = _buscar(root, "estado")
    mensajes = []
    for m in root.iter():
        if _tag(m) == "mensaje":
            mensajes.append(m.text or "")
        if _tag(m) == "informacionAdicional":
            mensajes.append(m.text or "")
    estado_txt = (estado.text or "").strip() if estado is not None else "ERROR"
    return estado_txt, mensajes


def consultar_autorizacion(clave, config):
    """
    Consulta la autorizacion de un comprobante por su clave de acceso.
    Devuelve (estado, numero_autorizacion, fecha_autorizacion, mensajes).
    """
    try:
        import requests
    except Exception:
        return "ERROR", None, None, ["Falta la librería 'requests'."]

    import xml.etree.ElementTree as ET
    url = SRI_URLS.get(config.ambiente or "1", SRI_URLS["1"])["autorizacion"]
    body = SOAP_AUTORIZACION.format(clave=clave)
    try:
        resp = requests.post(url, data=body.encode("utf-8"),
                             headers={"Content-Type": "text/xml; charset=UTF-8", "SOAPAction": ""},
                             timeout=30, verify=True)
    except Exception as e:
        return "ERROR", None, None, [f"No se pudo conectar con el SRI: {e}"]

    try:
        root = ET.fromstring(resp.content)
    except Exception:
        return "ERROR", None, None, [f"Respuesta no válida (HTTP {resp.status_code})."]

    estado = _buscar(root, "estado")
    numero = _buscar(root, "numeroAutorizacion")
    fecha = _buscar(root, "fechaAutorizacion")
    mensajes = [m.text or "" for m in root.iter() if _tag(m) == "mensaje"]
    return ((estado.text or "").strip() if estado is not None else "ERROR",
            numero.text if numero is not None else None,
            fecha.text if fecha is not None else None,
            mensajes)


# =====================================================================
# COMPROBANTE DE RETENCION (codDoc 07)
# =====================================================================

def _tipo_id_num(valor):
    if not valor:
        return "07", "9999999999999"
    c = str(valor).strip()
    if len(c) == 13:
        return "04", c
    if len(c) == 10:
        return "05", c
    return "06", c


def _codigo_retencion_iva(porcentaje):
    mapa = {10: "1", 20: "2", 30: "3", 50: "4", 60: "5", 70: "6", 75: "7", 80: "8", 90: "9", 100: "10"}
    try:
        return mapa.get(int(float(porcentaje)), "10")
    except (TypeError, ValueError):
        return "10"


def generar_xml_retencion(ret, config, secuencial):
    """Genera el XML del comprobante de retención (sin firmar)."""
    if ret.tipo == "emitida":
        sujeto = ret.supplier
        sujeto_nombre = sujeto.name if sujeto else "PROVEEDOR"
        sujeto_id = sujeto.ruc if sujeto else ""
    else:
        sujeto = ret.customer
        sujeto_nombre = sujeto.full_name if sujeto else "CLIENTE"
        sujeto_id = sujeto.cedula if sujeto else ""
    tipo_id, num_id = _tipo_id_num(sujeto_id)

    clave = generar_clave_acceso(
        ret.fecha, config.ruc, config.ambiente, config.establecimiento, config.punto_emision,
        secuencial, tipo_comprobante="07", tipo_emision=config.tipo_emision or "1",
    )

    periodo = ret.periodo_fiscal or ret.fecha.strftime("%m/%Y")
    obligado = "SI" if config.obligado_contabilidad else "NO"
    base = float(ret.base_imponible or 0)

    impuestos = []
    if float(ret.valor_iva_retenido or 0) > 0:
        impuestos.append(
            "    <impuesto>\n"
            "      <codigo>2</codigo>\n"
            f"      <codigoRetencion>{_codigo_retencion_iva(ret.porcentaje_iva)}</codigoRetencion>\n"
            f"      <baseImponible>{base:.2f}</baseImponible>\n"
            f"      <porcentajeRetener>{float(ret.porcentaje_iva or 0):.2f}</porcentajeRetener>\n"
            f"      <valorRetenido>{float(ret.valor_iva_retenido or 0):.2f}</valorRetenido>\n"
            "    </impuesto>"
        )
    if float(ret.valor_renta_retenido or 0) > 0:
        impuestos.append(
            "    <impuesto>\n"
            "      <codigo>1</codigo>\n"
            f"      <codigoRetencion>{_e(ret.codigo_renta or '')}</codigoRetencion>\n"
            f"      <baseImponible>{base:.2f}</baseImponible>\n"
            f"      <porcentajeRetener>{float(ret.porcentaje_renta or 0):.2f}</porcentajeRetener>\n"
            f"      <valorRetenido>{float(ret.valor_renta_retenido or 0):.2f}</valorRetenido>\n"
            "    </impuesto>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<comprobanteRetencion id="comprobante" version="2.0.0">\n'
        "  <infoTributaria>\n"
        f"    <ambiente>{_e(config.ambiente)}</ambiente>\n"
        f"    <tipoEmision>{_e(config.tipo_emision or '1')}</tipoEmision>\n"
        f"    <razonSocial>{_e(config.razon_social)}</razonSocial>\n"
        f"    <nombreComercial>{_e(config.nombre_comercial or config.razon_social)}</nombreComercial>\n"
        f"    <ruc>{_e(config.ruc)}</ruc>\n"
        f"    <claveAcceso>{clave}</claveAcceso>\n"
        "    <codDoc>07</codDoc>\n"
        f"    <estab>{_e(str(config.establecimiento).zfill(3))}</estab>\n"
        f"    <ptoEmi>{_e(str(config.punto_emision).zfill(3))}</ptoEmi>\n"
        f"    <secuencial>{str(secuencial).zfill(9)}</secuencial>\n"
        f"    <dirMatriz>{_e(config.direccion_matriz)}</dirMatriz>\n"
        "  </infoTributaria>\n"
        "  <infoCompRetencion>\n"
        f"    <fechaEmision>{ret.fecha.strftime('%d/%m/%Y')}</fechaEmision>\n"
        f"    <dirEstablecimiento>{_e(config.direccion_matriz)}</dirEstablecimiento>\n"
        f"    <obligadoContabilidad>{obligado}</obligadoContabilidad>\n"
        f"    <tipoIdentificacionSujetoRetenido>{tipo_id}</tipoIdentificacionSujetoRetenido>\n"
        f"    <razonSocialSujetoRetenido>{_e(sujeto_nombre)}</razonSocialSujetoRetenido>\n"
        f"    <identificacionSujetoRetenido>{num_id}</identificacionSujetoRetenido>\n"
        f"    <periodoFiscal>{periodo}</periodoFiscal>\n"
        "  </infoCompRetencion>\n"
        "  <impuestos>\n"
        + "\n".join(impuestos) + "\n"
        "  </impuestos>\n"
        "</comprobanteRetencion>\n"
    )
    return clave, xml


# =====================================================================
# ATS (Anexo Transaccional Simplificado)
# =====================================================================

def _fecha_ats(fecha):
    return fecha.strftime("%d/%m/%Y") if fecha else ""


def generar_xml_ats(anio, mes, config, ventas, compras, ret_emitidas, ret_recibidas):
    """
    Genera el XML del ATS (Anexo Transaccional Simplificado) de un mes.
    Estructura base (<iva>) con ventas, compras y retenciones. Revisar con el
    contador antes de subirlo al SRI.
    """
    def tipo_id_cliente(customer):
        if not customer or customer.full_name in ("Consumidor Final", "Venta de Mostrador") or not customer.cedula:
            return "07", "9999999999999"
        c = customer.cedula.strip()
        if len(c) == 13:
            return "04", c
        if len(c) == 10:
            return "05", c
        return "06", c

    total_ventas = sum(float(v.total_amount or 0) for v in ventas)

    det_ventas = []
    for v in ventas:
        tipo_id, num_id = tipo_id_cliente(v.customer)
        base = round(float(v.total_amount or 0) / (1 + (int(config.iva_porcentaje or IVA_DEFAULT) / 100.0)), 2)
        iva = round(float(v.total_amount or 0) - base, 2)
        det_ventas.append(
            "    <detalleVentas>\n"
            f"      <tpIdCliente>{tipo_id}</tpIdCliente>\n"
            f"      <idCliente>{num_id}</idCliente>\n"
            "      <parteRel>NO</parteRel>\n"
            f"      <tipoComprobante>{'01' if v.document_type == 'factura' else '00'}</tipoComprobante>\n"
            "      <tipoEmision>E</tipoEmision>\n"
            f"      <numeroAutorizacion>{_e(v.sri_clave_acceso or '')}</numeroAutorizacion>\n"
            f"      <fechaAutorizacion>{_fecha_ats(v.sri_autorizado_at)}</fechaAutorizacion>\n"
            f"      <establecimiento>{_e(config.establecimiento)}</establecimiento>\n"
            f"      <puntoEmision>{_e(config.punto_emision)}</puntoEmision>\n"
            f"      <secuencial>{str(v.sale_id).zfill(9)}</secuencial>\n"
            f"      <fechaEmision>{_fecha_ats(v.sale_date)}</fechaEmision>\n"
            f"      <denominacionCliente>{_e(v.customer.full_name if v.customer else '')}</denominacionCliente>\n"
            "      <baseNoGraIva>0.00</baseNoGraIva>\n"
            f"      <baseImponible>{base:.2f}</baseImponible>\n"
            "      <baseImpGrav>0.00</baseImpGrav>\n"
            f"      <montoIva>{iva:.2f}</montoIva>\n"
            "      <montoIce>0.00</montoIce>\n"
            "      <valorRetIva>0.00</valorRetIva>\n"
            "      <valorRetRenta>0.00</valorRetRenta>\n"
            "    </detalleVentas>"
        )

    det_compras = []
    for p in compras:
        base = round(float(p.total_amount or 0) / (1 + (int(config.iva_porcentaje or IVA_DEFAULT) / 100.0)), 2)
        iva = round(float(p.total_amount or 0) - base, 2)
        det_compras.append(
            "    <detalleCompras>\n"
            "      <codSustento>01</codSustento>\n"
            f"      <tpIdProv>{'04' if p.supplier and p.supplier.ruc and len(p.supplier.ruc) == 13 else '05'}</tpIdProv>\n"
            f"      <idProv>{_e(p.supplier.ruc if p.supplier else '')}</idProv>\n"
            f"      <tipoComprobante>01</tipoComprobante>\n"
            f"      <fechaRegistro>{_fecha_ats(p.invoice_date)}</fechaRegistro>\n"
            f"      <establecimiento>{_e(config.establecimiento)}</establecimiento>\n"
            f"      <puntoEmision>{_e(config.punto_emision)}</puntoEmision>\n"
            f"      <secuencial>{str(p.invoice_id).zfill(9)}</secuencial>\n"
            f"      <fechaEmision>{_fecha_ats(p.invoice_date)}</fechaEmision>\n"
            "      <tipoEmision>F</tipoEmision>\n"
            "      <baseNoGraIva>0.00</baseNoGraIva>\n"
            f"      <baseImponible>{base:.2f}</baseImponible>\n"
            "      <baseImpGrav>0.00</baseImpGrav>\n"
            f"      <montoIva>{iva:.2f}</montoIva>\n"
            "      <montoIce>0.00</montoIce>\n"
            "    </detalleCompras>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<iva>\n"
        "  <TipoIDInformante>R</TipoIDInformante>\n"
        f"  <IdInformante>{_e(config.ruc)}</IdInformante>\n"
        f"  <razonSocial>{_e(config.razon_social)}</razonSocial>\n"
        f"  <Anio>{anio}</Anio>\n"
        f"  <Mes>{str(mes).zfill(2)}</Mes>\n"
        f"  <numEstabRuc>{_e(str(config.establecimiento).zfill(3))}</numEstabRuc>\n"
        f"  <totalVentas>{total_ventas:.2f}</totalVentas>\n"
        "  <codigoOperativo>IVA</codigoOperativo>\n"
        "  <compras>\n" + "\n".join(det_compras) + "\n  </compras>\n"
        "  <ventas>\n" + "\n".join(det_ventas) + "\n  </ventas>\n"
        "</iva>\n"
    )
    return xml


def dia_vencimiento(ruc):
    """
    Dia del mes en que vence la declaracion, segun el 9no digito del RUC
    (calendario del SRI). El IVA/ATS de un mes se declara el mes siguiente.
    """
    try:
        d = int(str(ruc).strip()[8])
    except (ValueError, IndexError, TypeError):
        return 18
    if d in (1, 2):
        return 10
    if d in (3, 4):
        return 12
    if d in (5, 6):
        return 14
    if d in (7, 8):
        return 16
    return 18  # 9 o 0


def generar_xml_nota_credito(nc, config, secuencial):
    """Genera el XML de la Nota de Crédito (codDoc 04)."""
    sale = nc.sale
    iva = int(config.iva_porcentaje or IVA_DEFAULT)
    factor = 1 + (iva / 100.0)
    total = float(nc.total or 0)
    total_sin_imp = round(total / factor, 2)
    valor_iva = round(total - total_sin_imp, 2)

    clave = generar_clave_acceso(
        nc.fecha, config.ruc, config.ambiente, config.establecimiento, config.punto_emision,
        secuencial, tipo_comprobante="04", tipo_emision=config.tipo_emision or "1",
    )
    tipo_id, num_id = tipo_identificacion(nc.customer)
    num_doc_mod = f"{str(config.establecimiento).zfill(3)}-{str(config.punto_emision).zfill(3)}-{str(sale.sale_id).zfill(9)}"
    obligado = "SI" if config.obligado_contabilidad else "NO"
    fecha = nc.fecha.strftime("%d/%m/%Y")
    fecha_doc = sale.sale_date.strftime("%d/%m/%Y") if sale and sale.sale_date else fecha

    lineas = []
    for d in nc.details:
        p = d.product
        base = round((float(d.unit_price) * d.quantity) / factor, 2)
        pu = round(float(d.unit_price) / factor, 4)
        lineas.append(
            "    <detalle>\n"
            f"      <codigoInterno>{_e(p.sku or p.product_id) if p else d.product_id}</codigoInterno>\n"
            f"      <descripcion>{_e(p.name if p else 'Producto')}</descripcion>\n"
            f"      <cantidad>{d.quantity}</cantidad>\n"
            f"      <precioUnitario>{pu:.4f}</precioUnitario>\n"
            "      <descuento>0.00</descuento>\n"
            f"      <precioTotalSinImpuesto>{base:.2f}</precioTotalSinImpuesto>\n"
            "    </detalle>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<notaCredito id="comprobante" version="1.1.0">\n'
        "  <infoTributaria>\n"
        f"    <ambiente>{_e(config.ambiente)}</ambiente>\n"
        f"    <tipoEmision>{_e(config.tipo_emision or '1')}</tipoEmision>\n"
        f"    <razonSocial>{_e(config.razon_social)}</razonSocial>\n"
        f"    <nombreComercial>{_e(config.nombre_comercial or config.razon_social)}</nombreComercial>\n"
        f"    <ruc>{_e(config.ruc)}</ruc>\n"
        f"    <claveAcceso>{clave}</claveAcceso>\n"
        "    <codDoc>04</codDoc>\n"
        f"    <estab>{_e(str(config.establecimiento).zfill(3))}</estab>\n"
        f"    <ptoEmi>{_e(str(config.punto_emision).zfill(3))}</ptoEmi>\n"
        f"    <secuencial>{str(secuencial).zfill(9)}</secuencial>\n"
        f"    <dirMatriz>{_e(config.direccion_matriz)}</dirMatriz>\n"
        "  </infoTributaria>\n"
        "  <infoNotaCredito>\n"
        f"    <fechaEmision>{fecha}</fechaEmision>\n"
        f"    <dirEstablecimiento>{_e(config.direccion_matriz)}</dirEstablecimiento>\n"
        f"    <tipoIdentificacionComprador>{tipo_id}</tipoIdentificacionComprador>\n"
        f"    <razonSocialComprador>{_e(nc.customer.full_name if nc.customer else 'CONSUMIDOR FINAL')}</razonSocialComprador>\n"
        f"    <identificacionComprador>{num_id}</identificacionComprador>\n"
        f"    <obligadoContabilidad>{obligado}</obligadoContabilidad>\n"
        "    <codDocModificado>01</codDocModificado>\n"
        f"    <numDocModificado>{num_doc_mod}</numDocModificado>\n"
        f"    <fechaEmisionDocSustento>{fecha_doc}</fechaEmisionDocSustento>\n"
        f"    <totalSinImpuestos>{total_sin_imp:.2f}</totalSinImpuestos>\n"
        "    <valorModificacion>0.00</valorModificacion>\n"
        "    <moneda>DOLAR</moneda>\n"
        "    <totalConImpuestos>\n"
        "      <totalImpuesto>\n"
        "        <codigo>2</codigo>\n"
        "        <codigoPorcentaje>4</codigoPorcentaje>\n"
        f"        <baseImponible>{total_sin_imp:.2f}</baseImponible>\n"
        f"        <valor>{valor_iva:.2f}</valor>\n"
        "      </totalImpuesto>\n"
        "    </totalConImpuestos>\n"
        f"    <motivo>{_e(nc.motivo_label())}</motivo>\n"
        "  </infoNotaCredito>\n"
        "  <detalles>\n" + "\n".join(lineas) + "\n  </detalles>\n"
        "</notaCredito>\n"
    )
    return clave, xml
