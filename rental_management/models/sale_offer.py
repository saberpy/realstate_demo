# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class SaleOffer(models.Model):
    """Reusable sale scenario which can be offered for many units."""

    _name = 'property.sale.offer'
    _description = 'Property Sale Offer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'

    name = fields.Char(required=True, readonly=True, copy=False,
                       default=lambda self: self.env._('New'))
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    offer_date = fields.Date(default=fields.Date.today, required=True)
    valid_until = fields.Date(string='Valid Until')
    offer_price = fields.Monetary(string='Offer Price', required=True, tracking=True)
    payment_line_ids = fields.One2many('property.sale.offer.line', 'offer_id',
                                       string='Payment Methods', copy=True)
    payment_total = fields.Monetary(compute='_compute_payment_total', store=True)
    unit_offer_ids = fields.One2many('property.sale.offer.unit', 'offer_id',
                                     string='Units', copy=True)
    notes = fields.Html()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('archived', 'Archived'),
    ], default='draft', required=True, tracking=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', self.env._('New')) == self.env._('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'property.sale.offer') or self.env._('New')
        return super().create(vals_list)

    @api.depends('payment_line_ids.amount')
    def _compute_payment_total(self):
        for offer in self:
            offer.payment_total = sum(offer.payment_line_ids.mapped('amount'))

    @api.constrains('offer_price', 'valid_until')
    def _check_offer(self):
        for offer in self:
            if offer.offer_price <= 0:
                raise ValidationError(self.env._('Offer price must be greater than zero.'))
            if offer.valid_until and offer.valid_until < offer.offer_date:
                raise ValidationError(self.env._('Valid Until cannot be before the offer date.'))

    def _check_ready_for_use(self):
        self.ensure_one()
        if not self.payment_line_ids:
            raise ValidationError(self.env._('Add at least one payment method before publishing the offer.'))
        if self.currency_id.compare_amounts(self.payment_total, self.offer_price) != 0:
            raise ValidationError(self.env._(
                'The total of payment methods must equal the offer price.'))
        if self.valid_until and self.valid_until < fields.Date.today():
            raise ValidationError(self.env._('This offer has expired.'))

    def action_publish(self):
        for offer in self:
            if offer.state != 'draft':
                raise ValidationError(self.env._('Only draft offers can be published.'))
            offer._check_ready_for_use()
            offer.state = 'published'

    def action_archive(self):
        self.write({'state': 'archived'})


class SaleOfferUnit(models.Model):
    """State of one reusable offer for one specific unit."""

    _name = 'property.sale.offer.unit'
    _description = 'Sale Offer Unit'
    _order = 'property_id, offer_id'
    _sql_constraints = [
        ('offer_unit_unique', 'unique(offer_id, property_id)',
         'An offer can only be linked to a unit once.'),
    ]

    offer_id = fields.Many2one('property.sale.offer', required=True, ondelete='cascade')
    property_id = fields.Many2one('property.details', string='Unit', required=True,
                                  ondelete='cascade', domain="[('sale_lease', '=', 'for_sale')]")
    customer_id = fields.Many2one(related='property_id.customer_id', string='Unit Customer',
                                  readonly=True)
    contract_id = fields.Many2one('property.vendor', string='Sale Contract', readonly=True,
                                  copy=False, ondelete='restrict')
    state = fields.Selection([
        ('available', 'Available'),
        ('customer_selected', 'Selected by Customer'),
        ('contracted', 'Contracted'),
        ('cancelled', 'Cancelled'),
    ], default='available', required=True, copy=False)

    @api.constrains('property_id')
    def _check_unit(self):
        for line in self:
            if line.property_id.sale_lease != 'for_sale':
                raise ValidationError(self.env._('Sale offers can only be linked to units for sale.'))
            if line.property_id.stage in ('sold', 'cancelled'):
                raise ValidationError(self.env._('A sold or cancelled unit cannot receive a sale offer.'))

    def _ensure_unit_open(self):
        self.ensure_one()
        if self.offer_id.state != 'published':
            raise ValidationError(self.env._('Only published offers can be selected.'))
        if self.property_id.stage in ('sold', 'cancelled'):
            raise ValidationError(self.env._('This unit is already sold or cancelled.'))

    def action_customer_select(self):
        for line in self:
            if line.state != 'available':
                raise ValidationError(self.env._('Only available offers can be selected.'))
            line._ensure_unit_open()
            if not line.property_id.customer_id:
                raise ValidationError(self.env._(
                    'Set the customer on the unit before selecting a sale offer.'))
            line.write({'state': 'customer_selected'})

    def action_seller_confirm(self):
        self.ensure_one()
        if self.state != 'customer_selected':
            raise ValidationError(self.env._(
                'The customer must select this offer before seller confirmation.'))
        self._ensure_unit_open()
        active_contract = self.env['property.vendor'].search([
            ('property_id', '=', self.property_id.id),
            ('stage', 'not in', ['refund', 'cancel']),
        ], limit=1)
        if active_contract:
            raise ValidationError(self.env._('This unit already has an active sale contract.'))

        contract = self.env['property.vendor'].create({
            'property_id': self.property_id.id,
            'customer_id': self.property_id.customer_id.id,
            'sale_price': self.offer_id.offer_price,
            'ask_price': self.offer_id.offer_price,
            'payment_term': 'offer_plan',
            'sale_offer_id': self.offer_id.id,
            'stage': 'booked',
        })
        for payment in self.offer_id.payment_line_ids.sorted(
                lambda item: (item.due_date or fields.Date.today(), item.sequence, item.id)):
            self.env['sale.invoice'].create({
                'name': payment.name,
                'desc': payment.description,
                'property_sold_id': contract.id,
                'invoice_date': payment.due_date,
                'amount': payment.amount,
                'sale_offer_line_id': payment.id,
            })
        self.write({'state': 'contracted', 'contract_id': contract.id})
        self.search([
            ('property_id', '=', self.property_id.id),
            ('id', '!=', self.id),
            ('state', 'in', ['available', 'customer_selected']),
        ]).write({'state': 'cancelled'})
        self.property_id.sold_booking_id = contract.id
        contract.action_confirm_sale()
        return {
            'type': 'ir.actions.act_window', 'name': self.env._('Sale Contract'),
            'res_model': 'property.vendor', 'res_id': contract.id,
            'view_mode': 'form', 'target': 'current',
        }


class SaleOfferLine(models.Model):
    _name = 'property.sale.offer.line'
    _description = 'Property Sale Offer Payment Method'
    _order = 'sequence, due_date, id'

    offer_id = fields.Many2one('property.sale.offer', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='offer_id.company_id', store=True)
    currency_id = fields.Many2one(related='offer_id.currency_id')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Payment Method', required=True)
    due_date = fields.Date(string='Due Date', required=True, default=fields.Date.today)
    amount = fields.Monetary(required=True)
    percentage = fields.Float(string='Percentage')
    description = fields.Text()
