# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

import json

from lxml import etree

from odoo import api, models


class PsPlanningDepartmentMixin(models.AbstractModel):
    _name = "ps.planning.department.mixin"
    _description = "Mixin to inject department filters in the search view"

    @api.model
    def _fields_view_get(
        self, view_id=None, view_type="form", toolbar=False, submenu=False
    ):
        result = super()._fields_view_get(
            view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu
        )
        if view_type == "search":
            arch = etree.fromstring(result["arch"])
            for node in arch.xpath("//search"):
                etree.SubElement(
                    node,
                    "separator",
                )
                for department in self.env["hr.department"].search([]):
                    etree.SubElement(
                        node,
                        "filter",
                        attrib={
                            "string": department.name,
                            "domain": json.dumps(
                                [("project_id.department_id", "=", department.id)]
                            ),
                        },
                    )

            result["arch"] = etree.tostring(arch)
        return result
