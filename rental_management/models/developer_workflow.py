# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError



class DeveloperReservationForm(models.Model):
    _name = 'developer.reservation.form'
    _description = 'Developer Reservation Form'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    name = fields.Char(required=True, default=lambda self: self.env._('New'))
    customer_id = fields.Many2one('res.partner', string='Customer')
    opportunity_id = fields.Many2one('crm.lead', string='Opportunity')
    unit_id = fields.Many2one('property.details', string='Unit')
    project_id = fields.Many2one('property.project', string='Project')
    broker_id = fields.Many2one('res.partner', string='Broker')
    agent_id = fields.Many2one('res.partner', string='Agent')
    eoi_id = fields.Many2one('developer.eoi', string='EOI')
    reservation_date = fields.Date(string='Reservation Date', default=fields.Date.today)
    valid_until = fields.Date(string='Valid Until')
    unit_price = fields.Monetary(string='Unit Price')
    discount_amount = fields.Monetary(string='Discount Amount')
    final_price = fields.Monetary(string='Final Price')
    payment_plan_id = fields.Many2one('developer.payment.plan', string='Payment Plan')
    required_down_payment_percent = fields.Float(string='Required Down Payment %')
    required_down_payment_amount = fields.Monetary(string='Required Down Payment Amount')
    dld_fee_percent = fields.Float(string='DLD Fee %')
    dld_fee_amount = fields.Monetary(string='DLD Fee Amount')
    admin_fee = fields.Monetary(string='Admin Fee')
    eoi_deduction = fields.Monetary(string='EOI Deduction')
    net_required_before_spa = fields.Monetary(string='Net Required Before SPA')
    customer_signed = fields.Binary(string='Customer Signed')
    company_signed = fields.Binary(string='Company Signed')
    customer_signed_date = fields.Datetime(string='Customer Signed Date')
    company_signed_date = fields.Datetime(string='Company Signed Date')
    version_number = fields.Integer(string='Version Number', default=1)
    previous_version_id = fields.Many2one('developer.reservation.form', string='Previous Version')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
        ('sent_to_customer', 'Sent to Customer'),
        ('customer_signed', 'Customer Signed'),
        ('company_signed', 'Company Signed'),
        ('payment_pending', 'Payment Pending'),
        ('finance_approved', 'Finance Approved'),
        ('ready_for_spa', 'Ready for SPA'),
        ('converted_to_spa', 'Converted to SPA'),
        ('revised', 'Revised'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('automation', 'Automation'),
    ], default='draft', tracking=True)
    qr_code = fields.Binary(string='QR Code')

    def action_generate(self):
        for record in self:
            approval = self.env['developer.payment.approval'].search([
                ('related_model', '=', self._name),
                ('related_record_id', '=', record.id),
                ('state', '=', 'approved'),
            ], limit=1)
            if not approval:
                raise ValidationError(self.env._("Finance approval is required."))
            record.state = 'generated'
            if record.unit_id:
                record.unit_id.stage = 'booked'

    def action_finance_approved(self):
        self.state = 'ready_for_spa'

    def action_convert_to_spa(self):
        for record in self:
            approval = self.env['developer.payment.approval'].search([
                ('related_model', '=', 'developer.reservation.form'),
                ('related_record_id', '=', record.id),
                ('state', '=', 'approved'),
            ], limit=1)
            if not approval:
                raise ValidationError(self.env._("Finance approval is required."))
            spa = self.env['developer.spa'].create({
                'name': record.name,
                'customer_id': record.customer_id.id,
                'opportunity_id': record.opportunity_id.id,
                'unit_id': record.unit_id.id,
                'project_id': record.project_id.id,
                'reservation_id': record.id,
                'broker_id': record.broker_id.id,
                'agent_id': record.agent_id.id,
            })
            record.state = 'converted_to_spa'
            if record.unit_id:
                record.unit_id.stage = 'sold'
            self.env['developer.oqood.case'].create({
                'name': f'OQOOD/{record.name}',
                'spa_id': spa.id,
                'reservation_id': record.id,
                'unit_id': record.unit_id.id,
                'customer_id': record.customer_id.id,
                'state': 'draft',
            })
            spa.action_approved()
            return spa


