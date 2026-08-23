# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleOfferPaymentGenerator(models.TransientModel):
    """Build a full payment schedule from a few business payment rules."""

    _name = 'property.sale.offer.payment.generator'
    _description = 'Sale Offer Payment Schedule Generator'

    offer_id = fields.Many2one('property.sale.offer', required=True, readonly=True)
    company_id = fields.Many2one(related='offer_id.company_id')
    currency_id = fields.Many2one(related='offer_id.currency_id')
    base_amount = fields.Monetary(string='Sale Price', required=True)
    replace_existing = fields.Boolean(string='Replace Existing Schedule', default=True)
    rule_ids = fields.One2many('property.sale.offer.payment.generator.rule', 'wizard_id',
                               string='Payment Rules')
    generated_total = fields.Monetary(compute='_compute_generated_total')
    remaining_amount = fields.Monetary(compute='_compute_generated_total')

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        offer = self.env['property.sale.offer'].browse(self.env.context.get('active_id'))
        if offer:
            values.update({
                'offer_id': offer.id,
                'base_amount': offer.offer_price,
            })
        return values

    @api.depends('base_amount', 'rule_ids.calculation_type', 'rule_ids.percent',
                 'rule_ids.fixed_amount', 'rule_ids.installment_count')
    def _compute_generated_total(self):
        for wizard in self:
            total = 0.0
            for rule in wizard.rule_ids:
                unit_amount = (wizard.base_amount * rule.percent / 100.0
                               if rule.calculation_type == 'percent' else rule.fixed_amount)
                total += unit_amount * rule.installment_count
            wizard.generated_total = total
            wizard.remaining_amount = wizard.base_amount - total

    def action_generate(self):
        self.ensure_one()
        if self.offer_id.state != 'draft':
            raise ValidationError(self.env._('Payment schedules can only be generated for draft offers.'))
        if self.base_amount <= 0:
            raise ValidationError(self.env._('Sale price must be greater than zero.'))
        if not self.rule_ids:
            raise ValidationError(self.env._('Add at least one payment rule.'))

        values_list = []
        sequence = 10
        for rule in self.rule_ids.sorted('sequence'):
            rule._validate_rule()
            amount = (self.base_amount * rule.percent / 100.0
                      if rule.calculation_type == 'percent' else rule.fixed_amount)
            for number in range(1, rule.installment_count + 1):
                values_list.append({
                    'sequence': sequence,
                    'name': rule.name if rule.installment_count == 1
                    else f'{rule.name} {number}/{rule.installment_count}',
                    'due_date': rule._get_due_date(number - 1),
                    'amount': self.currency_id.round(amount),
                    'percentage': rule.percent if rule.calculation_type == 'percent' else 0.0,
                    'description': rule.description,
                })
                sequence += 10

        total = sum(value['amount'] for value in values_list)
        if self.currency_id.compare_amounts(self.generated_total, self.base_amount) != 0:
            raise ValidationError(self.env._(
                'The generated schedule must equal the sale price. Adjust the rules, '
                'percentages, or fixed amounts.'))
        # Preserve the exact sale price despite per-line currency rounding.
        values_list[-1]['amount'] += self.base_amount - total

        if self.replace_existing:
            self.offer_id.payment_line_ids.unlink()
        self.offer_id.write({
            'offer_price': self.base_amount,
            'payment_line_ids': [(0, 0, values) for values in values_list],
        })
        return {'type': 'ir.actions.act_window_close'}


class SaleOfferPaymentGeneratorRule(models.TransientModel):
    _name = 'property.sale.offer.payment.generator.rule'
    _description = 'Sale Offer Payment Generator Rule'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('property.sale.offer.payment.generator', required=True,
                                ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Payment Type', required=True, default='Monthly Installment')
    calculation_type = fields.Selection([
        ('percent', 'Percentage of Sale Price'),
        ('fixed', 'Fixed Amount'),
    ], default='percent', required=True)
    percent = fields.Float(string='Percentage per Payment', default=1.0)
    fixed_amount = fields.Monetary(string='Amount per Payment')
    currency_id = fields.Many2one(related='wizard_id.currency_id')
    start_date = fields.Date(string='First Due Date', required=True, default=fields.Date.today)
    recurrence = fields.Selection([
        ('once', 'One Time'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ], default='once', required=True)
    installment_count = fields.Integer(string='Number of Payments', default=1, required=True)
    description = fields.Text()

    def _validate_rule(self):
        self.ensure_one()
        if self.installment_count < 1:
            raise ValidationError(self.env._('Number of payments must be at least one.'))
        if self.calculation_type == 'percent' and self.percent <= 0:
            raise ValidationError(self.env._('Percentage per payment must be greater than zero.'))
        if self.calculation_type == 'fixed' and self.fixed_amount <= 0:
            raise ValidationError(self.env._('Fixed amount per payment must be greater than zero.'))
        if self.recurrence == 'once' and self.installment_count != 1:
            raise ValidationError(self.env._('A one-time rule must have exactly one payment.'))

    def _get_due_date(self, index):
        self.ensure_one()
        intervals = {
            'once': {}, 'monthly': {'months': index},
            'quarterly': {'months': index * 3}, 'yearly': {'years': index},
        }
        return self.start_date + relativedelta(**intervals[self.recurrence])
