# Copyright 2018 The Open Source Company ((www.tosc.nl).)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
from collections import defaultdict
from itertools import chain

from psycopg2.extensions import AsIs

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tests.common import Form


class PSInvoice(models.Model):
    _name = "ps.invoice"
    _inherit = "mail.thread"
    _inherits = {"account.move": "invoice_id"}
    _description = "PS Invoice"
    _order = "date_to desc"
    _rec_name = "partner_id"

    @api.depends(
        "period_id",
        "gb_week",
        "project_operating_unit_id",
        "project_id",
        "link_project",
    )
    def _compute_objects(self):
        """
        this method computes account_analytic_ids, task_user_ids and user_total_ids
        :param self:
        :return:
        """
        task_user_ids, user_total_data = [], []
        # first we compute user_total_lines already in the invoice and the ps_time_lines
        # we shouldn't look at
        user_total_invoiced_lines, ptl_ids = self._existing_user_total_lines()
        # then we determine the analytic_account_ids, that will be invoiced in this
        # ps_invoice
        analytic_accounts = (
            self._determine_analytic_account_ids() or self.account_analytic_ids.ids
        )
        if not analytic_accounts:
            return
        self.account_analytic_ids = [(6, 0, analytic_accounts)]
        # we build the domains for the selection of ps_time_lines for both regular
        # and reconfirmed ptl's
        time_domain_regular, time_domain_reconfirm = self._calculate_domain(ptl_ids)
        # we determine the grouping of ps_time_lines in the user_total_lines
        (
            reg_fields_grouped,
            reg_grouped_by,
            reconfirmed_fields_grouped,
            reconfirmed_grouped_by,
        ) = self._calculate_grouping()
        # the actual reads of the selected ps_time_lines
        result_regular = self.env["ps.time.line"].read_group(
            time_domain_regular,
            reg_fields_grouped,
            reg_grouped_by,
            offset=0,
            limit=None,
            orderby=False,
            lazy=False,
        )
        result_reconfirm = self.env["ps.time.line"].read_group(
            time_domain_reconfirm,
            reconfirmed_fields_grouped,
            reconfirmed_grouped_by,
            offset=0,
            limit=None,
            orderby=False,
            lazy=False,
        )
        # we calculate the task_user_ids and user_total_ids from the read_group
        # above
        if len(result_regular) > 0:
            task_user_regular, user_total_regular = self._calculate_data(
                result_regular, time_domain_regular
            )
            task_user_ids += task_user_regular
            user_total_data += user_total_regular
        if len(result_reconfirm) > 0:
            task_user_reconfirm, user_total_reconfirm = self._calculate_data(
                result_reconfirm, time_domain_reconfirm, True
            )
            task_user_ids += task_user_reconfirm
            user_total_data += user_total_reconfirm
        if task_user_ids:
            self.task_user_ids = [(6, 0, task_user_ids)]
        else:
            self.task_user_ids = [(6, 0, [])]
        # add user_total_lines already present in the invoice if they still have lines
        for total_line in user_total_invoiced_lines:
            if total_line.detail_ids:
                user_total_data.append((4, total_line.id))
        self.user_total_ids = user_total_data
        if self.invoice_properties.actual_expenses and self.period_id:
            expense_domain = self._get_expense_line_ids_domain()
            self.expense_line_ids = [
                (4, line.id)
                for line in self.env["account.analytic.line"].search(expense_domain)
            ]
        if self.invoice_properties.invoice_mileage and self.period_id:
            self.mileage_line_ids = [
                (4, line.id)
                for line in self.env["ps.time.line"].search(
                    [
                        ("account_id", "in", analytic_accounts),
                        ("product_uom_id", "=", self.env.ref("uom.product_uom_km").id),
                        ("state", "=", "invoiceable"),
                    ]
                    + self.period_id.get_domain("date")
                )
            ]

    def _calculate_data(self, result, time_domain, reconfirmed_entries=False):
        """
        :param self:
        :param result:
        :param time_domain:
        :param reconfirmed_entries:
        :return:
        """
        task_user_ids = []
        user_total_data = []
        task_user_obj = self.env["task.user"]
        for item in result:
            vals = self._prepare_user_total(item, reconfirmed_entries)
            ptl_domain = time_domain + [
                ("user_id", "=", vals["user_id"]),
                ("task_id", "=", vals["task_id"]),
                ("account_id", "=", vals["account_id"]),
                ("product_id", "=", vals["product_id"]),
                ("line_fee_rate", "=", vals["line_fee_rate"]),
            ]
            if reconfirmed_entries:
                ptl_domain += [("month_of_last_wip", "=", vals["gb_period_id"])]
            else:
                ptl_domain += [("period_id", "=", vals["gb_period_id"])]
                if vals["gb_week_id"]:
                    ptl_domain += [("week_id", "=", vals["gb_week_id"])]

            user_total_ps_time_lines = []
            for ptl in self.env["ps.time.line"].search(ptl_domain):
                task_user_lines = task_user_obj.get_task_user_obj(
                    ptl.task_id.id, ptl.user_id.id, ptl.date
                )
                if task_user_lines:
                    task_user_ids += task_user_lines.ids
                user_total_ps_time_lines.append((4, ptl.id))
            vals["detail_ids"] = user_total_ps_time_lines
            user_total_data.append((0, 0, vals))
        return list(set(task_user_ids)), user_total_data

    def _existing_user_total_lines(self):
        ctx = self.env.context.copy()
        current_ref = ctx.get("active_invoice_id", False)
        ptl_ids = self.env["ps.time.line"]
        if not current_ref:
            return [], []
        # get all invoiced user total objs using current reference
        invoiced_states = ("invoice_created", "invoiced", "invoice-by-fixed")
        user_total_invoiced_lines = self.env["ps.time.line.user.total"].search(
            [
                ("ps_invoice_id", "=", current_ref),
                ("state", "in", invoiced_states),
            ]
        )
        # don't look for ps_time lines which have been already added to other analytic
        # invoice
        other_lines = self.env["ps.time.line.user.total"].search(
            [
                ("ps_invoice_id", "!=", current_ref),
                ("state", "not in", invoiced_states),
            ]
        )
        for t in other_lines:
            ptl_ids |= t.detail_ids
        return user_total_invoiced_lines, ptl_ids

    def _determine_analytic_account_ids(self):
        partner_id = self.partner_id or False
        analytic_accounts = self.env["account.analytic.account"]
        if self.project_id and self.link_project:
            partner_id = self.project_id.partner_id
        if partner_id and len(self.account_analytic_ids) == 0:
            analytic_accounts = self.env["account.analytic.account"].search(
                [("partner_id", "=", partner_id.id)]
            )
            if len(analytic_accounts) == 0:
                analytic_accounts = self.env["account.analytic.account"].search(
                    [("partner_id", "=", self.project_id.partner_id.id)]
                )
        return analytic_accounts.ids if len(analytic_accounts) > 0 else False

    def _calculate_domain(self, ptl_ids):
        account_analytic_ids = self.account_analytic_ids.ids
        domain = [("account_id", "in", account_analytic_ids)]
        if self.project_operating_unit_id:
            domain += [
                ("project_operating_unit_id", "=", self.project_operating_unit_id.id)
            ]
        if self.project_id and self.link_project:
            domain += [("project_id", "=", self.project_id.id)]
        else:
            domain += [
                "|",
                ("project_id.invoice_properties.group_invoice", "=", True),
                ("task_id.project_id.invoice_properties.group_invoice", "=", True),
            ]
        hrs = self.env.ref("uom.product_uom_hour").id
        time_domain = domain + [
            ("chargeable", "=", True),
            ("product_uom_id", "=", hrs),
            ("state", "in", ["invoiceable", "progress"]),
        ]
        if ptl_ids:
            time_domain += [("id", "not in", ptl_ids.ids)]
        time_domain_regular = time_domain + [("month_of_last_wip", "=", False)]
        if self.period_id:
            time_domain_regular += self.period_id.get_domain("date")
        time_domain_reconfirm = time_domain + [("month_of_last_wip", "!=", False)]
        return time_domain_regular, time_domain_reconfirm

    def _calculate_grouping(self):
        fields_grouped = [
            "id",
            "user_id",
            "task_id",
            "account_id",
            "product_id",
            "unit_amount",
            "line_fee_rate",
            "operating_unit_id",
            "project_operating_unit_id",
        ]
        grouped_by = [
            "user_id",
            "task_id",
            "account_id",
            "product_id",
            "line_fee_rate",
            "operating_unit_id",
            "project_operating_unit_id",
        ]
        reg_fields_grouped = fields_grouped + ["period_id", "week_id"]
        reg_grouped_by = grouped_by + ["period_id"]
        if self.gb_week:
            reg_grouped_by.append("week_id")
        reconfirmed_fields_grouped = fields_grouped + ["month_of_last_wip"]
        reconfirmed_grouped_by = grouped_by + ["month_of_last_wip"]
        return (
            reg_fields_grouped,
            reg_grouped_by,
            reconfirmed_fields_grouped,
            reconfirmed_grouped_by,
        )

    def _prepare_user_total(self, item, reconfirmed_entries=False):
        task_id = item.get("task_id")[0] if item.get("task_id", False) else False
        project_id = False
        if task_id:
            project_id = self.env["project.task"].browse(task_id).project_id.id or False
        vals = {
            "name": "/",
            "user_id": item.get("user_id")[0] if item.get("user_id", False) else False,
            "task_id": item.get("task_id")[0] if item.get("task_id", False) else False,
            "project_id": project_id,
            "account_id": item.get("account_id")[0]
            if item.get("account_id", False)
            else False,
            "unit_amount": item.get("unit_amount"),
            "product_id": item.get("product_id")[0]
            if item.get("product_id", False)
            else False,
            "operating_unit_id": item.get("operating_unit_id")[0]
            if item.get("operating_unit_id", False)
            else False,
            "project_operating_unit_id": item.get("project_operating_unit_id")[0]
            if item.get("project_operating_unit_id", False)
            else False,
            "line_fee_rate": item.get("line_fee_rate"),
            "period_id": self.period_id.id,
        }
        if reconfirmed_entries:
            vals.update(
                {
                    "gb_period_id": item.get("month_of_last_wip")[0]
                    if item.get("month_of_last_wip")
                    else False
                }
            )
        else:
            vals.update(
                {
                    "gb_period_id": item.get("period_id")[0]
                    if item.get("period_id")
                    else False,
                    "gb_week_id": item.get("week_id")[0]
                    if self.gb_week and item.get("week_id")
                    else False,
                }
            )
        return vals

    def _sql_update(self, self_obj, status):
        if not self_obj.ids or not status:
            return True
        self.env.cr.execute(
            "UPDATE %s SET state = %s WHERE id IN %s",
            (AsIs(self_obj._table), status, tuple(self_obj.ids)),
        )
        self_obj.invalidate_cache(fnames=["state"], ids=self_obj.ids)

    @api.depends("invoice_id.state", "invoice_id.line_ids")
    def _compute_state(self):
        state2ps_line, state2user_total = self._compute_state_updates()

        # TODO: compute functions shouldn't have side effects, this can lead to
        # nasty and hard to debug bugs. Move this to compute functions for the
        # state fields involved
        for state, records in chain(state2ps_line.items(), state2user_total.items()):
            self._sql_update(records, state)

    def _compute_state_updates(self):
        state2ps_line = defaultdict(lambda: self.env["ps.time.line"])
        state2user_total = defaultdict(lambda: self.env["ps.time.line.user.total"])
        for ai in self:
            if not ai.invoice_id:
                ai.state = "draft"
                user_totals = ai.user_total_ids.filtered(lambda ut: ut.state != "draft")
                state2ps_line["progress"] += user_totals.mapped("detail_ids")
                state2ps_line["progress"] += ai.mileage_line_ids
                state2user_total["draft"] += user_totals

            elif ai.invoice_id.state == "cancel":
                ai.state = "draft"
                user_totals = ai.mapped("invoice_line_ids.user_task_total_line_ids")
                state2ps_line["progress"] += user_totals.mapped("detail_ids")
                state2ps_line["progress"] += ai.mileage_line_ids
                state2user_total["draft"] += user_totals

            elif ai.invoice_id.state == "draft":
                ai.state = "open"
                user_totals = ai.mapped("invoice_line_ids.user_task_total_line_ids")
                state2ps_line["invoice_created"] += user_totals.mapped("detail_ids")
                state2ps_line["invoice_created"] += ai.mileage_line_ids
                state2user_total["invoice_created"] += user_totals

            elif ai.invoice_id.state == "posted":
                ai.state = "invoiced"
                line_state = "invoiced"
                if ai.invoice_properties.fixed_amount:
                    line_state = "invoiced-by-fixed"
                user_totals = ai.mapped("invoice_line_ids.user_task_total_line_ids")
                state2ps_line[line_state] += user_totals.mapped("detail_ids")
                state2ps_line["invoiced"] += ai.mileage_line_ids
                state2user_total[line_state] += user_totals

        return state2ps_line, state2user_total

    @api.model
    def _get_fiscal_month_domain(self):
        # We have access to self.env in this context.
        fm = self.env.ref("account_fiscal_month.date_range_fiscal_month").id
        return [("type_id", "=", fm)]

    @api.depends("user_total_ids")
    def _compute_task_user_ids_domain(self):
        for rec in self:
            rec.task_user_ids_domain = json.dumps(
                [
                    ("user_id", "in", rec.user_total_ids.mapped("user_id").ids),
                    ("task_id", "in", rec.user_total_ids.mapped("task_id").ids),
                ]
            )

    @api.onchange("account_analytic_ids")
    def onchange_account_analytic(self):
        res = {}
        operating_units = self.env["operating.unit"]
        for aa in self.account_analytic_ids:
            operating_units |= aa.operating_unit_ids
        if operating_units:
            res["domain"] = {
                "project_operating_unit_id": [("id", "in", operating_units.ids)]
            }
        return res

    name = fields.Char(string="Name")
    account_analytic_ids = fields.Many2many(
        "account.analytic.account",
        compute="_compute_objects",
        string="Analytic Account",
        store=True,
    )
    task_user_ids_domain = fields.Char(
        compute="_compute_task_user_ids_domain",
        readonly=True,
        store=False,
    )
    task_user_ids = fields.Many2many(
        "task.user", compute="_compute_objects", string="Task Fee Rate", store=True
    )
    invoice_id = fields.Many2one(
        "account.move",
        string="Customer Invoice",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    expense_line_ids = fields.One2many(
        "account.analytic.line",
        "ps_invoice_id",
        string="Expenses",
        store=True,
    )
    expense_line_ids_domain = fields.Char(
        compute="_compute_expense_line_ids_domain",
    )
    mileage_line_ids = fields.Many2many(
        comodel_name="ps.time.line",
        relation="ps_invoice_mileage_time_line_rel",
        string="Mileage",
        store=True,
        readonly=True,
    )
    user_total_ids = fields.One2many(
        "ps.time.line.user.total",
        "ps_invoice_id",
        compute="_compute_objects",
        string="User Total Line",
        store=True,
    )
    period_id = fields.Many2one("date.range")
    date_from = fields.Date(related="period_id.date_start", string="Date From")
    date_to = fields.Date(related="period_id.date_end", string="Date To", store=True)
    gb_week = fields.Boolean("Group By Week", default=False)
    gb_month = fields.Boolean("Group By Month", default=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "In Progress"),
            ("invoiced", "Invoiced"),
        ],
        string="Status",
        compute="_compute_state",
        copy=False,
        index=True,
        store=True,
        tracking=True,
    )
    project_operating_unit_id = fields.Many2one(
        "operating.unit",
        string="Project Operating Unit",
    )
    link_project = fields.Boolean(
        "Link Project",
        help="If true then must select project of type group invoice False",
    )
    project_id = fields.Many2one(
        "project.project", domain=[("invoice_properties.group_invoice", "=", False)]
    )
    invoice_properties = fields.Many2one(
        "project.invoicing.properties",
        related="project_id.invoice_properties",
        string="Invoice Properties",
        store=True,
    )
    actual_expenses = fields.Boolean(related="invoice_properties.actual_expenses")
    invoice_mileage = fields.Boolean(related="invoice_properties.invoice_mileage")

    @api.depends("account_analytic_ids")
    def _compute_expense_line_ids_domain(self):
        with_date = not self.env.user.has_group("account.group_account_manager")
        for this in self:
            this.expense_line_ids_domain = json.dumps(
                this._get_expense_line_ids_domain(with_date=with_date)
            )

    def _get_expense_line_ids_domain(self, with_date=True):
        account_types = self.env.ref(
            "account.data_account_type_expenses"
        ) + self.env.ref("account.data_account_type_direct_costs")
        return [
            ("ps_invoice_id", "=", False),
            ("ps_invoice_line_id", "=", False),
            ("account_id", "in", self.account_analytic_ids.ids),
            ("general_account_id.user_type_id", "in", account_types.ids),
        ] + (
            [
                (field, operator, fields.Date.to_string(date))
                for (field, operator, date) in self.period_id.get_domain("date")
            ]
            if with_date
            else []
        )

    def unlink_rec(self):
        user_total_ids = self.env["ps.time.line.user.total"].search(
            [("ps_invoice_id", "=", False)]
        )
        if user_total_ids:
            # reset ps time line state to invoiceable
            ps_time_lines = user_total_ids.mapped("detail_ids")
            ps_time_lines.write({"state": "invoiceable"})
            user_total_ids.unlink()

    def write(self, vals):
        if "invoice_line_ids" in vals:
            vals = dict(vals)
            edit_commands = filter(lambda x: x[0] == 1, vals["invoice_line_ids"])
            vals["invoice_line_ids"] = list(
                filter(lambda x: x[0] != 1, vals["invoice_line_ids"])
            )
            if edit_commands:
                self._write_invoice_line_ids(edit_commands)
        res = super().write(vals)
        self.unlink_rec()
        analytic_lines = self.user_total_ids.mapped("detail_ids")
        if analytic_lines:
            analytic_lines.write({"state": "progress"})
        return res

    def _write_invoice_line_ids(self, invoice_line_commands):
        """
        changing invoice_line_ids is tricky because the invoice form does a lot of
        recomputations in its onchange methods. We simulate that here
        """
        for this in self.filtered("invoice_id"):
            with Form(this.invoice_id) as invoice_form:
                for index in range(len(invoice_form.invoice_line_ids)):
                    with invoice_form.invoice_line_ids.edit(index) as invoice_line:
                        # support only edits for now
                        for cmd_tuple in invoice_line_commands:
                            if cmd_tuple[0] == 1 and cmd_tuple[1] == invoice_line.id:
                                for key, value in cmd_tuple[2].items():
                                    setattr(invoice_line, key, value)

    @api.model
    def create(self, vals):
        res = super().create(vals)
        analytic_lines = res.user_total_ids.mapped("detail_ids")
        if analytic_lines:
            analytic_lines.write({"state": "progress"})
        return res

    def unlink(self):
        """
        reset analytic line state to invoiceable
        :return:
        """
        self._sql_update(self.mapped("user_total_ids.detail_ids"), "invoiceable")
        self._sql_update(self.mapped("mileage_line_ids"), "invoiceable")
        return super().unlink()

    def _prepare_invoice_line(
        self,
        product,
        uom,
        quantity,
        user,
        analytic_account,
        price_unit,
    ):
        invoice_line = (
            self.env["account.move.line"]
            .with_context(
                active_model="analytic.invoice",
                active_id=self.invoice_id.id,
                active_ids=self.invoice_id.ids,
            )
            .new(
                {
                    "move_id": self.invoice_id.id,
                    "product_id": product.id,
                    "quantity": quantity,
                    "product_uom_id": uom.id,
                    "user_id": user.id,
                    "operating_unit_id": user and user._get_operating_unit_id().id,
                }
            )
        )
        # Get other invoice line values from product onchange
        invoice_line._onchange_product_id()
        invoice_line_vals = invoice_line._convert_to_write(invoice_line._cache)

        invoice_line_vals.update(
            {
                "analytic_account_id": analytic_account.id
                or invoice_line.analytic_account_id.id,
                "price_unit": price_unit,
                "ps_invoice_id": self.id,
                # TODO: no origin field any more, readd?
                # 'origin': line.task_id.project_id.po_number
                # if line.task_id and line.task_id.project_id.correction_charge
                # else '/',
            }
        )

        return invoice_line_vals

    def _prepare_invoice_lines_fixed_amount(self, user_total_lines):
        product = self.env.ref("ps_timesheet_invoicing.product_fixed_amount")
        return [
            dict(
                self._prepare_invoice_line(
                    product,
                    product.uom_id,
                    1,
                    self.env["res.users"],
                    self.account_analytic_ids[:1],
                    self.project_id.ps_fixed_amount,
                ),
                name=self.project_id.name,
                currency_id=self.project_id.partner_currency_id.id,
                user_task_total_line_ids=[(6, 0, user_total_lines.ids)],
            )
        ]

    def _prepare_expense_invoice_line(self):
        return (
            [
                {
                    "name": _("Expenses"),
                    "quantity": 1,
                    "price_unit": -sum(self.expense_line_ids.mapped("amount")),
                    "ps_analytic_line_ids": [(6, 0, self.expense_line_ids.ids)],
                    "operating_unit_id": self.operating_unit_id.id,
                }
            ]
            if sum(self.expense_line_ids.mapped("amount"))
            else []
        )

    def _prepare_mileage_invoice_line(self):
        product = self.project_id.ps_mileage_product_id or self.env.ref(
            "ps_timesheet_invoicing.product_mileage"
        )
        return (
            [
                self._prepare_invoice_line(
                    product,
                    product.uom_id,
                    sum(self.mileage_line_ids.mapped("unit_amount")),
                    self.env["res.users"],
                    self.env["account.analytic.account"],
                    self.project_id.ps_fixed_amount,
                ),
            ]
            if sum(self.mileage_line_ids.mapped("unit_amount"))
            else []
        )

    def generate_invoice(self):
        self.ensure_one()
        if self.invoice_id.state == "cancel":
            raise UserError(
                _("Can't generate invoice, kindly re-set invoice to draft'")
            )
        user_summary_lines = self.user_total_ids.filtered(lambda x: x.state == "draft")
        ptl_from_summary = self.env["ps.time.line"]
        user_total = self.env["ps.time.line.user.total"]

        invoice_lines = []

        props = self.invoice_properties
        if props.fixed_amount:
            user_total = user_summary_lines
            invoice_lines = [(5, False)] + [
                (0, 0, vals)
                for vals in self._prepare_invoice_lines_fixed_amount(user_summary_lines)
            ]
        else:
            for line in user_summary_lines:
                inv_line_vals = self._prepare_invoice_line(
                    line.product_id,
                    line.product_uom_id,
                    line.unit_amount,
                    line.user_id,
                    line.account_id,
                    line.effective_fee_rate,
                )
                inv_line_vals["user_task_total_line_ids"] = [(6, 0, line.ids)]
                invoice_lines.append((0, 0, inv_line_vals))
                ptl_from_summary |= line.detail_ids
                user_total |= line

        if self.actual_expenses:
            invoice_lines += [
                (3, line.id)
                for line in self.invoice_id.invoice_line_ids.filtered(
                    "ps_analytic_line_ids"
                )
            ]
            invoice_lines += [
                (0, 0, vals) for vals in self._prepare_expense_invoice_line()
            ]

        if self.invoice_mileage:
            invoice_lines += [
                (3, line.id)
                for line in self.invoice_id.invoice_line_ids.filtered(
                    lambda x: x.product_id == self.project_id.ps_mileage_product_id
                )
            ]
            invoice_lines += [
                (0, 0, vals) for vals in self._prepare_mileage_invoice_line()
            ]

        if invoice_lines:
            self.write({"invoice_line_ids": invoice_lines})

        if self.state == "draft" and ptl_from_summary:
            self.state = "open"
        if ptl_from_summary:
            self._sql_update(ptl_from_summary, "invoice_created")
        if user_total:
            self._sql_update(user_total, "invoice_created")
        self._sql_update(self.mileage_line_ids, "invoice_created")
        return True

    def delete_invoice(self):
        self.mapped("invoice_id").button_draft()
        self.mapped("invoice_id.line_ids").unlink()

        self.state = "draft"
        for user_total in self.user_total_ids:
            self._sql_update(user_total.detail_ids, "progress")
            self._sql_update(user_total, "draft")
        self._sql_update(self.mileage_line_ids, "progress")

    def action_view_invoices(self):
        self.ensure_one()
        action = self.env.ref("account.action_move_out_invoice_type").read()[0]
        invoices = self.mapped("invoice_id")
        if len(invoices) > 1:
            action["domain"] = [("id", "in", invoices.ids)]
        elif invoices:
            action["views"] = [(self.env.ref("account.view_move_form").id, "form")]
            action["res_id"] = invoices.id
        return action

    def _get_user_per_month(self):
        self.ensure_one()
        result = {}

        # FIX:on invoice send by mail action, self.user_total_ids is returning as empty set
        user_total_objs = self.user_total_ids
        if not user_total_objs:
            usrTotIDS = self.read(["user_total_ids"])[0]["user_total_ids"]
            user_total_objs = self.user_total_ids.browse(usrTotIDS)

        project = self.env["project.project"]
        user = self.env["res.users"]

        analytic_obj = user_total_objs.mapped("detail_ids")

        self.env.cr.execute(
            """
            SELECT pp.id AS project_id, prop.group_by_month, prop.group_by_fee_rate
            FROM project_invoicing_properties prop
            JOIN project_project pp ON pp.invoice_properties = prop.id
            JOIN
                (
                    SELECT project_id FROM ps_time_line ptl WHERE ptl.id IN %s
                    GROUP BY project_id
                ) AS temp
                ON temp.project_id = pp.id
            WHERE prop.specs_invoice_report = TRUE
            """,
            (tuple(analytic_obj.ids),),
        )

        grp_data = self.env.cr.fetchall()
        for data in grp_data:
            fields_grouped = [
                "id",
                "project_id",
                "user_id",
                "period_id",
                "line_fee_rate",
                "unit_amount",
                "amount",
            ]
            grouped_by = [
                "project_id",
                "user_id",
            ]

            if data[1]:
                grouped_by += [
                    "period_id",
                ]
            if data[2]:
                grouped_by += [
                    "line_fee_rate",
                ]

            ptl_grp_data = self.env["ps.time.line"].read_group(
                [("id", "in", analytic_obj.ids), ("project_id", "=", data[0])],
                fields_grouped,
                grouped_by,
                offset=0,
                limit=None,
                orderby=False,
                lazy=False,
            )

            for item in ptl_grp_data:
                project_obj = project.browse(item.get("project_id")[0])
                user_obj = user.browse(item.get("user_id")[0])
                unit_amount = item.get("unit_amount")
                fee_rate = item.get("line_fee_rate")
                amount = item.get("amount")
                month = (
                    self.env["date.range"].browse(item.get("period_id")[0])
                    if item.get("period_id", False)
                    else "null"
                )
                gb_fee_rate = abs(fee_rate) if data[2] else "null"

                if month in result:
                    if gb_fee_rate in result[month]:
                        if project_obj in result[month][gb_fee_rate]:
                            if user_obj in result[month][gb_fee_rate][project_obj]:
                                result[month][gb_fee_rate][project_obj][user_obj][
                                    "hours"
                                ] += unit_amount
                                result[month][gb_fee_rate][project_obj][user_obj][
                                    "fee_rate"
                                ] += fee_rate
                                result[month][gb_fee_rate][project_obj][user_obj][
                                    "amount"
                                ] += amount
                            else:
                                result[month][gb_fee_rate][project_obj][user_obj] = {
                                    "hours": unit_amount,
                                    "fee_rate": fee_rate,
                                    "amount": amount,
                                }
                            result[month][gb_fee_rate][project_obj][
                                "hrs_tot"
                            ] += unit_amount
                            result[month][gb_fee_rate][project_obj]["amt_tot"] += amount
                        else:
                            result[month][gb_fee_rate][project_obj] = {
                                "hrs_tot": unit_amount,
                                "amt_tot": amount,
                            }
                            result[month][gb_fee_rate][project_obj][user_obj] = {
                                "hours": unit_amount,
                                "fee_rate": fee_rate,
                                "amount": amount,
                            }

                    else:
                        result[month][gb_fee_rate] = {}
                        result[month][gb_fee_rate][project_obj] = {
                            "hrs_tot": unit_amount,
                            "amt_tot": amount,
                        }
                        result[month][gb_fee_rate][project_obj][user_obj] = {
                            "hours": unit_amount,
                            "fee_rate": fee_rate,
                            "amount": amount,
                        }
                else:
                    result[month] = {}
                    result[month][gb_fee_rate] = {}
                    result[month][gb_fee_rate][project_obj] = {
                        "hrs_tot": unit_amount,
                        "amt_tot": amount,
                    }
                    result[month][gb_fee_rate][project_obj][user_obj] = {
                        "hours": unit_amount,
                        "fee_rate": fee_rate,
                        "amount": amount,
                    }
        return result

    def _get_user_per_day(self):
        self.ensure_one()
        result = {}
        for user_tot in self.user_total_ids:
            inv_property = user_tot.project_id.invoice_properties
            if (
                inv_property.specs_invoice_report
                and inv_property.specs_type != "per_month"
            ):
                if user_tot.project_id in result:
                    result[user_tot.project_id] |= user_tot.detail_ids
                else:
                    result[user_tot.project_id] = user_tot.detail_ids
        return result

    def _get_specs_on_task(self):
        self.ensure_one()
        result = {}

        # FIX:on invoice send by mail action, self.user_total_ids is returning as empty set
        user_total_objs = self.user_total_ids
        if not user_total_objs:
            usrTotIDS = self.read(["user_total_ids"])[0]["user_total_ids"]
            user_total_objs = self.user_total_ids.browse(usrTotIDS)

        project = self.env["project.project"]
        task = self.env["project.task"]

        analytic_obj = user_total_objs.mapped("detail_ids")

        self.env.cr.execute(
            """
                SELECT pp.id AS project_id, prop.group_by_month, prop.group_by_fee_rate
                FROM project_invoicing_properties prop
                JOIN project_project pp ON pp.invoice_properties = prop.id
                JOIN (
                    SELECT project_id FROM ps_time_line ptl WHERE ptl.id IN %s
                    GROUP BY project_id
                ) AS temp ON temp.project_id = pp.id
                WHERE prop.specs_invoice_report = TRUE AND prop.specs_on_task_level = TRUE
            """,
            (tuple(analytic_obj.ids),),
        )

        grp_data = self.env.cr.fetchall()
        for data in grp_data:
            fields_grouped = [
                "id",
                "project_id",
                "task_id",
                "period_id",
                "line_fee_rate",
                "unit_amount",
            ]
            grouped_by = [
                "project_id",
                "task_id",
            ]

            if data[1]:
                grouped_by += [
                    "period_id",
                ]
            if data[2]:
                grouped_by += [
                    "line_fee_rate",
                ]

            ptl_grp_data = self.env["ps.time.line"].read_group(
                [("id", "in", analytic_obj.ids), ("project_id", "=", data[0])],
                fields_grouped,
                grouped_by,
                offset=0,
                limit=None,
                orderby=False,
                lazy=False,
            )

            for item in ptl_grp_data:
                project_obj = project.browse(item.get("project_id")[0])
                task_obj = task.browse(item.get("task_id")[0])
                unit_amount = item.get("unit_amount")
                fee_rate = item.get("line_fee_rate")
                month = (
                    self.env["date.range"].browse(item.get("period_id")[0])
                    if item.get("period_id", False)
                    else "null"
                )

                gb_fee_rate = abs(fee_rate) if data[2] else "null"
                if month in result:
                    if gb_fee_rate in result[month]:
                        if project_obj in result[month][gb_fee_rate]:
                            if task_obj in result[month][gb_fee_rate][project_obj]:
                                result[month][gb_fee_rate][project_obj][task_obj][
                                    "unit_amount"
                                ] += unit_amount
                            else:
                                result[month][gb_fee_rate][project_obj][task_obj] = {
                                    "unit_amount": unit_amount
                                }
                        else:
                            result[month][gb_fee_rate][project_obj] = {}
                            result[month][gb_fee_rate][project_obj][task_obj] = {
                                "unit_amount": unit_amount
                            }
                    else:
                        result[month][gb_fee_rate] = {}
                        result[month][gb_fee_rate][project_obj] = {}
                        result[month][gb_fee_rate][project_obj][task_obj] = {
                            "unit_amount": unit_amount
                        }
                else:
                    result[month] = {}
                    result[month][gb_fee_rate] = {}
                    result[month][gb_fee_rate][project_obj] = {}
                    result[month][gb_fee_rate][project_obj][task_obj] = {
                        "unit_amount": unit_amount
                    }
        return result
