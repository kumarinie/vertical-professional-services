# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

from odoo import fields, models


class PsPlanningLine(models.Model):
    _name = "ps.planning.line"
    _inherit = "ps.planning.department.mixin"
    _description = "Planning entry"
    _order = "project_id, task_id, employee_id, range_id"

    line_type = fields.Selection(
        [("contracted", "Contracted"), ("planned", "Planned")],
        default="planned",
        required=True,
    )
    state = fields.Selection([("draft", "Draft"), ("final", "Final")], default="draft")
    range_id = fields.Many2one("date.range", string="Period", required=True)
    task_id = fields.Many2one("project.task", required=True)
    product_id = fields.Many2one("product.product", required=True)
    employee_id = fields.Many2one("hr.employee")
    days = fields.Float(required=True)
    contracted_line_id = fields.Many2one(
        "ps.contracted.line", required=True, ondelete="cascade"
    )
    project_id = fields.Many2one(related="task_id.project_id", store=True)
    project_user_id = fields.Many2one(related="task_id.project_id.user_id", store=True)
    project_partner_id = fields.Many2one(
        related="task_id.project_id.partner_id", store=True
    )

    _sql_constraints = [
        (
            "unique_all",
            "unique (range_id, task_id, product_id, employee_id, line_type)",
            "The combination of range, task, product and employee must be unique",
        )
    ]
