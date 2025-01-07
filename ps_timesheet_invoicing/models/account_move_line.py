# Copyright 2018 The Open Source Company ((www.tosc.nl).)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    ps_invoice_id = fields.Many2one(
        "ps.invoice", string="Invoice Reference", ondelete="cascade", index=True
    )
    user_id = fields.Many2one("res.users", "Timesheet User", index=True)
    user_task_total_line_ids = fields.Many2many(
        comodel_name="ps.time.line.user.total",
        relation="account_move_line_user_total_rel",
        string="Grouped PS Time line",
        ondelete="cascade",
        index=True,
    )
    ps_analytic_line_ids = fields.One2many(
        "account.analytic.line",
        "ps_invoice_line_id",
    )
    # wip_percentage=fields.Float("WIP percentage")

    @api.constrains("operating_unit_id", "analytic_account_id", "user_id")
    def _check_analytic_operating_unit(self):
        for rec in self.filtered("user_id"):
            if rec.operating_unit_id != rec.user_id._get_operating_unit_id():
                raise UserError(
                    _(
                        "The Operating Unit in the"
                        " Move Line must be the "
                        "Operating Unit in the department"
                        " of the user/employee"
                    )
                )
        super(
            AccountMoveLine, self - self.filtered("user_id")
        )._check_analytic_operating_unit()

    @api.onchange("analytic_account_id", "user_id")
    def onchange_operating_unit(self):
        super().onchange_operating_unit()
        if self.user_id:
            self.operating_unit_id = self.user_id._get_operating_unit_id()

    @api.depends("account_analytic_id", "user_id", "move_id.operating_unit_id")
    def _compute_operating_unit(self):
        super()._compute_operating_unit()
        for line in self.filtered("user_id"):
            line.operating_unit_id = line.user_id._get_operating_unit_id()

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        invoice_id = self.env.context.get("default_invoice_id")
        if invoice_id:
            invoice_obj = self.env["account.move"].browse(invoice_id)
            ps_invoice_id = invoice_obj.invoice_line_ids.mapped("ps_invoice_id")
            if ps_invoice_id:
                res["ps_invoice_id"] = ps_invoice_id.id
        return res
