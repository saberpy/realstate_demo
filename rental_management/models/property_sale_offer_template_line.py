# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PropertySaleOfferTemplateLine(models.Model):
    _name = 'property.sale.offer.template.line'
    _description = 'Property Sale Offer Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Payment Name', required=True)
    offer_id = fields.Many2one('property.sale.offer.template', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='offer_id.company_id', store=True)
    currency_id = fields.Many2one(related='offer_id.currency_id')
    sequence = fields.Integer()
    due_date = fields.Date(string='Due Date')
    amount_type = fields.Selection([('percentage', 'Percentage of Unit Price'),
                                    ('fixed', 'Fixed Amount')],
                                   string='Amount Type', default='percentage', required=True)
    percentage = fields.Float(string='Percentage')
    fixed_amount = fields.Monetary(string='Fixed Amount')
    description = fields.Text()

    @api.constrains('sequence', 'due_date')
    def _check_sequence_or_due_date(self):
        for line in self:
            if not line.sequence and not line.due_date:
                raise ValidationError(_("One of (Sequence, Due Date) is required!"))

    @api.constrains('amount_type', 'percentage', 'fixed_amount')
    def _check_amount(self):
        for line in self:
            if line.amount_type == 'percentage' and line.percentage <= 0:
                raise ValidationError(_("Percentage must be greater than zero."))
            if line.amount_type == 'fixed' and line.fixed_amount <= 0:
                raise ValidationError(_("Fixed amount must be greater than zero."))