# Copyright 2018 - 2023 The Open Source Company ((www.tosc.nl).)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import json
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Lead(models.Model):
    _inherit = "crm.lead"

    @api.constrains("start_date", "end_date")
    def _check_dates(self):
        start_date = self.start_date
        end_date = self.end_date
        if (start_date and end_date) and (start_date > end_date):
            raise ValidationError(_("End date should be greater than start date."))

    @api.depends("operating_unit_id")
    def _compute_dept_ou_domain(self):
        """
        Compute the domain for the department domain.
        """
        department_ids = []
        if self.operating_unit_id:
            self.env.cr.execute(
                """
                            SELECT id
                            FROM hr_department
                            WHERE operating_unit_id = %s
                            AND parent_id IS NULL
                            """,
                (self.operating_unit_id.id,),
            )

            result = self.env.cr.fetchall()
            for res in result:
                department_id = res[0]
                self.env.cr.execute(
                    """
                    WITH RECURSIVE
                        subordinates AS(
                            SELECT id, parent_id  FROM hr_department WHERE id = %s
                            UNION
                            SELECT h.id, h.parent_id FROM hr_department h
                            INNER JOIN subordinates s ON s.id = h.parent_id)
                        SELECT  *  FROM subordinates""",
                    (department_id,),
                )
                result2 = self.env.cr.fetchall()
                for res2 in result2:
                    department_ids.append(res2[0])
        self.dept_ou_domain = json.dumps([("id", "in", department_ids)])

    start_date = fields.Date("Start Date")
    end_date = fields.Date("End Date")
    project_id = fields.Many2one("project.project", string="Project")
    subject = fields.Char("Subject")
    operating_unit_id = fields.Many2one(
        "operating.unit", string="Operating Unit", required=True
    )
    contract_signed = fields.Boolean(string="Contract Signed")
    department_id = fields.Many2one("hr.department", string="Practice")
    expected_duration = fields.Integer(string="Expected Duration")
    monthly_revenue_ids = fields.One2many(
        "crm.monthly.revenue", "lead_id", string="Monthly Revenue"
    )
    show_button = fields.Boolean(string="Show button")
    latest_revenue_date = fields.Date("Latest Revenue Date")
    partner_contact_id = fields.Many2one("res.partner", string="Contact Person")
    revenue_split_ids = fields.One2many(
        "crm.revenue.split", "lead_id", string="Revenue"
    )
    dept_ou_domain = fields.Char(
        compute=_compute_dept_ou_domain,
        readonly=True,
        store=False,
    )

    @api.model
    def _onchange_stage_id_values(self, stage_id):
        """returns the new values when stage_id has changed"""
        res = super()._onchange_stage_id_values(stage_id)
        for rec in self.monthly_revenue_ids:
            rec.update({"percentage": res.get("probability")})
        if self.stage_id.show_when_chaing:
            if self.stage_id.requirements:
                text = self.stage_id.requirements
                result = text.split("\n")
                if result:
                    final_string = ""
                    for str_val in result:
                        final_string += str_val + "</br>"
                    text = final_string
                self.env.user.notify_info(message=text, sticky=True)
        return res

    @api.depends("operating_unit_id")
    @api.onchange("operating_unit_id")
    def onchange_operating_unit_id(self):
        for rec in self.revenue_split_ids:
            rec.ps_blue_bv_per = 0.0
            rec.ps_blue_bv_amount = 0.0
            rec.ps_red_bv_amount = 0.0
            rec.ps_red_bv_per = 0.0
            rec.ps_green_bv_per = 0.0
            rec.ps_green_bv_amount = 0.0
            rec.ps_black_bv_per = 0.0
            rec.ps_black_bv_amount = 0.0
            if self.operating_unit_id.name == "Magnus Blue B.V.":
                rec.ps_blue_bv_per = 100
                rec.ps_blue_bv_amount = rec.total_revenue
            if self.operating_unit_id.name == "Magnus Red B.V.":
                rec.ps_red_bv_amount = rec.total_revenue
                rec.ps_red_bv_per = 100
            if self.operating_unit_id.name == "Magnus Green B.V.":
                rec.ps_green_bv_per = 100
                rec.ps_green_bv_amount = rec.total_revenue
            if self.operating_unit_id.name == "Magnus Black B.V.":
                rec.ps_black_bv_per = 100
                rec.ps_black_bv_amount = rec.total_revenue

    @api.model
    def default_get(self, fields):
        res = super(Lead, self).default_get(fields)
        context = self._context
        current_uid = context.get("uid")
        user = self.env["res.users"].browse(current_uid)
        res.update({"operating_unit_id": user.default_operating_unit_id.id})
        return res

    @api.model
    def create(self, vals):
        res = super(Lead, self).create(vals)
        monthly_revenue_ids = res.monthly_revenue_ids.filtered("date")
        if monthly_revenue_ids:
            res.write(
                {"latest_revenue_date": monthly_revenue_ids.sorted("date")[-1].date}
            )
        return res

    @api.onchange("monthly_revenue_ids")
    def onchange_monthly_revenue_ids(self):
        if round(sum(self.monthly_revenue_ids.mapped("expected_revenue")), 2) != round(
            self.prorated_revenue, 2
        ):
            self.show_button = True
        else:
            self.show_button = False

    def update_monthly_revenue(self):
        self.ensure_one()
        manual_lines = []
        sd = self.start_date
        ed = self.end_date
        if sd and ed:
            sd = datetime.strptime(sd, "%Y-%m-%d").date()
            ed = datetime.strptime(ed, "%Y-%m-%d").date()

            for line in self.monthly_revenue_ids.filtered(
                lambda l: not l.computed_line
            ):
                manual_lines.append((4, line.id))

            month_end_date = (sd + relativedelta(months=1)).replace(day=1) - timedelta(
                days=1
            )
            if month_end_date > ed:
                month_end_date = ed
            monthly_revenues = []
            monthly_revenues_split = []
            total_days = (ed - sd).days + 1
            date_range = self.env["date.range"]
            company = self.company_id.id or self.env.user.company_id.id

            while True:
                common_domain = [
                    ("date_start", "<=", month_end_date),
                    ("date_end", ">=", month_end_date),
                    ("company_id", "=", company),
                ]
                month = date_range.search(
                    common_domain + [("type_id.fiscal_month", "=", True)]
                )
                year = date_range.search(
                    common_domain + [("type_id.fiscal_year", "=", True)]
                )
                days_per_month = (month_end_date - sd).days + 1
                expected_revenue_per_month = (
                    self.prorated_revenue * days_per_month / total_days
                )
                weighted_revenue_per_month = (
                    (float(days_per_month) / float(total_days)) * self.prorated_revenue
                ) * (self.probability / 100)
                days = " days (" if days_per_month > 1 else " day ("
                duration = (
                    str(days_per_month)
                    + days
                    + str(sd.day)
                    + "-"
                    + str(month_end_date.day)
                    + " "
                    + str(sd.strftime("%B"))
                    + ")"
                )
                monthly_revenues.append(
                    (
                        0,
                        0,
                        {
                            "date": month_end_date,
                            "latest_revenue_date": month_end_date.replace(day=1)
                            - timedelta(days=1),
                            "year": year.id,
                            "month": month.id,
                            "no_of_days": duration,
                            "weighted_revenue": weighted_revenue_per_month,
                            "expected_revenue": expected_revenue_per_month,
                            "computed_line": True,
                            "percentage": self.probability,
                        },
                    )
                )

                blue_per = 0.0
                red_per = 0.0
                green_per = 0.0
                black_per = 0.0
                ps_blue_bv_amount = 0.0
                ps_red_bv_amount = 0.0
                ps_green_bv_amount = 0.0
                ps_black_bv_amount = 0.0
                if self.operating_unit_id.name == "Magnus Blue B.V.":
                    blue_per = 100
                    ps_blue_bv_amount = expected_revenue_per_month
                if self.operating_unit_id.name == "Magnus Red B.V.":
                    red_per = 100
                    ps_red_bv_amount = expected_revenue_per_month
                if self.operating_unit_id.name == "Magnus Green B.V.":
                    green_per = 100
                    ps_green_bv_amount = expected_revenue_per_month
                if self.operating_unit_id.name == "Magnus Black B.V.":
                    black_per = 100
                    ps_black_bv_amount = expected_revenue_per_month

                monthly_revenues_split.append(
                    (
                        0,
                        0,
                        {
                            "month": month.id,
                            "total_revenue": expected_revenue_per_month,
                            "total_revenue_per": 100,
                            "ps_blue_bv_per": blue_per,
                            "ps_red_bv_per": red_per,
                            "ps_black_bv_per": black_per,
                            "ps_green_bv_per": green_per,
                            "ps_blue_bv_amount": ps_blue_bv_amount,
                            "ps_red_bv_amount": ps_red_bv_amount,
                            "ps_green_bv_amount": ps_green_bv_amount,
                            "ps_black_bv_amount": ps_black_bv_amount,
                        },
                    )
                )
                sd = month_end_date + timedelta(days=1)
                month_end_date = (sd + relativedelta(months=1)).replace(
                    day=1
                ) - timedelta(days=1)
                if sd > ed:
                    break
                if month_end_date > ed:
                    month_end_date = ed
            self.monthly_revenue_ids = monthly_revenues + manual_lines
            self.revenue_split_ids = monthly_revenues_split

    def recalculate_total(self):
        self.ensure_one()
        if round(sum(self.monthly_revenue_ids.mapped("expected_revenue")), 2) != round(
            self.prorated_revenue, 2
        ):
            self.prorated_revenue = round(
                sum(self.monthly_revenue_ids.mapped("expected_revenue")), 2
            )
            self.show_button = False

    @api.onchange("start_date", "end_date", "prorated_revenue", "probability")
    def onchange_date(self):
        if (
            self.start_date
            and not self._origin.end_date
            and self.start_date > self.end_date
        ):
            self.end_date = self.start_date
        self.update_monthly_revenue()

    @api.onchange("partner_id")
    def onchange_partner(self):
        values = {}
        if not self.partner_id:
            return values

        part = self.partner_id
        addr = self.partner_id.address_get(["delivery", "invoice", "contact"])

        if part.type == "contact":
            contact = self.env["res.partner"].search(
                [
                    ("is_company", "=", False),
                    ("type", "=", "contact"),
                    ("parent_id", "=", part.id),
                ]
            )
            if len(contact) >= 1:
                contact_id = contact[0]
            else:
                contact_id = False
        elif addr["contact"] == addr["default"]:
            contact_id = False
        else:
            contact_id = addr["contact"]

        values.update({"partner_contact_id": contact_id, "partner_name": part.name})

        if part.industry_id:
            values.update(
                {
                    "industry_id": part.industry_id,
                    "secondary_industry_ids": [(6, 0, part.secondary_industry_ids.ids)],
                }
            )
        else:
            values.update(
                {
                    "industry_id": False,
                    "secondary_industry_ids": False,
                }
            )
        return {"value": values}

    @api.onchange("partner_contact_id")
    def onchange_contact(self):
        if self.partner_contact_id:
            partner = self.partner_contact_id
            values = {
                "contact_name": partner.name,
                "title": partner.title.id,
                "email_from": partner.email,
                "phone": partner.phone,
                "mobile": partner.mobile,
                "function": partner.function,
            }
        else:
            values = {
                "contact_name": False,
                "title": False,
                "email_from": False,
                "phone": False,
                "mobile": False,
                "function": False,
            }
        return {"value": values}
