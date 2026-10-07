from datetime import datetime
from app.extensions import db


class Employee(db.Model):
    """Personal del negocio (vendedor, chofer, administrador, bodeguero...)."""
    __tablename__ = "employees"

    employee_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    role = db.Column(
        db.Enum("vendedor", "chofer", "administrador", "bodeguero", "otro"),
        nullable=False, default="vendedor")
    phone = db.Column(db.String(20))
    base_salary = db.Column(db.Numeric(12, 2), default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    expenses = db.relationship("Expense", backref="employee")

    def role_label(self):
        return {
            "vendedor": "Vendedor",
            "chofer": "Chofer",
            "administrador": "Administrador",
            "bodeguero": "Bodeguero",
            "otro": "Otro",
        }.get(self.role, self.role)


class Expense(db.Model):
    """Gasto del negocio (sueldos, luz, arriendo, etc.)."""
    __tablename__ = "expenses"

    expense_id = db.Column(db.Integer, primary_key=True)
    expense_date = db.Column(db.Date, nullable=False)
    category = db.Column(
        db.Enum("sueldos", "luz", "arriendo", "agua", "internet", "transporte", "otros"),
        nullable=False, default="otros")
    description = db.Column(db.String(255))
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.employee_id"))
    payment_method = db.Column(db.Enum("efectivo", "transferencia", "cheque", "otro"), default="efectivo")
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship("User", foreign_keys=[created_by])

    def category_label(self):
        return {
            "sueldos": "Sueldos / Personal",
            "luz": "Luz",
            "arriendo": "Arriendo",
            "agua": "Agua",
            "internet": "Internet",
            "transporte": "Transporte",
            "otros": "Otros",
        }.get(self.category, self.category)

    def payment_method_label(self):
        return {
            "efectivo": "Efectivo",
            "transferencia": "Transferencia",
            "cheque": "Cheque",
            "otro": "Otro",
        }.get(self.payment_method, self.payment_method)


class Attendance(db.Model):
    """Asistencia del personal (entrada / salida por dia)."""
    __tablename__ = "attendance"

    attendance_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.employee_id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.Time)
    check_out = db.Column(db.Time)
    notes = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref="attendance")

    def horas(self):
        if self.check_in and self.check_out:
            a = datetime.combine(self.date, self.check_in)
            b = datetime.combine(self.date, self.check_out)
            if b < a:
                b = b.replace(day=b.day)  # mismo dia; si es menor, se asume error
                return None
            return round((b - a).total_seconds() / 3600, 2)
        return None


class LeaveRequest(db.Model):
    """Vacaciones y permisos del personal."""
    __tablename__ = "leave_requests"

    leave_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.employee_id"), nullable=False)
    type = db.Column(db.Enum("vacaciones", "permiso", "enfermedad", "otro"), nullable=False, default="permiso")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(255))
    status = db.Column(db.Enum("pendiente", "aprobado", "rechazado"), default="pendiente")
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref="leaves")

    def dias(self):
        return (self.end_date - self.start_date).days + 1

    def type_label(self):
        return {
            "vacaciones": "Vacaciones",
            "permiso": "Permiso",
            "enfermedad": "Enfermedad",
            "otro": "Otro",
        }.get(self.type, self.type)

    def status_label(self):
        return {"pendiente": "Pendiente", "aprobado": "Aprobado", "rechazado": "Rechazado"}.get(self.status, self.status)


class Advance(db.Model):
    """Adelantos y prestamos de sueldo al personal."""
    __tablename__ = "advances"

    advance_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.employee_id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    kind = db.Column(db.Enum("adelanto", "prestamo"), default="adelanto")
    description = db.Column(db.String(255))
    status = db.Column(db.Enum("pendiente", "descontado"), default="pendiente")
    created_by = db.Column(db.Integer, db.ForeignKey("users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship("Employee", backref="advances")

    def kind_label(self):
        return {"adelanto": "Adelanto", "prestamo": "Préstamo"}.get(self.kind, self.kind)

    def status_label(self):
        return {"pendiente": "Pendiente", "descontado": "Descontado"}.get(self.status, self.status)
