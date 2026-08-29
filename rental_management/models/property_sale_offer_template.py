# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PropertySaleOfferTemplate(models.Model):
    _name = 'property.sale.offer.template'
    _description = 'Property Sale Offer Template'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True, readonly=False, copy=False)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    line_ids = fields.One2many('property.sale.offer.template.line', 'offer_id', string='Payment Methods', copy=True)
    payment_total_percent = fields.Float(compute='_compute_payment_total_percent', store=True)
    notes = fields.Html()
    state = fields.Selection([('draft', 'Draft'), ('published', 'Published'), ('archived', 'Archived'),], default='draft', required=True, tracking=True, copy=False)


    @api.depends('line_ids.percentage')
    def _compute_payment_total_percent(self):
        for offer in self:
            offer.payment_total_percent = sum(offer.line_ids.mapped('percentage'))

    @api.constrains('payment_total_percent')
    def _check_payment_total_percent(self):
        for offer in self:
            if offer.payment_total_percent > 1:
                raise ValidationError(_('Offer total percent cannot be greater than 100.'))

    def _check_ready_for_use(self):
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_('Add at least one payment method before publishing the offer.'))

    def action_publish(self):
        for offer in self:
            if offer.state != 'draft':
                raise ValidationError(_('Only draft offers can be published.'))
            offer._check_ready_for_use()
            offer.state = 'published'

    def action_archive(self):
        self.write({'state': 'archived'})