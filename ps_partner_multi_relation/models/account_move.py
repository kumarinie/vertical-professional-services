from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _compute_member_invoice(self):
        member_invoice = self.read_group(
            [("parent_id", "in", self.ids)], ["parent_id"], ["parent_id"]
        )
        res = {data["parent_id"][0]: data["parent_id_count"] for data in member_invoice}
        for line in self:
            line.member_invoice_count = res.get(line.id, 0)

    parent_id = fields.Many2one(
        comodel_name="account.move", string="Parent Invoice", index=True
    )
    child_ids = fields.One2many("account.move", "parent_id")

    member_invoice_count = fields.Integer(
        "Member Invoices", compute="_compute_member_invoice"
    )

    @api.model
    def get_members_sharing_key(self, left_partner_id, relation_type):
        members_data = {}
        relations = self.env["res.partner.relation"].search(
            [
                ("left_partner_id", "=", left_partner_id.id),
                ("type_id", "=", relation_type),
            ]
        )
        total_share = sum([r.distribution_key for r in relations])
        for rel in relations:
            members_data.update(
                {rel.right_partner_id: (rel.distribution_key / total_share)}
            )
        return members_data

    @api.model
    def _prepare_member_invoice_line(self, line, invoice, share_key):
        invoice_line_vals = {
            "name": line.name,
            "move_id": invoice.id,
            "product_id": line.product_id.id,
            "quantity": line.quantity,
            "product_uom_id": line.product_uom_id.id,
            "discount": line.discount,
            "account_id": line.account_id.id,
            "analytic_tag_ids": [fields.Command.set(line.analytic_tag_ids.ids)],
            "price_unit": line.price_unit * share_key,
            "analytic_distribution": line.analytic_distribution,
        }

        # Analytic Invoice invoicing period is doesn't lies in same month update with
        # property_account_wip_id
        if line.ps_invoice_id.period_id:
            period_date = line.ps_invoice_id.period_id.date_start.strftime("%Y-%m")
            invoice_date = (
                line.ps_invoice_id.date or line.ps_invoice_id.invoice_id.invoice_date
            )
            inv_date = invoice_date.strftime("%Y-%m")
            if inv_date != period_date:
                account = (
                    line.product_id.property_account_wip_id
                    or line.company_id.wip_journal_id.default_account_id
                )
                invoice_line_vals.update({"account_id": account.id})

        return invoice_line_vals

    def _prepare_member_invoice(self, partner):
        self.ensure_one()
        company_id = partner.company_id if partner.company_id else self.company_id
        journal = self.journal_id or self.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", company_id.id)], limit=1
        )
        if not journal:
            raise ValidationError(
                _("Please define a sale journal for the company '%s'.")
                % (company_id.name or "",)
            )
        currency = (
            partner.property_product_pricelist.currency_id or company_id.currency_id
        )
        invoice_vals = {
            "ref": self.name,
            "move_type": "out_invoice",
            "partner_id": partner.address_get(["invoice"])["invoice"],
            "currency_id": currency.id,
            "journal_id": journal.id,
            "invoice_date": self.invoice_date,
            # TODO: restore origin field?
            # 'origin': self.name,
            "company_id": company_id.id,
            "parent_id": self.id,
            "user_id": partner.user_id.id,
            "invoice_description": self.invoice_description,
            "ps_custom_layout": self.ps_custom_layout,
            "ps_custom_footer": self.ps_custom_footer,
            "ps_custom_header": self.ps_custom_header,
        }

        return invoice_vals

    def _create_member_invoice(self, partner, share_key):
        self.ensure_one()
        invoice_vals = self._prepare_member_invoice(partner)
        invoice = self.env["account.move"].create(invoice_vals)
        invoice.write(
            {
                "invoice_line_ids": [
                    (0, 0, self._prepare_member_invoice_line(line, invoice, share_key))
                    for line in self.invoice_line_ids
                ],
            }
        )
        return invoice

    def _post(self, soft=True):
        """
            If partner has members split invoice by distribution keys,
            & Validate same invoice without creating moves
            Otherwise, call super()
        :return:
        """

        relation_type = self.env.ref("ps_partner_multi_relation.rel_type_consortium").id
        invoice2members_data = {
            this: members_data
            for this, members_data in (
                (this, self.get_members_sharing_key(this.partner_id, relation_type))
                for this in self
            )
            if members_data
        }

        result = super(
            AccountMove, self - sum(invoice2members_data, self.browse([]))
        )._post(soft=soft)

        # lots of duplicate calls to action_invoice_open, so we remove those already open
        to_open_invoices = self.filtered(
            lambda inv: inv.state != "open" and inv in invoice2members_data
        )
        if to_open_invoices.filtered(lambda inv: inv.state != "draft"):
            raise UserError(
                _("Invoice must be in draft state in order to validate it.")
            )

        for invoice in to_open_invoices:
            for partner, share_key in invoice2members_data[invoice].items():
                invoice._create_member_invoice(partner, share_key)

        to_open_invoices.button_cancel()

        return result + to_open_invoices

    def action_view_member_invoice(self):
        self.ensure_one()
        action = self.env.ref("account.action_move_out_invoice_type").read()[0]
        invoice = self.search([("parent_id", "in", self._ids)])
        if not invoice or len(invoice) > 1:
            action["domain"] = [("id", "in", invoice.ids)]
        elif invoice:
            action["views"] = [(self.env.ref("account.view_move_form").id, "form")]
            action["res_id"] = invoice.id
        action["context"] = {}
        return action
