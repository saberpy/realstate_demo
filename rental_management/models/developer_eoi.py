# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class DeveloperEOI(models.Model):
    _name = 'developer.eoi'
    _description = 'Developer Expression of Interest'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    name = fields.Char(required=True, default=lambda self: self.env._('New'), copy=False)
    customer_id = fields.Many2one('res.partner', string='Customer', required=True)
    opportunity_id = fields.Many2one('crm.lead', string='Opportunity')
    unit_id = fields.Many2one('property.details', string='Unit')
    project_id = fields.Many2one('property.project', string='Project')
    broker_id = fields.Many2one('res.partner', string='Broker')
    agent_id = fields.Many2one('res.partner', string='Agent')
    eoi_amount = fields.Monetary(string='EOI Amount', required=True)
    payment_proof_id = fields.Many2one('ir.attachment', string='Payment Proof')
    payment_status = fields.Selection([
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed')
    ], string='Payment Status', default='pending', tracking=True)
    refund_policy = fields.Text(string='Refund Policy')
    deduction_amount = fields.Monetary(string='Deduction Amount')
    expiry_date = fields.Date(string='Expiry Date')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('payment_proof_uploaded', 'Payment Proof Uploaded'),
        ('finance_review', 'Finance Review'),
        ('manager_review', 'Manager Review'),
        ('confirmed', 'Confirmed'),
        ('converted_to_rf', 'Converted to RF'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('refund_pending', 'Refund Pending'),
        ('refunded', 'Refunded'),
    ], default='draft', tracking=True)
    qr_code = fields.Binary(string='QR Code')
    cancellation_history = fields.Text(string='Cancellation History', copy=False)

    # ==========================================
    # HELPER METHODS
    # ==========================================
    def _require_finance_approval(self):
        self.ensure_one()
        approval = self.env['developer.payment.approval'].search([
            ('related_model', '=', self._name),
            ('related_record_id', '=', self.id),
            ('state', '=', 'approved'),
        ], limit=1)
        if not approval:
            raise ValidationError(self.env._("Finance approval is required before proceeding."))

    # ==========================================
    # FLOW MANAGEMENT ACTIONS
    # ==========================================
    
    def action_submit(self):
        for record in self:
            if record.state != 'draft':
                continue
            if record.name == self.env._('New'):
                record.name = self.env['ir.sequence'].next_by_code('developer.eoi') or '/'
            record.state = 'submitted'
            
    def action_upload_payment_proof(self):
        for record in self:
            if not record.payment_proof_id:
                raise ValidationError(self.env._("Please upload the payment proof attachment first."))
            record.write({
                'state': 'finance_review',
                'payment_status': 'pending'
            })

    def action_finance_approve(self):
        for record in self:
            if record.state != 'finance_review':
                continue
            record._require_finance_approval() 
            record.write({
                'state': 'manager_review',
                'payment_status': 'paid'
            })

    def action_confirm(self):
        for record in self:
            if record.state != 'manager_review':
                raise ValidationError(self.env._("Only records in Manager Review can be confirmed."))
            record.state = 'confirmed'
            if record.unit_id:
                if record.unit_id.stage in ['booked', 'sold']:
                    raise ValidationError(self.env._("The selected unit is already booked or sold."))
                record.unit_id.stage = 'prebooked'

    def action_convert_to_rf(self):
        for record in self:
            if record.state != 'confirmed':
                raise ValidationError(self.env._("Only confirmed EOIs can be converted to Reservation Form."))
            
            record.state = 'converted_to_rf'
            if record.unit_id:
                record.unit_id.stage = 'booked'
                
            reservation = self.env['developer.reservation.form'].create({
                'name': record.name,
                'customer_id': record.customer_id.id,
                'opportunity_id': record.opportunity_id.id,
                'unit_id': record.unit_id.id,
                'project_id': record.project_id.id,
                'broker_id': record.broker_id.id,
                'agent_id': record.agent_id.id,
                'eoi_id': record.id,
                'state': 'generated',
            })
            record.message_post(body=f"Reservation form created: {reservation.display_name}")

    def action_reject(self, reason=None):
        for record in self:
            record.state = 'rejected'
            if record.unit_id and record.unit_id.stage == 'prebooked':
                record.unit_id.stage = 'available'
            record.message_post(body=f"EOI Rejected. Reason: {reason or 'No reason provided.'}")

    def action_cancel(self, reason=None):
        for record in self:
            record.cancellation_history = (record.cancellation_history or '') + (
                f"\nCancelled on {fields.Datetime.now()}: {reason or ''}"
            )
            record.state = 'cancelled'
            if record.unit_id:
                record.unit_id.stage = 'available'

    def action_refund_pending(self):
        for record in self:
            if record.state not in ['cancelled', 'rejected']:
                raise ValidationError(self.env._("Only cancelled or rejected EOIs can be moved to Refund Pending."))
            record.state = 'refund_pending'

    def action_refunded(self):
        for record in self:
            if record.state != 'refund_pending':
                raise ValidationError(self.env._("Application must be in 'Refund Pending' state."))
            record.state = 'refunded'
            record.message_post(body=f"Refund processed successfully. Deduction: {record.deduction_amount}")

    def action_set_to_draft(self):
        for record in self:
            if record.state in ['confirmed', 'converted_to_rf', 'refunded']:
                raise ValidationError(self.env._("Cannot reset to draft at this stage."))
            record.state = 'draft'

    # ==========================================
    # AUTOMATION / CRON ACTIONS
    # ==========================================
    @api.model
    def cron_check_expired_eoi(self):
        today = fields.Date.today()
        expired_records = self.search([
            ('state', 'in', ['draft', 'submitted', 'confirmed']),
            ('expiry_date', '<', today)
        ])
        for record in expired_records:
            record.state = 'expired'
            if record.unit_id and record.unit_id.stage == 'prebooked':
                record.unit_id.stage = 'available'
            record.message_post(body="Automatically set to Expired due to reaching the expiry date.")