# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PropertyDetailsOffers(models.Model):
    _name = 'property.details.offers'
    _description = 'Property Details Offers'

    offer_template_id = fields.Many2one('property.sale.offer.template', required=True)
    property_id = fields.Many2one('property.details', required=True)
    total_installments = fields.Integer(required=True)


    def action_get_offer_report(self):
        pass