# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

{
    "name": "PS planning",
    "summary": "Planning tool for professional services",
    "version": "14.0.1.0.1",
    "development_status": "Alpha",
    "category": "Planning",
    "website": "http://www.tosc.nl",
    "author": "Hunki Enterprises BV,The Open Source Company,Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "depends": [
        "ps_timesheet_invoicing",
        "project_department",
    ],
    "data": [
        "data/date_range_type.xml",
        "security/ps_planning.xml",
        "security/ir.model.access.csv",
        "views/project_project.xml",
        "views/ps_contracted_line.xml",
        "views/ps_planning_line.xml",
        "views/ps_planning_billing_report.xml",
        "views/ps_time_line_planning_report.xml",
        "views/templates.xml",
        "wizards/ps_planning_wizard.xml",
        "wizards/ps_planning_report_wizard.xml",
        "wizards/ps_contracting_wizard.xml",
        "views/menu.xml",
    ],
    "demo": [
        "demo/project_project.xml",
        "demo/project_task.xml",
        "demo/product_product.xml",
    ],
}
