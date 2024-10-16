import calendar
from datetime import date

from odoo import api, fields, models


class MaintenanceEquipment(models.Model):
    _name = "maintenance.equipment"
    _inherit = "maintenance.equipment"

    # General fields
    purchase_date = fields.Date(
        string="Date of acquisition", default=fields.Date.context_today
    )
    maintenance_status = fields.Many2one(
        "maintenance.equipment.maintenance.status", string="Equipment Status"
    )
    brand = fields.Char(string="Brand")
    model = fields.Char(string="Model")
    warranty_category = fields.Many2one(
        "maintenance.equipment.warranty.category",
        string="Warranty Category",
        tracking=True,
    )
    warranty_date = fields.Date(
        string="Warranty until", compute="_compute_warranty_date"
    )
    department = fields.Many2one("hr.department", string="Department")

    # Phone specific fields
    phone_number = fields.Char(string="Phone Number", size=10)
    sim_number = fields.Char(string="SIM number")
    puk_code = fields.Char(string="PUK Code")
    imei_number = fields.Char(string="IMEI Number")
    remarks = fields.Text(string="Remarks")

    # Laptop specific fields
    cpu = fields.Char(string="CPU")
    memory = fields.Char(string="Memory")
    hard_disk = fields.Char(string="Hard Disk")
    accessories = fields.Text(string="Accessories")
    iso_security_check = fields.Date(string="ISO/Security Check")

    @api.depends("purchase_date", "warranty_category.warranty_duration")
    def _compute_warranty_date(self):
        purchase_date = self.purchase_date
        month = purchase_date.month - 1 + self.warranty_category.warranty_duration
        year = purchase_date.year + month // 12
        month = month % 12 + 1
        day = min(purchase_date.day, calendar.monthrange(year, month)[1])
        self.warranty_date = date(year, month, day)
