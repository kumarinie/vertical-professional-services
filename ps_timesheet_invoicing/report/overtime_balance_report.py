from odoo import fields, models, tools


class OvertimeBalanceReport(models.Model):
    _name = "overtime.balance.report"
    _auto = False
    _description = "Overtime Balance Report"

    date = fields.Date("Date", readonly=True)
    user_id = fields.Many2one("res.users", string="User", readonly=True)
    overtime_balanced = fields.Float(string="Overtime Balance", readonly=True)
    overtime_taken = fields.Float(string="Overtime Taken", readonly=True)
    overtime_hrs = fields.Float(string="Overtime Hrs", readonly=True)

    # @api.model_cr
    def init(self):
        tools.drop_view_if_exists(self.env.cr, "overtime_balance_report")

        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW overtime_balance_report AS (
            SELECT
                min(ptl.id) AS id,
                ptl.date AS date,
                ptl.user_id AS user_id,
                SUM(CASE
                    WHEN pp.overtime
                    AND product_uom_id = %(uom)s
                    THEN ptl.unit_amount
                    ELSE 0
                    END) AS overtime_taken,
                SUM(CASE
                    WHEN pp.overtime_hrs
                    AND product_uom_id = %(uom)s
                    THEN ptl.unit_amount
                    ELSE 0
                    END) AS overtime_hrs,
                (
                  SUM(CASE
                    WHEN pp.overtime_hrs
                    AND product_uom_id = %(uom)s
                    THEN ptl.unit_amount
                    ELSE 0
                    END) -
                  SUM(CASE
                    WHEN pp.overtime
                    AND product_uom_id = %(uom)s
                    THEN ptl.unit_amount
                    ELSE 0
                    END)
                ) AS overtime_balanced
            FROM ps_time_line ptl
            JOIN account_analytic_account aa ON aa.id = ptl.account_id
            JOIN project_project pp ON pp.analytic_account_id = aa.id
            WHERE pp.overtime = true OR pp.overtime_hrs = true
            GROUP BY ptl.date, ptl.user_id
            )""",
            {"uom": self.env.ref("uom.product_uom_hour").id},
        )
