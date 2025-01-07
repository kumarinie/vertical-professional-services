# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)


from dateutil.relativedelta import SA, SU, relativedelta

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError, ValidationError


class PsContractedLine(models.Model):
    _name = "ps.contracted.line"
    _inherit = "ps.planning.department.mixin"
    _description = "Contracted entry"
    _order = "project_id, task_id, product_id"

    project_id = fields.Many2one("project.project", ondelete="cascade", required=True)
    project_user_id = fields.Many2one(related="project_id.user_id", store=True)
    project_partner_id = fields.Many2one(related="project_id.partner_id", store=True)
    task_id = fields.Many2one(
        "project.task",
        ondelete="cascade",
        required=True,
        domain="[('project_id', '=', project_id), '|', ('stage_id.fold', '=', False),"
        "('stage_id', '=', False)]",
    )
    product_id = fields.Many2one(
        "product.product",
        domain=lambda self: [
            (
                "categ_id",
                "=",
                self.env.ref("ps_timesheet_invoicing.product_category_fee_rate").id,
            )
        ],
        ondelete="cascade",
        required=True,
    )
    date_from = fields.Date()
    date_to = fields.Date()
    days = fields.Float()
    range_id = fields.Many2one("date.range", copy=False)
    rate = fields.Monetary(currency_field="currency_id", group_operator="avg")
    value = fields.Monetary(currency_field="currency_id")
    currency_id = fields.Many2one(
        "res.currency", default=lambda self: self.env.company.currency_id
    )
    planning_line_ids = fields.One2many("ps.planning.line", "contracted_line_id")

    def _get_date_range(self, date_from=None, date_to=None):
        range_type = self.env.ref("ps_planning.date_range_type_contracted_period")
        return self.env["date.range"].search(
            [
                ("type_id", "=", range_type.id),
                ("date_start", "=", date_from or self.date_from),
                ("date_end", "=", date_to or self.date_to),
            ]
        )

    def _create_or_assign_date_range(self):
        DateRange = self.env["date.range"]
        range_type = self.env.ref("ps_planning.date_range_type_contracted_period")
        month_type = self.env.ref("account_fiscal_month.date_range_fiscal_month")
        for this in self:
            if this.date_from and this.date_to:
                month_date = this.date_from.replace(day=1)
                while month_date <= this.date_to:
                    if not DateRange.search(
                        [
                            ("date_start", "<=", month_date),
                            ("date_end", ">=", month_date),
                            ("type_id", "=", month_type.id),
                        ]
                    ):
                        raise UserError(
                            _(
                                "Date range for %s is missing, please contact your "
                                "administrator"
                            )
                            % month_date
                        )
                    month_date += relativedelta(months=1)
                date_range = self._get_date_range()
                if not date_range:
                    date_range = DateRange.create(
                        {
                            "name": "%s - %s"
                            % (
                                tools.format_date(self.env, this.date_from),
                                tools.format_date(self.env, this.date_to),
                            ),
                            "type_id": range_type.id,
                            "date_start": this.date_from,
                            "date_end": this.date_to,
                        }
                    )
                this.range_id = date_range

    @api.constrains("project_id", "task_id", "product_id", "range_id")
    def _check_project_id(self):
        for this in self:
            if (
                not this.project_id
                or not this.task_id
                or not this.product_id
                or not this.range_id
            ):
                continue
            if self.search(
                [
                    ("project_id", "=", this.project_id.id),
                    ("task_id", "=", this.task_id.id),
                    ("product_id", "=", this.product_id.id),
                    ("range_id", "=", this.range_id.id),
                    ("id", "!=", this.id),
                ]
            ):
                raise ValidationError(
                    _(
                        "The combination of project, task, product and period must be unique"
                    )
                )
            if self.search(
                [
                    ("project_id", "=", this.project_id.id),
                    ("task_id", "=", this.task_id.id),
                    ("product_id", "=", this.product_id.id),
                    ("range_id.date_start", "<=", this.range_id.date_end),
                    ("range_id.date_end", ">=", this.range_id.date_start),
                    ("id", "!=", this.id),
                ]
            ):
                raise ValidationError(
                    _("You cannot have overlapping contracts for the same task/product")
                )
            if this.task_id and not this.task_id & this.project_id.task_ids:
                raise UserError(_("Select a task from the chosen project"))

    def onchange(self, values, field_name, field_onchange):
        """Avoid recomutation loop when setting value, which sets rate, recomputing value"""
        result = super().onchange(values, field_name, field_onchange)
        if field_name == "value":
            result.get("value", {}).pop("value", False)
        return result

    @api.onchange("days", "rate")
    def _onchange_days(self):
        if self.days and self.rate:
            self.value = self.days * self.rate
        elif self.days and self.value:
            self.rate = self.value / self.days
        elif self.rate and self.value:
            self.days = self.value / self.rate

    @api.onchange("value")
    def _onchange_value(self):
        self.rate = (self.value / self.days) if self.days else 0

    @api.onchange("project_id")
    def _onchange_project_id(self):
        self.task_id = False

    @api.model_create_multi
    def create(self, vals):
        result = super().create(vals)
        result._create_or_assign_date_range()
        return result

    def write(self, vals):
        result = super().write(vals)
        if "date_from" in vals or "date_to" in vals:
            self._create_or_assign_date_range()
            out_of_range_lines = self.planning_line_ids.filtered(
                lambda x: x.range_id.date_end < self[:1].date_from
                or x.range_id.date_start > self[:1].date_to
            )
            if any(
                line.line_type == "planned" and line.days for line in out_of_range_lines
            ):
                raise UserError(
                    _("You have planned time out of the new contract period")
                )
            out_of_range_lines.unlink()
        if "date_from" in vals or "date_to" in vals or "days" in vals:
            for this in self:
                planning_line_by_month = {
                    line.range_id: line
                    for line in this.planning_line_ids.filtered(
                        lambda x: x.line_type == "contracted"
                    )
                }
                for (
                    month,
                    contracted_days,
                ) in this._get_contracted_days_by_month().items():
                    if month in planning_line_by_month:
                        planning_line_by_month[month].days = contracted_days
        if "task_id" in vals or "product_id" in vals:
            self.planning_line_ids.write(
                {
                    key: value
                    for key, value in vals.items()
                    if key in ("task_id", "product_id")
                }
            )
        return result

    def _get_contracted_days_by_month(self):
        months = self.env["ps.planning.wizard"]._get_months(self.range_id)
        available_work_days = self._get_work_days(self.range_id)
        contracted_days_by_month = {
            month: self.days
            * round(self._get_work_days(month) / available_work_days, 2)
            for month in months
        }
        contracted_days_by_month[months[-1:]] += self.days - sum(
            contracted_days_by_month.values()
        )
        return contracted_days_by_month

    def _get_work_days(self, period):
        return self._get_work_days_dates(period.date_start, period.date_end)

    def _get_work_days_dates(self, date_start, date_end):
        start_weekday = date_start.weekday()
        end_weekday = date_end.weekday()
        weeks = (
            (
                (date_end + relativedelta(weekday=SU))
                - (
                    date_start
                    + (
                        relativedelta(weekday=SA)
                        if start_weekday != 6
                        else relativedelta(days=-1)
                    )
                )
            ).days
            - 1
        ) / 7
        days = weeks * 5
        if start_weekday < 5:
            days += 5 - start_weekday
        if end_weekday < 4:
            days -= 4 - end_weekday
        return days
