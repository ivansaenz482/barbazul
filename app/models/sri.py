from datetime import datetime
from app.extensions import db


class SriConfig(db.Model):
    """Configuracion del emisor para facturacion electronica (SRI Ecuador)."""
    __tablename__ = "sri_config"

    id = db.Column(db.Integer, primary_key=True)
    ruc = db.Column(db.String(13))
    razon_social = db.Column(db.String(200))
    nombre_comercial = db.Column(db.String(200))
    direccion_matriz = db.Column(db.String(200))
    establecimiento = db.Column(db.String(3), default="001")
    punto_emision = db.Column(db.String(3), default="001")
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    obligado_contabilidad = db.Column(db.Boolean, default=False)
    regimen = db.Column(db.String(20))            # GENERAL, RIMPE_POPULAR, RIMPE_EMPRENDEDOR
    contribuyente_especial = db.Column(db.String(5))
    iva_porcentaje = db.Column(db.Integer, default=15)   # IVA vigente (Ecuador: 15)
    ambiente = db.Column(db.Enum("1", "2"), default="1") # 1=Pruebas, 2=Produccion
    tipo_emision = db.Column(db.Enum("1"), default="1")  # 1=Normal
    cert_path = db.Column(db.String(300))
    cert_password = db.Column(db.String(255))
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    @classmethod
    def actual(cls):
        return cls.query.first()

    def ambiente_label(self):
        return {"1": "Pruebas", "2": "Producción"}.get(self.ambiente, "Pruebas")

    def completo(self):
        """True si esta listo para emitir (faltan datos o certificado si no)."""
        return bool(self.ruc and self.razon_social and self.cert_path)


class Retencion(db.Model):
    """
    Comprobante de Retención (codDoc 07).
      - tipo "emitida": el negocio RETIENE a un proveedor (compras).
      - tipo "recibida": un cliente RETIENE al negocio (ventas).
    """
    __tablename__ = "retenciones"

    retencion_id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.Enum("emitida", "recibida"), default="emitida", nullable=False)
    numero = db.Column(db.String(30))
    fecha = db.Column(db.Date, nullable=False)
    periodo_fiscal = db.Column(db.String(7))  # mm/yyyy
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.supplier_id"))
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.customer_id"))
    purchase_invoice_id = db.Column(db.Integer, db.ForeignKey("purchase_invoices.invoice_id"))
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.sale_id"))

    base_imponible = db.Column(db.Numeric(12, 2), default=0)
    porcentaje_iva = db.Column(db.Numeric(5, 2), default=0)
    valor_iva_retenido = db.Column(db.Numeric(12, 2), default=0)
    porcentaje_renta = db.Column(db.Numeric(5, 2), default=0)
    valor_renta_retenido = db.Column(db.Numeric(12, 2), default=0)
    total_retenido = db.Column(db.Numeric(12, 2), default=0)
    codigo_renta = db.Column(db.String(10))  # ej. 312, 332, 725...

    observaciones = db.Column(db.String(255))
    ambiente = db.Column(db.Enum("1", "2"), default="1")
    clave_acceso = db.Column(db.String(80))
    estado = db.Column(db.Enum("borrador", "autorizada", "anulada"), default="borrador")
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.now)

    supplier = db.relationship("Supplier")
    customer = db.relationship("Customer")
    purchase_invoice = db.relationship("PurchaseInvoice")
    sale = db.relationship("Sale")

    def sujeto_nombre(self):
        if self.tipo == "emitida":
            return self.supplier.name if self.supplier else "—"
        return self.customer.full_name if self.customer else "—"

    def sujeto_identificacion(self):
        if self.tipo == "emitida":
            return self.supplier.ruc if self.supplier else ""
        return self.customer.cedula if self.customer else ""

    def tipo_label(self):
        return "Emitida (a proveedor)" if self.tipo == "emitida" else "Recibida (de cliente)"

