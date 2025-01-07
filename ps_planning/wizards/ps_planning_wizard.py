# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

from odoo import _, api, exceptions, fields, models


class PsPlanningWizard(models.TransientModel):
    _name = "ps.planning.wizard"
    _description = "PS planning wizard"
    _rec_name = "project_id"

    project_id = fields.Many2one("project.project", required=True)
    period_id = fields.Many2one("date.range", required=True)
    available_period_ids = fields.One2many(
        "date.range", compute="_compute_available_period_ids"
    )
    contracted_line_ids = fields.One2many(
        "ps.contracted.line", compute="_compute_contracted_line_ids"
    )
    line_ids = fields.One2many("ps.planning.wizard.line", "wizard_id")
    add_line_task_id = fields.Many2one("project.task", string="Task")
    available_task_ids = fields.One2many(
        "project.task", compute="_compute_available_task_ids"
    )
    add_line_product_id = fields.Many2one("product.product", string="Product")
    available_product_ids = fields.One2many(
        "product.product", compute="_compute_available_product_ids"
    )
    add_line_employee_id = fields.Many2one("hr.employee", string="Employee")

    @api.depends("project_id")
    def _compute_available_period_ids(self):
        self.available_period_ids = self.project_id.mapped(
            "ps_contracted_line_ids.range_id"
        )

    @api.depends("project_id", "period_id")
    def _compute_contracted_line_ids(self):
        for this in self:
            this.contracted_line_ids = this.project_id.ps_contracted_line_ids.filtered(
                lambda x: x.range_id == this.period_id
            )

    @api.depends("contracted_line_ids")
    def _compute_available_task_ids(self):
        self.available_task_ids = self.contracted_line_ids.mapped("task_id")

    @api.depends("contracted_line_ids", "add_line_task_id")
    def _compute_available_product_ids(self):
        self.available_product_ids = self.contracted_line_ids.filtered(
            lambda x: x.task_id == self.add_line_task_id
        ).mapped("product_id")

    @api.onchange("project_id")
    def _onchange_project_id(self):
        self.period_id = False

    @api.onchange("add_line_task_id")
    def _onchange_add_line_employee_id(self):
        self.add_line_product_id = False
        self.add_line_employee_id = False

    @api.constrains("line_ids")
    def _check_line_ids(self):
        for this in self:
            contracted = this.line_ids.filtered(lambda x: x.line_type == "contracted")
            for contracted_line in contracted.contracted_line_id:
                planning_lines = contracted.filtered(
                    lambda x: x.task_id == contracted_line.task_id
                    and x.product_id == contracted_line.product_id
                )
                if sum(planning_lines.mapped("days")) < contracted_line.days:
                    raise exceptions.ValidationError(
                        _("You need to plan at least %d days for %s, %s")
                        % (
                            contracted_line.days,
                            contracted_line.task_id.display_name,
                            contracted_line.product_id.display_name,
                        )
                    )

    def action_add_line(self):
        if (
            not self.add_line_employee_id
            or not self.add_line_task_id
            or not self.add_line_product_id
        ):
            return
        for month in self._get_months():
            self._add_line(month)
        self.add_line_employee_id = self.env["hr.employee"]

    def action_remove_line(self):
        if (
            not self.add_line_employee_id
            or not self.add_line_task_id
            or not self.add_line_product_id
        ):
            return
        self.line_ids.filtered(
            lambda x: x.employee_id == self.add_line_employee_id
            and x.task_id == self.add_line_task_id
            and x.product_id == self.add_line_product_id
        ).unlink()

    def _add_line(self, month, task=None, product=None, employee=None, **extra_vals):
        task = task or self.add_line_task_id
        product = product or self.add_line_product_id
        employee = employee if employee is not None else self.add_line_employee_id
        planning_line = self.env["ps.planning.line"].search(
            [
                ("range_id", "=", month.id),
                ("task_id", "=", task.id),
                ("product_id", "=", product.id),
                ("line_type", "=", "planned"),
                ("employee_id", "=", employee.id),
            ],
        )
        contracted_line = self.contracted_line_ids.filtered_domain(
            [
                ("task_id", "=", task.id),
                ("product_id", "=", product.id),
            ]
        )

        return self.env["ps.planning.wizard.line"].create(
            dict(
                {
                    "wizard_id": self.id,
                    "y_axis": "%10d-%10d-1-%s"
                    % (task.id, product.id, employee.display_name),
                    "y_axis_display": "",
                    "range_id": month.id,
                    "task_id": task.id,
                    "product_id": product.id,
                    "employee_id": employee.id,
                    "days": planning_line.days,
                    "line_type": "planned",
                    "state": planning_line.state or "draft",
                    "planning_line_id": planning_line.id,
                    "contracted_line_id": contracted_line.id,
                },
                **extra_vals
            )
        )

    def action_start_planning(self):
        PsPlanningLine = self.env["ps.planning.line"]
        months = self._get_months()
        employees = self.env["hr.employee"].search([])
        self.line_ids.unlink()

        for contracted_line in self.contracted_line_ids:
            task = contracted_line.task_id
            product = contracted_line.product_id
            contracted_days_by_month = contracted_line._get_contracted_days_by_month()
            for date_range in months:
                planning_line = PsPlanningLine.search(
                    [
                        ("range_id", "=", date_range.id),
                        ("task_id", "=", task.id),
                        ("product_id", "=", product.id),
                        ("line_type", "=", "contracted"),
                    ],
                )
                self._add_line(
                    date_range,
                    task,
                    product,
                    self.env["hr.employee"],
                    y_axis="%10d-%10d-0" % (task.id, product.id),
                    days=contracted_days_by_month[date_range]
                    if not planning_line
                    else planning_line.days,
                    planning_line_id=planning_line.id,
                    line_type="contracted",
                )
                for employee in employees:
                    if not PsPlanningLine.search_count(
                        [
                            ("task_id", "=", task.id),
                            ("product_id", "=", product.id),
                            ("line_type", "=", "planned"),
                            ("employee_id", "=", employee.id),
                        ],
                    ):
                        continue
                    self._add_line(date_range, task, product, employee)

        action = self.env["ir.actions.actions"]._for_xml_id(
            "ps_planning.action_ps_planning_wizard"
        )
        action["res_id"] = self.id
        return action

    def action_commit_planning(self):
        for line in self.line_ids:
            if line.planning_line_id:
                line.planning_line_id.write({"days": line.days, "state": line.state})
            else:
                line.planning_line_id = line.planning_line_id.create(
                    {
                        "days": line.days,
                        "employee_id": line.employee_id.id,
                        "task_id": line.task_id.id,
                        "range_id": line.range_id.id,
                        "product_id": line.product_id.id,
                        "line_type": line.line_type,
                        "state": line.state,
                        "contracted_line_id": line.contracted_line_id.id,
                    }
                )
        self.action_start_planning()

    def _get_months(self, period=None):
        month_type = self.env.ref("account_fiscal_month.date_range_fiscal_month")
        period = period or self.period_id
        return self.env["date.range"].search(
            [
                ("date_end", ">", period.date_start),
                ("date_start", "<", period.date_end),
                ("type_id", "=", month_type.id),
            ]
        )


class PsPlanningWizardLine(models.TransientModel):
    _name = "ps.planning.wizard.line"
    _description = "PS planning wizard line"
    _order = "y_axis, range_id"

    wizard_id = fields.Many2one("ps.planning.wizard", required=True)
    y_axis = fields.Char()
    y_axis_display = fields.Char()
    range_id = fields.Many2one("date.range")
    days = fields.Float()
    planning_line_id = fields.Many2one("ps.planning.line")
    contracted_line_id = fields.Many2one("ps.contracted.line")
    line_type = fields.Char()
    state = fields.Char()
    task_id = fields.Many2one("project.task")
    product_id = fields.Many2one("product.product")
    employee_id = fields.Many2one("hr.employee")
    daily_rate = fields.Monetary(related="contracted_line_id.rate")
    currency_id = fields.Many2one(related="contracted_line_id.currency_id")
    contracted_days = fields.Float(related="contracted_line_id.days")
    disabled = fields.Boolean(compute="_compute_disabled")

    @api.depends("state", "line_type")
    def _compute_disabled(self):
        for this in self:
            this.disabled = this.line_type == "planned" and this.state == "final"
