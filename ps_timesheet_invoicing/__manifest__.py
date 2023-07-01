# -*- coding: utf-8 -*-
# Copyright 2014-2023 The Open Source Company (www.tosc.nl).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
{
    'name': 'Timesheet and Invoicing',

    'summary': """This module introduces an advanced professional services invoicing process,
        offering fixed price, time and material, licensing and several combinations
         thereof""",

    'description': """
        Record and validate timesheets, invoice captured time - extended
==============================================================================

The extended timesheet validation process is:
--------------------------------------------------
* Timesheet period is set to weeks (from Monday to Sunday).
* Each week day (Monday-Friday) needs to have at least 8 logged hours.
* Each Monday-Friday period needs to have at least 40 logged hours.
* Logged hours should be 0 - 24.

The extended date range validation process is:
--------------------------------------------------
* Name is prepended with year generated according to ISO 8601 Calendar.
* Name is appended with week number generated according to ISO 8601 Calendar.
* Note: Start date should be Monday while generating weekly date ranges for timesheet. Also a date range must be unique per company

The advanced professional services invoicing process, offering fixed price, time and material, licensing and several combinations
thereof""",

    'author': "The Open Source Company",
    'website': "http://www.tosc.nl",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/master/odoo/addons/base/module/module_data.xml
    # for the full list
    'category': 'module_category_specific_industry_applications',
    'version': '2.0',

    # any module necessary for this one to work correctly
    'depends': ['account',
                'analytic',
                'uom',
                'hr',
                'hr_timesheet_task_required',
                'fleet',
                'ps_hr',
                'ps_crm',
                'data_time_tracker',
                'ps_date_range_week',
                'uom_unece',
                'ps_project',
                'web_m2x_options',
                # 'web_readonly_bypass', its full of JS files, so as of now the module is not installed and is commented
                'sale_timesheet',
                'analytic_base_department',
                'account_fiscal_month',
                'account_fiscal_year',
                'hr_timesheet_sheet_validators',
                # 'connector_jira',
                # 'web_domain_field', its full of JS files, so as of now the module is not installed and is commented
                'invoice_line_revenue_distribution_operating_unit',
                'queue_job'
                ],

    # always loaded
    'data': [
        'data/cron_data.xml',
        'data/data.xml',
        'security/ps_security.xml',
        'security/ir.model.access.csv',
        'wizard/analytic_line_invoice_view.xml',
        'wizard/change_chargecode_view.xml',
        'wizard/planning_wizard_view.xml',
        'report/hr_chargeability_report.xml',
        'report/status_time_report.xml',
        'report/overtime_balance_report.xml',
        'report/crm_pipeline_actuals_report.xml',
        'views/hr_timesheet_view.xml',
        'views/project_timesheet_view.xml',
        'views/project_view.xml',
        # 'views/hr_timesheet_assets.xml',
        'views/hr_view.xml',
        'views/analytic_view.xml',
        'views/fleet_view.xml',
        'views/ps_planning_views.xml',
        'views/analytic_invoice.xml',
        'views/product_view.xml',
        'views/account_move_view.xml',
        'views/invoice_view.xml',
        'views/inter_ou_account_mapping_view.xml',
        'views/menu_item.xml',
        'views/res_company_view.xml',
    ],
    'installable': True,
    # only loaded in demonstration mode
    'demo' : [],
    'qweb': ['static/src/xml/planning.xml',],
}