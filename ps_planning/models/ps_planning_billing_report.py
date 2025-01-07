# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

from psycopg2.extensions import AsIs

from odoo import fields, models, tools


class PsPlanningBillingReport(models.Model):
    _name = "ps.planning.billing.report"
    _inherit = "ps.planning.department.mixin"
    _description = "Billing report"
    _order = "project_id, range_id"
    _auto = False

    project_id = fields.Many2one("project.project")
    project_user_id = fields.Many2one("res.users")
    project_partner_id = fields.Many2one("res.partner")
    range_id = fields.Many2one("date.range", string="Period")
    contracted_days = fields.Float()
    contracted_value = fields.Float()
    planned_days = fields.Float()
    planned_value = fields.Float()
    actual_days = fields.Float()
    actual_value = fields.Float()
    billed_days = fields.Float()
    billed_value = fields.Float()

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(
            """
            CREATE view %s as
                WITH xmlids AS (
                    SELECT (
                        SELECT res_id from ir_model_data
                        WHERE module='uom' and name='product_uom_hour'
                    ) as product_uom_hour, (
                        SELECT res_id from ir_model_data
                        WHERE module='uom' and name='product_uom_unit'
                    ) as product_uom_unit
                )
                SELECT
                min(ps_planning_line_planned.id) as id,
                ps_contracted_line.project_id,
                ps_planning_line_planned.range_id,
                max(project_project.partner_id) as project_partner_id,
                max(project_project.user_id) as project_user_id,
                (
                    select sum(days)
                    from ps_planning_line
                    where line_type='contracted'
                    and project_id=ps_contracted_line.project_id
                    and range_id=ps_planning_line_planned.range_id
                ) as contracted_days,
                (
                    select sum(ps_planning_line.days * (
                        ps_contracted_line_inner.value /
                        ps_contracted_line_inner.days
                    ))
                    from ps_planning_line
                    join ps_contracted_line ps_contracted_line_inner
                    on ps_planning_line.contracted_line_id=ps_contracted_line_inner.id
                    where ps_planning_line.line_type='contracted'
                    and ps_planning_line.project_id=ps_contracted_line.project_id
                    and ps_planning_line.range_id=ps_planning_line_planned.range_id
                    and ps_contracted_line_inner.days <> 0
                ) as contracted_value,
                sum(ps_planning_line_planned.days) as planned_days,
                sum(
                    ps_planning_line_planned.days * ps_contracted_line.rate
                ) as planned_value,
                (
                    select sum(unit_amount) / 8
                    from ps_time_line
                    where
                    product_uom_id=(select product_uom_hour from xmlids)
                    and project_id=ps_contracted_line.project_id
                    and date >= date_range.date_start
                    and date <= date_range.date_end
                ) as actual_days,
                -(
                    select sum(amount)
                    from ps_time_line
                    where
                    product_uom_id=(select product_uom_hour from xmlids)
                    and project_id=ps_contracted_line.project_id
                    and date >= date_range.date_start
                    and date <= date_range.date_end
                ) as actual_value,
                CASE
                WHEN project_invoicing_properties.actual_time_spent THEN (
                    select sum(quantity) / 8
                    from account_move_line aml
                    join ps_invoice psi on aml.ps_invoice_id=psi.id
                    where
                    aml.analytic_account_id=project_project.analytic_account_id
                    and aml.product_uom_id=(select product_uom_hour from xmlids)
                    and psi.period_id=ps_planning_line_planned.range_id
                )
                WHEN project_invoicing_properties.fixed_amount THEN (
                    select sum(days)
                    from ps_planning_line
                    where line_type='contracted'
                    and project_id=ps_contracted_line.project_id
                    and range_id=ps_planning_line_planned.range_id
                )
                ELSE 0
                END as billed_days,
                (
                    select sum(aml.price_total)
                    from account_move_line aml
                    join ps_invoice psi on aml.ps_invoice_id=psi.id
                    where
                    aml.analytic_account_id=project_project.analytic_account_id
                    and aml.product_uom_id=(
                        CASE
                        WHEN project_invoicing_properties.actual_time_spent THEN (
                            select product_uom_hour from xmlids
                        )
                        WHEN project_invoicing_properties.fixed_amount THEN (
                            select product_uom_unit from xmlids
                        )
                        END
                    )
                    and psi.period_id=ps_planning_line_planned.range_id
                ) as billed_value
                FROM
                ps_contracted_line
                JOIN
                ps_planning_line ps_planning_line_planned
                ON ps_planning_line_planned.contracted_line_id=ps_contracted_line.id
                AND ps_planning_line_planned.line_type='planned'
                JOIN
                project_project
                ON ps_contracted_line.project_id=project_project.id
                JOIN
                account_analytic_account
                ON project_project.analytic_account_id=account_analytic_account.id
                JOIN
                project_invoicing_properties
                ON project_project.invoice_properties=project_invoicing_properties.id
                JOIN
                date_range
                ON ps_planning_line_planned.range_id=date_range.id
                GROUP BY
                ps_contracted_line.project_id,
                ps_planning_line_planned.range_id,
                date_range.date_start,
                date_range.date_end,
                project_invoicing_properties.actual_time_spent,
                project_invoicing_properties.fixed_amount,
                project_project.analytic_account_id
        """,
            (AsIs(self._table),),
        )
