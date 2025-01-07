# Copyright 2018 The Open Source Company ((www.tosc.nl).)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import api, fields, models


class TimelineUserTotal(models.Model):
    _name = "ps.time.line.user.total"
    _description = "Timeline User Total"

    @api.depends("unit_amount", "user_id", "task_id", "ps_invoice_id.task_user_ids")
    def _compute_fee_rate(self):
        """
        First, look get fee rate from task_user_ids from analytic invoice.
        Else, get fee rate from method get_fee_rate()
        :return:
        """
        task_user = self.env["task.user"]
        for this in self:
            # get task-user out of first ptline
            ptline = this.detail_ids[:1]
            task_user = task_user.search(
                [
                    ("id", "in", this.ps_invoice_id.task_user_ids.ids),
                    ("task_id", "=", this.task_id.id),
                    ("from_date", "<=", ptline.date),
                    ("user_id", "=", this.user_id.id),
                ]
            )
            if task_user:
                task_user = task_user.search(
                    [("id", "in", task_user.ids)], limit=1, order="from_date Desc"
                )
                this.fee_rate = fr = task_user.fee_rate
                this.ic_fee_rate = ic_fr = task_user.ic_fee_rate
            else:
                rates = ptline.get_fee_rate(
                    this.task_id.id, this.user_id.id, ptline.date
                )
                this.fee_rate = fr = rates[0]
                this.ic_fee_rate = ic_fr = rates[1]
            this.amount = -this.unit_amount * fr
            this.ic_amount = -this.unit_amount * ic_fr
            this.effective_fee_rate = (
                this.fee_rate
                if this.operating_unit_id == this.project_operating_unit_id
                else this.ic_fee_rate
            )

    def _compute_time_line(self):
        for aut in self:
            aut.count_time_line = str(len(aut.detail_ids)) + " (records)"

    @api.model
    def _default_user(self):
        return self.env.context.get("user_id", self.env.user.id)

    ps_invoice_id = fields.Many2one("ps.invoice")
    fee_rate = fields.Float(compute=_compute_fee_rate, string="Fee Rate")
    ic_fee_rate = fields.Float(
        compute=_compute_fee_rate, string="Intercompany Fee Rate"
    )
    effective_fee_rate = fields.Float(
        compute=_compute_fee_rate, string="Effective Fee Rate"
    )
    amount = fields.Float(compute=_compute_fee_rate, string="Amount")
    ic_amount = fields.Float(compute=_compute_fee_rate, string="Intercompany Amount")
    detail_ids = fields.One2many(
        "ps.time.line",
        "user_total_id",
        string="Detail Time Lines",
        readonly=True,
        copy=False,
    )
    count_time_line = fields.Char(
        compute=_compute_time_line, string="# Detail Time Lines"
    )
    gb_week_id = fields.Many2one(
        "date.range",
        string="Week",
    )
    gb_period_id = fields.Many2one(
        "date.range",
        string="Month",
    )
    period_id = fields.Many2one("date.range")
    name = fields.Char("Description", required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Confirmed"),
            ("delayed", "Delayed"),
            ("invoiceable", "To be Invoiced"),
            ("progress", "In Progress"),
            ("invoice_created", "Invoice Created"),
            ("invoiced", "Invoiced"),
            ("write-off", "Write-Off"),
            ("change-chargecode", "Change-Chargecode"),
            ("re_confirmed", "Re-Confirmed"),
            ("invoiced-by-fixed", "Invoiced by Fixed"),
            ("expense-invoiced", "Expense Invoiced"),
        ],
        string="Status",
        readonly=True,
        copy=False,
        index=True,
        default="draft",
    )
    account_id = fields.Many2one(
        "account.analytic.account",
        "Analytic Account",
        required=True,
        ondelete="restrict",
    )
    partner_id = fields.Many2one(
        "res.partner",
        #        related='account_id.partner_id',
        string="Partner",
        #        store=True,
        #        readonly=True
    )
    user_id = fields.Many2one("res.users", string="User", default=_default_user)
    company_id = fields.Many2one(
        related="account_id.company_id", string="Company", store=True, readonly=True
    )
    department_id = fields.Many2one(
        "hr.department",
        "Department",
        related="user_id.employee_ids.department_id",
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one("product.product", string="Product")
    task_id = fields.Many2one("project.task", "Task")
    project_id = fields.Many2one(
        "project.project", "Project", domain=[("allow_timesheets", "=", True)]
    )
    product_uom_id = fields.Many2one("uom.uom", string="Unit of Measure")
    unit_amount = fields.Float("Quantity", default=0.0)
    operating_unit_id = fields.Many2one(
        "operating.unit", string="Operating Unit", store=True
    )
    project_operating_unit_id = fields.Many2one(
        "operating.unit", string="Project Operating Unit", store=True
    )
    date = fields.Date(
        "Date", required=True, index=True, default=fields.Date.context_today
    )
    line_fee_rate = fields.Float()
