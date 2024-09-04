{
    "name": "PS expenses",
    "summary": "Adjustments to Expense Module",
    "author": "The Open Source Company",
    "website": "http://www.tosc.nl",
    "license": "AGPL-3",
    "category": "Human Resources",
    "version": "16.0.1.0.0",
    "depends": [
        "hr_expense",
        "hr_expense_operating_unit",
        # TODO migrate
        # "invoice_line_revenue_distribution_operating_unit",
        "sale_expense",
    ],
    "data": [
        "security/ir_rule.xml",
        "security/ps_expense.xml",
        "views/hr_expense.xml",
        "views/hr_expense_sheet.xml",
        "views/res_company_view.xml",
        "views/account_analytic_account.xml",
        "views/account_analytic_line.xml",
    ],
    "demo": [
        "demo/res_company.xml",
    ],
    "installable": True,
}
