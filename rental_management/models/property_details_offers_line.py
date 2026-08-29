# -*- coding: utf-8 -*-
from odoo import api, fields, models

STATUTORY_KEYWORDS = ('dld', 'admin')


class PropertyDetailsOffersLine(models.Model):
    """One generated installment of a unit's payment schedule."""

    _name = 'property.details.offers.line'
    _description = 'Property Details Offer Installment'
    _order = 'sequence, due_date, id'

    offer_id = fields.Many2one('property.details.offers', required=True, ondelete='cascade')
    source_line_id = fields.Many2one('property.sale.offer.template.line',
                                     string='Template Line', ondelete='set null')
    company_id = fields.Many2one(related='offer_id.company_id', store=True)
    currency_id = fields.Many2one(related='offer_id.currency_id')
    name = fields.Char(string='Payment Type', required=True)
    sequence = fields.Integer()
    due_date = fields.Date(string='Due Date', required=True)
    amount_type = fields.Selection([('percentage', 'Percentage of Unit Price'),
                                    ('fixed', 'Fixed Amount')],
                                   default='percentage', required=True)
    percentage = fields.Float(string='Percentage')
    amount = fields.Monetary(string='Amount', required=True)
    paid_amount = fields.Monetary(string='Receipt / Adjusted', default=0.0)
    balance = fields.Monetary(compute='_compute_balance', store=True)
    is_statutory_charge = fields.Boolean(compute='_compute_is_statutory_charge', store=True,
                                         help='Detected from the payment name (e.g. "DLD", "Admin").')
    status = fields.Selection([('fully_paid', 'Fully Paid'),
                               ('partially_paid', 'Partially Paid'),
                               ('overdue', 'Overdue'),
                               ('not_due', 'Not Yet Due')],
                              compute='_compute_status')

    @api.depends('amount', 'paid_amount')
    def _compute_balance(self):
        for line in self:
            line.balance = line.amount - line.paid_amount

    @api.depends('name')
    def _compute_is_statutory_charge(self):
        for line in self:
            label = (line.name or '').lower()
            line.is_statutory_charge = any(keyword in label for keyword in STATUTORY_KEYWORDS)

    @api.depends('amount', 'paid_amount', 'due_date')
    def _compute_status(self):
        today = fields.Date.today()
        for line in self:
            if line.paid_amount >= line.amount and line.amount > 0:
                line.status = 'fully_paid'
            elif line.paid_amount > 0:
                line.status = 'partially_paid'
            elif line.due_date and line.due_date < today:
                line.status = 'overdue'
            else:
                line.status = 'not_due'
