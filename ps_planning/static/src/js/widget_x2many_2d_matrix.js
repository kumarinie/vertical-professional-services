/* License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl). */

odoo.define("ps_planning.web_widget_x2many_2d_matrix", function (require) {
    "use strict";

    var core = require("web.core");
    var _t = core._t;
    var field_registry = require("web.field_registry");
    var field_utils = require("web.field_utils");
    var X2Many2dMatrixRenderer = require("web_widget_x2many_2d_matrix.X2Many2dMatrixRenderer");

    var WidgetX2Many2dMatrixWidget = require("web_widget_x2many_2d_matrix.widget");
    var WidgetX2Many2dMatrix = WidgetX2Many2dMatrixWidget.WidgetX2Many2dMatrix;

    var FormView = require("web.FormView");

    FormView.include({
        _setSubViewLimit: function (attrs) {
            this._super(attrs);
            if (attrs.widget === "x2many_2d_matrix_ps_planning") {
                attrs.limit = Infinity;
            }
        },
    });

    var CustomMatrixWidget = WidgetX2Many2dMatrix.extend({
        init: function (parent, name, record, options) {
            this._super(parent, name, record, options);
        },

        init_params: function () {
            this._super();
        },

        init_matrix: function () {
            this._super();
        },

        _render: function () {
            if (!this.view) {
                return this._super();
            }
            this.$el.addClass("o_form_field_x2many_2d_matrix_ps_planning");
            return this._super();
        },
    });

    X2Many2dMatrixRenderer.include({
        is_ps_planning: false,
        init: function (parent) {
            this._super.apply(this, arguments);
            this.is_ps_planning = parent.$el.hasClass(
                "o_form_field_x2many_2d_matrix_ps_planning"
            );
        },
        _renderView: function () {
            var result = this._super();
            if (!this.is_ps_planning) {
                return result;
            }
            this.$el.children("table").removeClass("table-striped");
            return result;
        },
        _renderHeader: function () {
            var $thead = this._super();
            if (!this.is_ps_planning) {
                return $thead;
            }
            $thead
                .find("th")
                .first()
                .after($("<th>").append($("<div/>").text(_t("Employee"))));
            $thead
                .find("th")
                .first()
                .after($("<th>").append($("<div/>").text(_t("Rate"))));
            $thead
                .find("th")
                .first()
                .after($("<th>").append($("<div/>").text(_t("Product"))));
            $thead
                .find("th")
                .first()
                .after($("<th>").append($("<div/>").text(_t("Task"))));
            $thead
                .find("th")
                .first()
                .after($("<th>").append($("<div/>").text(_t("Status"))));
            $thead
                .find("th")
                .first()
                .after($("<th>").append($("<div/>").text(_t("Type"))));
            $thead
                .find("th")
                .first()
                .after($("<th>").append($("<div/>").text(_t("Total days"))));
            $thead.find("th").first().hide();
            return $thead;
        },
        _renderRow: function (row) {
            var self = this;
            var $tr = this._super(row);

            if (!this.is_ps_planning) {
                return $tr;
            }
            var data = row.data[0].data;
            $tr.find("td")
                .first()
                .after(
                    $("<td>").text(
                        data.line_type === "contracted"
                            ? ""
                            : data.employee_id.data.display_name
                    )
                );
            $tr.find("td")
                .first()
                .after($("<td>").text(field_utils.format.float(data.daily_rate)));
            $tr.find("td")
                .first()
                .after($("<td>").text(data.product_id.data.display_name));
            $tr.find("td")
                .first()
                .after($("<td>").text(data.task_id.data.display_name));
            var $td = $("<td>");
            if (data.line_type !== "contracted") {
                $td.append(
                    $('<input type="checkbox" />')
                        .prop("checked", data.state === "final")
                        .attr("id", "final_" + data.id)
                        .change(function () {
                            var value = $(this).prop("checked") ? "final" : "draft";
                            row.data.forEach(function (cell) {
                                self.trigger_up("field_changed", {
                                    dataPointID: cell.id,
                                    notifyChange: true,
                                    changes: {
                                        state: value,
                                    },
                                });
                            });
                            $tr.find("input[type='text']").prop(
                                "disabled",
                                value === "final"
                            );
                        })
                );
                $td.append(
                    $("<label />")
                        .attr("for", "final_" + data.id)
                        .text(_t("Final"))
                );
            }
            $tr.find("td").first().after($td);
            $tr.find("td").first().after($("<td>").text(data.line_type));
            $tr.find("td")
                .first()
                .after(
                    $("<td>").text(
                        data.line_type === "contracted"
                            ? field_utils.format.float(data.contracted_days)
                            : ""
                    )
                );
            $tr.find("td").first().hide();
            if (data.line_type === "contracted") {
                $tr.addClass("table-active");
            }
            return $tr;
        },
        _renderFooter: function () {
            var $tfoot = this._super();
            if (!this.is_ps_planning) {
                return $tfoot;
            }
            $tfoot.find("td").first().after("<td/><td/><td/><td/><td/><td/><td/>");
            $tfoot.find("td").first().hide();
            return $tfoot;
        },
        _computeColumnAggregates: function () {
            this._super();
            if (!this.is_ps_planning) {
                return;
            }
            this.total.aggregate.value = 0;
            this.total.aggregate.contracted_value = 0;
            var fname = this.matrix_data.field_value;
            _.each(
                this.columns,
                function (column, index) {
                    column.aggregate = {
                        help: _t("Sum"),
                        value: 0,
                        contracted_value: 0,
                    };
                    _.each(this.rows, function (row) {
                        var data = row.data[index].data;
                        if (data.line_type === "planned") {
                            column.aggregate.value += data[fname];
                        } else if (data.line_type === "contracted") {
                            column.aggregate.contracted_value += data[fname];
                        }
                    });
                    this.total.aggregate.value += column.aggregate.value;
                    this.total.aggregate.contracted_value +=
                        column.aggregate.contracted_value;
                }.bind(this)
            );
        },
        applyAggregateValue: function ($cell, axis) {
            this._super($cell, axis);
            if (!this.is_ps_planning) {
                return;
            }
            if (axis.aggregate.contracted_value !== undefined) {
                $cell.text(
                    String(field_utils.format.float(axis.aggregate.value)) +
                        "/" +
                        String(
                            field_utils.format.float(axis.aggregate.contracted_value)
                        )
                );
            }
        },
    });

    field_registry.add("x2many_2d_matrix_ps_planning", CustomMatrixWidget);

    return {
        widget: CustomMatrixWidget,
    };
});
