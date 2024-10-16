# Copyright 2014-2023 The Open Source Company ((www.tosc.nl).)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ProjectInvoicingProperties(models.Model):
    _inherit = "project.invoicing.properties"

    custom_layout = fields.Boolean("Add Custom Header/Footer")
    custom_header = fields.Text("Custom Header")
    custom_footer = fields.Text("Custom Footer")
    specs_on_task_level = fields.Boolean("Specification on task level")
    print_description_or_task_name = fields.Boolean("Print description Instead Of Task Name")