class DeveloperSPA(models.Model):
    _name = 'developer.spa'
    _description = 'Developer Sale Purchase Agreement'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    name = fields.Char(required=True, default=lambda self: self.env._('New'))
    customer_id = fields.Many2one('res.partner', string='Customer')
    opportunity_id = fields.Many2one('crm.lead', string='Opportunity')
    unit_id = fields.Many2one('property.details', string='Unit')
    project_id = fields.Many2one('property.project', string='Project')
    reservation_id = fields.Many2one('developer.reservation.form', string='Reservation')
    broker_id = fields.Many2one('res.partner', string='Broker')
    agent_id = fields.Many2one('res.partner', string='Agent')
    spa_date = fields.Date(string='SPA Date', default=fields.Date.today)
    final_sale_price = fields.Monetary(string='Final Sale Price')
    payment_plan_id = fields.Many2one('developer.payment.plan', string='Payment Plan')
    customer_signed = fields.Binary(string='Customer Signed')
    chief_signed = fields.Binary(string='Chief Signed')
    customer_signed_date = fields.Datetime(string='Customer Signed Date')
    chief_signed_date = fields.Datetime(string='Chief Signed Date')
    chief_user_id = fields.Many2one('res.users', string='Chief User')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('admin_review', 'Admin Review'),
        ('sent_to_customer', 'Sent to Customer'),
        ('customer_signed', 'Customer Signed'),
        ('pending_chief_signature', 'Pending Chief Signature'),
        ('chief_signed', 'Chief Signed'),
        ('approved', 'Approved'),
        ('activated', 'Activated'),
        ('cancelled', 'Cancelled'),
        ('amended', 'Amended'),
        ('automation', 'Automation'),
    ], default='draft', tracking=True)
    qr_code = fields.Binary(string='QR Code')
    spa_attachment_id = fields.Many2one('ir.attachment', string='SPA Attachment')

    def action_chief_signed(self):
        for record in self:
            record.state = 'chief_signed'
            record.chief_user_id = self.env.user.id
            if record.unit_id:
                record.unit_id.stage = 'sold'
            if record.opportunity_id:
                if hasattr(record.opportunity_id, 'action_set_won'):
                    record.opportunity_id.action_set_won()
                else:
                    record.opportunity_id.stage_id = self.env.ref('crm.stage_lead_won', raise_if_not_found=False)
            record._create_downstream_records()

    def action_approved(self):
        self.state = 'approved'

    def action_activate(self):
        for record in self:
            approval = self.env['developer.payment.approval'].search([
                ('related_model', '=', 'developer.spa'),
                ('related_record_id', '=', record.id),
                ('state', '=', 'approved'),
            ], limit=1)
            if not approval:
                raise ValidationError(self.env._("Finance approval is required."))
            record.state = 'activated'

    def _create_downstream_records(self):
        self.ensure_one()
        if self.payment_plan_id and self.final_sale_price:
            installment_count = self.payment_plan_id.installment_count or 1
            installment_amount = self.final_sale_price / installment_count
            for index in range(installment_count):
                self.env['developer.payment.schedule'].create({
                    'name': f'{self.name} - Installment {index + 1}',
                    'payment_plan_id': self.payment_plan_id.id,
                    'sequence': index + 1,
                    'amount': installment_amount,
                    'state': 'draft',
                })
        return True


class DeveloperPaymentPlan(models.Model):
    _name = 'developer.payment.plan'
    _description = 'Developer Payment Plan'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    name = fields.Char(required=True)
    project_id = fields.Many2one('property.project', string='Project')
    description = fields.Text(string='Description')
    down_payment_percent = fields.Float(string='Down Payment %')
    dld_fee_percent = fields.Float(string='DLD Fee %')
    admin_fee = fields.Monetary(string='Admin Fee')
    installment_count = fields.Integer(string='Installment Count')
    handover_payment_percent = fields.Float(string='Handover Payment %')
    active = fields.Boolean(default=True)


class DeveloperPaymentSchedule(models.Model):
    _name = 'developer.payment.schedule'
    _description = 'Developer Payment Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    name = fields.Char(required=True)
    payment_plan_id = fields.Many2one('developer.payment.plan', string='Payment Plan')
    due_date = fields.Date(string='Due Date')
    amount = fields.Monetary(string='Amount')
    sequence = fields.Integer(string='Sequence')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    ], default='draft')


class DeveloperPaymentApproval(models.Model):
    _name = 'developer.payment.approval'
    _description = 'Developer Payment Approval'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    name = fields.Char(required=True, default=lambda self: self.env._('New'))
    customer_id = fields.Many2one('res.partner', string='Customer')
    opportunity_id = fields.Many2one('crm.lead', string='Opportunity')
    unit_id = fields.Many2one('property.details', string='Unit')
    related_model = fields.Char(string='Related Model')
    related_record_id = fields.Integer(string='Related Record ID')
    amount = fields.Monetary(string='Amount')
    payment_type = fields.Selection([
        ('eoi', 'EOI'),
        ('rf', 'Reservation Form'),
        ('spa', 'SPA'),
        ('handover', 'Handover'),
    ], string='Payment Type')
    payment_proof_id = fields.Many2one('ir.attachment', string='Payment Proof')
    bank_reference = fields.Char(string='Bank Reference')
    payment_date = fields.Date(string='Payment Date')
    reviewed_by = fields.Many2one('res.users', string='Reviewed By')
    approved_by = fields.Many2one('res.users', string='Approved By')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('finance_review', 'Finance Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('need_more_information', 'Need More Information'),
    ], default='draft', tracking=True)

    def action_submit(self):
        self.state = 'submitted'

    def action_finance_review(self):
        self.state = 'finance_review'

    def action_approve(self):
        self.state = 'approved'
        self.approved_by = self.env.user.id

    def action_reject(self):
        self.state = 'rejected'


class DeveloperOqoodCase(models.Model):
    _name = 'developer.oqood.case'
    _description = 'Developer Oqood Case'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    name = fields.Char(required=True, default=lambda self: self.env._('New'))
    spa_id = fields.Many2one('developer.spa', string='SPA')
    reservation_id = fields.Many2one('developer.reservation.form', string='Reservation')
    unit_id = fields.Many2one('property.details', string='Unit')
    customer_id = fields.Many2one('res.partner', string='Customer')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('done', 'Done'),
    ], default='draft')
