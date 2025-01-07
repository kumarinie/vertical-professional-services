def migrate(cr, version=None):
    cr.execute(
        "alter table ps_planning_report_wizard_line drop column budget_utilization"
    )
