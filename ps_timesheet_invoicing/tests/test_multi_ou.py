from odoo.tests.common import Form, TransactionCase


class TestMultiOU(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env.company.write(
            {
                "ou_is_self_balanced": True,
                "inter_ou_clearing_account_id": self.env["account.account"]
                .search([], limit=1)
                .id,
            }
        )
        self.project = self.env.ref("project.project_project_2")
        self.ou1 = self.env.ref("operating_unit.main_operating_unit")
        self.ou2 = self.env.ref("operating_unit.b2b_operating_unit")
        template_user = self.env.ref("base.user_demo")
        self.user_ou1 = template_user.copy(
            {
                "login": "user_ou1",
                "default_operating_unit_id": self.ou1.id,
                "operating_unit_ids": self.ou1.ids,
            }
        )
        self.user_ou2 = template_user.copy(
            {
                "login": "user_ou2",
                "default_operating_unit_id": self.ou2.id,
                "operating_unit_ids": self.ou2.ids,
            }
        )
        self.department_ou1 = self.env["hr.department"].create(
            {
                "name": "ou1",
                "operating_unit_id": self.ou1.id,
            }
        )
        self.department_ou2 = self.env["hr.department"].create(
            {
                "name": "ou2",
                "operating_unit_id": self.ou2.id,
            }
        )
        self.employee_ou1 = template_user.employee_ids.copy(
            {
                "user_id": self.user_ou1.id,
                "department_id": self.department_ou1.id,
            }
        )
        self.employee_ou2 = template_user.employee_ids.copy(
            {
                "user_id": self.user_ou2.id,
                "department_id": self.department_ou2.id,
            }
        )
        template_line = self.env.ref(
            "ps_timesheet_invoicing.time_line_demo_user_2023_12_18"
        )
        self.time_line_ou1 = template_line.copy(
            {
                "user_id": self.user_ou1.id,
                "state": "open",
            }
        )
        self.time_line_ou2 = template_line.copy(
            {
                "user_id": self.user_ou2.id,
                "state": "open",
            }
        )

    def test_multi_ou(self):
        """
        Test that users with different OUs cause different OUs on invoice lines
        """
        lines = self.time_line_ou1 + self.time_line_ou2
        wizard = (
            self.env["time.line.status"]
            .with_context(
                active_id=lines[:1].id,
                active_ids=lines.ids,
                active_model=lines._name,
            )
            .create({"name": "invoiceable"})
        )
        wizard.ps_invoice_lines()
        ps_invoice = self.env["ps.invoice"].search(
            [("user_total_ids.detail_ids", "in", lines.ids)]
        )
        ps_invoice.generate_invoice()
        ps_invoice.invoice_id.action_post()
        self.assertEqual(ps_invoice.operating_unit_id, self.ou1)
        self.assertItemsEqual(
            ps_invoice.line_ids.operating_unit_id,
            self.ou1 + self.ou2,
        )

    def test_onchange(self):
        """
        Test that onchange functions in invoices don't mess with OUs
        """
        invoice = (
            self.env["account.move"]
            .with_context(default_move_type="out_invoice")
            .create(
                {
                    "partner_id": self.project.partner_id.id,
                    "operating_unit_id": self.ou1.id,
                }
            )
        )
        with Form(invoice) as invoice_form:
            with invoice_form.invoice_line_ids.new() as line_form:
                line_form.user_id = self.user_ou2
                self.assertEqual(line_form.operating_unit_id, self.ou2)
                line_form.name = "test ou"
        self.assertEqual(invoice.invoice_line_ids.operating_unit_id, self.ou2)
