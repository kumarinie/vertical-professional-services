from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import Form, TransactionCase


class TestPsPlanning(TransactionCase):
    def setUp(self):
        super().setUp()
        self.project = self.env.ref("ps_planning.planning_project")
        self.task1 = self.env.ref("ps_planning.planning_task1")
        self.task2 = self.env.ref("ps_planning.planning_task2")
        self.product1 = self.env.ref("ps_planning.planning_product1")
        self.product2 = self.env.ref("ps_planning.planning_product2")
        self.employee = self.env.ref("hr.employee_qdp")

    def test_contract_lines(self):
        wizard = self.env["ps.contracting.wizard"].create(
            {
                "project_id": self.project.id,
                "product_ids": [(6, 0, (self.product1 + self.product2).ids)],
                "date_from": "2024-01-01",
                "date_to": "2024-05-31",
            }
        )
        action = wizard.action_open_ps_contracted_lines()
        contracted_lines = self.env[action["res_model"]].search(action["domain"])

        self.assertEqual(len(contracted_lines), 4)

        action2 = wizard.action_open_ps_contracted_lines()
        contracted_lines2 = self.env[action2["res_model"]].search(action2["domain"])

        self.assertEqual(contracted_lines, contracted_lines2)

        product1_task1_line = contracted_lines.filtered(
            lambda x: x.product_id == self.product1 and x.task_id == self.task1
        )
        self.assertTrue(product1_task1_line)

        product1_task1_line.date_from = "2024-01-01"
        product1_task1_line.date_to = "2024-05-31"

        with self.assertRaisesRegex(
            ValidationError, "must be unique"
        ), self.env.cr.savepoint():
            product1_task1_line.copy()

        with self.assertRaisesRegex(
            ValidationError, "overlapping"
        ), self.env.cr.savepoint():
            product1_task1_line.copy(
                {"date_from": "2024-01-01", "date_to": "2024-04-30"}
            )

        with Form(product1_task1_line) as line_form:
            line_form.days = 420
            line_form.rate = 100

        self.assertTrue(product1_task1_line.value)

    def test_planning_lines(self):
        self.test_contract_lines()
        wizard = self.env["ps.planning.wizard"].create(
            {
                "project_id": self.project.id,
                "period_id": self.project.ps_contracted_line_ids.range_id.id,
            }
        )
        wizard.action_start_planning()
        wizard.write(
            {
                "add_line_task_id": self.task1.id,
                "add_line_product_id": self.product1.id,
                "add_line_employee_id": self.employee.id,
            }
        )
        wizard.action_add_line()
        product1_task1_wizard_line1 = wizard.line_ids.filtered(
            lambda x: x.line_type == "planned"
            and x.task_id == self.task1
            and x.product_id == self.product1
            and x.employee_id == self.employee
        )[:1]
        self.assertEqual(len(product1_task1_wizard_line1), 1)
        product1_task1_wizard_line1.days = 42
        wizard.action_commit_planning()
        # commit rebuilds lines
        product1_task1_wizard_line1 = wizard.line_ids.filtered(
            lambda x: x.line_type == "planned"
            and x.task_id == self.task1
            and x.product_id == self.product1
            and x.employee_id == self.employee
        )[:1]
        product1_task1_planning_line1 = product1_task1_wizard_line1.planning_line_id
        self.assertEqual(product1_task1_planning_line1.days, 42)

    def test_change_contracted_lines(self):
        self.test_contract_lines()
        self.test_planning_lines()

        planned_line = self.project.ps_contracted_line_ids.planning_line_ids.filtered(
            lambda x: x.line_type == "planned"
        )
        self.assertEqual(len(planned_line), 5)
        contracted_line = planned_line.contracted_line_id

        self.project.ps_contracted_line_ids.filtered(
            lambda x: x.task_id == self.task2
        ).unlink()

        contracted_line.task_id = self.task2
        self.assertEqual(planned_line.task_id, self.task2)
        contracted_line.product_id = self.product2
        self.assertEqual(planned_line.product_id, self.product2)

        with self.assertRaisesRegex(
            UserError, "out of the new contract period"
        ), self.env.cr.savepoint():
            contracted_line.date_from = "2024-02-01"

        planned_line.unlink()
        contracted_line.date_from = "2024-02-01"

    def test_reports(self):
        self.test_contract_lines()
        self.test_planning_lines()
        wizard = self.env["ps.planning.report.wizard"].create({})
        wizard.action_open_report()
        # TODO assert things

        self.env["ps.planning.billing.report"].search([])
        # TODO assert things

        self.env["ps.time.line.planning.report"].search([])
        # TODO assert things
