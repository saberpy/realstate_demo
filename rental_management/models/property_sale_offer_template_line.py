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
    percentage = fields.Float(string='Percentage', required=True)
    description = fields.Text()


    @api.constrains('sequence', 'due_date')
    def _check_sequence_or_due_date(self):
        for line in self:
            if not line.sequence and not line.due_date:
                raise ValidationError(_("One of (Sequence, Due Date) is required!"))