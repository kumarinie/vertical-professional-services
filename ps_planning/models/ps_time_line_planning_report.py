# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

from psycopg2.extensions import AsIs

from odoo import _, fields, models, tools


class PsTimeLinePlanningReport(models.Model):
    _name = "ps.time.line.planning.report"
    _inherit = "ps.planning.department.mixin"
    _description = "Activity Analysis (Contracted / Planned / Actual)"
    _auto = False

    project_id = fields.Many2one("project.project")
    task_id = fields.Many2one("project.task")
    employee_id = fields.Many2one("hr.employee")
    date = fields.Date()
    days_actual = fields.Float()
    days_planned = fields.Float()
    days_contracted = fields.Float()
    rate = fields.Float(group_operator="max")

    def init(self):
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(
            """
            CREATE view %s as
            SELECT
                id,
                project_id,
                task_id,
                employee_id,
                date,
                unit_amount / 8 as days_actual,
                0 as days_planned,
                0 as days_contracted,
                0 as rate
            FROM ps_time_line
            UNION (
            WITH
            xmlid_month_range AS (
                SELECT res_id FROM ir_model_data
                WHERE module='account_fiscal_month' AND name='date_range_fiscal_month'
            ),
            month_days AS (
                SELECT generate_series(date_start, date_end, '1day')::date month_day,
                date_range.id range_id FROM date_range, xmlid_month_range
                WHERE date_range.type_id=xmlid_month_range.res_id
            ),
            work_days AS (
                SELECT month_day, range_id FROM month_days
                WHERE extract(isodow from month_day) < 6
            ),
            work_day_count AS (
                SELECT count(month_day) work_days, range_id FROM work_days GROUP BY range_id
            )
            SELECT
                ps_planning_line.id,
                ps_planning_line.project_id,
                ps_planning_line.task_id,
                employee_id,
                work_days.month_day,
                0 as days_actual,
                0 as days_planned,
                ps_planning_line.days / work_day_count.work_days as days_contracted,
                ps_contracted_line.rate as rate
            FROM ps_planning_line, ps_contracted_line, work_days, work_day_count
            WHERE
            ps_planning_line.contracted_line_id=ps_contracted_line.id
            AND
            ps_planning_line.range_id=work_days.range_id
            AND
            ps_planning_line.range_id=work_day_count.range_id
            AND
            ps_planning_line.line_type='contracted'
            UNION
            SELECT
                ps_planning_line.id,
                ps_planning_line.project_id,
                ps_planning_line.task_id,
                employee_id,
                work_days.month_day,
                0 as days_actual,
                ps_planning_line.days / work_day_count.work_days as days_planned,
                0 as days_contracted,
                ps_contracted_line.rate as rate
            FROM ps_planning_line, ps_contracted_line, work_days, work_day_count
            WHERE
            ps_planning_line.contracted_line_id=ps_contracted_line.id
            AND
            ps_planning_line.range_id=work_days.range_id
            AND
            ps_planning_line.range_id=work_day_count.range_id
            AND
            ps_planning_line.line_type='planned'
            )
        """,
            (AsIs(self._table),),
        )

    def _read_group_resolve_many2one_fields(self, data, fields):
        result = super()._read_group_resolve_many2one_fields(data, fields)
        for record in data:
            if record.get("employee_id") is False:
                record["employee_id"] = (0, _("Contracted"))
        return result
