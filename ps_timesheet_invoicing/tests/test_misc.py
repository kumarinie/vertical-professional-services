from odoo.exceptions import ValidationError
from odoo.tests.common import Form, TransactionCase
from odoo.tools.misc import mute_logger


class TestMisc(TransactionCase):
    def setUp(self):
        super().setUp()
        self.project = self.env.ref("project.project_project_2")
        self.ps_line = self.env.ref(
            "ps_timesheet_invoicing.time_line_demo_user_2023_12_18"
        )
        self.ps_line_mileage = self.env.ref(
            "ps_timesheet_invoicing.time_line_demo_user_2023_12_18_mileage"
        )

    def test_change_chargecode(self):
        wizard = (
            self.env["change.chargecode"]
            .with_context(
                active_id=self.ps_line.id,
                active_ids=self.ps_line.ids,
                active_model=self.ps_line._name,
            )
            .create({})
        )
        with Form(wizard) as wizard_form:
            project = self.env["project.project"].search(
                [("id", "!=", self.ps_line.project_id.id)],
                limit=1,
            )
            wizard_form.project_id = project
            wizard_form.task_id = project.task_ids[:1]

        line_max = self.env["ps.time.line"].search([], limit=1, order="id desc")
        wizard.post()

        reverse_line, new_line = self.env["ps.time.line"].search(
            [("id", ">", line_max.id)], order="id asc"
        )
        self.assertEqual(self.ps_line.unit_amount, -reverse_line.unit_amount)

    def test_invoicing_properties(self):
        """Test invoicing properties form"""
        km_line = self.ps_line.copy(
            {
                "product_uom_id": self.env.ref("uom.product_uom_km").id,
                "non_invoiceable_mileage": True,
            }
        )
        with Form(self.project.invoice_properties) as properties_form:
            properties_form.invoice_mileage = True
        self.assertFalse(km_line.non_invoiceable_mileage)

    def test_delay(self):
        """Test delaying time lines"""
        wizard = (
            self.env["time.line.status"].with_context(
                active_id=self.ps_line[:1].id,
                active_ids=self.ps_line[:1].ids,
                active_model=self.ps_line._name,
            )
        ).create({})

        with Form(wizard) as wizard_form:
            wizard_form.name = "delayed"
            wizard_form.description = "hello world"

        move_max = self.env["account.move"].search([], limit=1, order="id desc")
        with mute_logger("odoo.addons.queue_job.delay"):
            wizard.with_context(test_queue_job_no_delay=True).ps_invoice_lines()

        self.assertEqual(self.ps_line.state, "delayed")
        reversed_move, move = self.env["account.move"].search(
            [("id", ">", move_max.id)]
        )
        self.assertEqual(reversed_move.reversed_entry_id, move)
        self.assertEqual(move.reversal_move_id, reversed_move)

    def test_task_user(self):
        """Test creating task.user objects"""
        task_user = self.env.ref("ps_timesheet_invoicing.task_user_task_11")
        hour_amount = self.ps_line.amount
        mileage_amount = self.ps_line_mileage.amount
        with self.assertRaises(ValidationError):
            task_user.copy({"fee_rate": 420})
        task_user += task_user[:1].copy({"from_date": "2023-01-02", "fee_rate": 420})
        task_user += task_user[:1].copy({"from_date": "2023-01-03", "fee_rate": 4200})
        task_user._compute_last_valid_fee_rate()
        self.assertEqual(task_user.filtered("last_valid_fee_rate"), task_user[-1:])
        self.env.clear()
        self.assertEqual(hour_amount * 100, self.ps_line.amount)
        self.assertEqual(mileage_amount, self.ps_line_mileage.amount)

    def test_odometer(self):
        """Test odometer recomputation works"""
        vehicle = self.env.ref("fleet.vehicle_1")
        self.env["fleet.vehicle.odometer"].search([]).unlink()
        odometer20230601 = self.env["fleet.vehicle.odometer"].create(
            {
                "vehicle_id": vehicle.id,
                "value_update": 42,
                "date": "2023-06-01",
            }
        )
        self.assertEqual(odometer20230601.value_period, 42)
        odometer20230101 = odometer20230601.copy(
            {"date": "2023-01-01", "value_period_update": 10}
        )
        self.assertEqual(odometer20230601.value, 52)
        odometer20230701 = odometer20230601.copy(
            {"date": "2023-07-01", "value_period_update": 20}
        )
        self.assertEqual(odometer20230701.value, 72)
        odometer20230101.value = 8
        self.assertEqual(odometer20230701.value, 70)
        odometer20230101.unlink()
        self.assertEqual(odometer20230701.value, 62)
