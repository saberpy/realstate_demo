# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PropertyDetailsOffers(models.Model):
    """Links a sale offer template to one unit and generates its payment schedule."""

    _name = 'property.details.offers'
    _description = 'Property Details Offers'

    offer_template_id = fields.Many2one('property.sale.offer.template', required=True,
                                        domain="[('state', '=', 'published')]")
    property_id = fields.Many2one('property.details', required=True)
    company_id = fields.Many2one(related='property_id.company_id', store=True)
    currency_id = fields.Many2one(related='property_id.currency_id')
    customer_id = fields.Many2one(related='property_id.customer_id', string='Customer',
                                  store=True, readonly=True)
    unit_price = fields.Monetary(related='property_id.price', string='Unit Price', readonly=True)
    start_date = fields.Date(string='Schedule Start Date', default=fields.Date.context_today,
                             required=True,
                             help='Anchor date used to compute the monthly installments.')
    total_installments = fields.Integer(required=True)
    line_ids = fields.One2many('property.details.offers.line', 'offer_id',
                               string='Payment Schedule')
    schedule_total = fields.Monetary(compute='_compute_schedule_total')

    @api.depends('line_ids.amount')
    def _compute_schedule_total(self):
        for offer in self:
            offer.schedule_total = sum(offer.line_ids.mapped('amount'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._generate_schedule()
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals.keys() & {'offer_template_id', 'total_installments', 'property_id', 'start_date'}:
            self._generate_schedule()
        return res

    def action_generate_schedule(self):
        self._generate_schedule()

    def action_get_offer_report(self):
        return self.env.ref('rental_management.action_report_property_details_offers').report_action(self)

    # ==========================================
    # SCHEDULE GENERATION
    # ==========================================
    def _generate_schedule(self):
        for offer in self:
            offer.line_ids.unlink()
            if not offer.offer_template_id or not offer.total_installments:
                continue
            offer._build_schedule_lines()

    def _build_schedule_lines(self):
        """Turn the offer template's lines into a concrete, dated installment schedule.

        Fixed-amount lines (statutory charges such as DLD/Admin fees, identified by
        amount_type='fixed') are generated once each, outside the monthly slots.

        Percentage lines are placed one per month, walking forward from start_date:
        for each month slot, the nearest not-yet-used due-date line that falls within
        that month's window wins; if none does, the next not-yet-used sequence-ordered
        line is used instead (dated to that month); once both pools are exhausted, the
        remaining slots become plain monthly installments splitting the leftover
        percentage evenly.
        """
        self.ensure_one()
        template_lines = self.offer_template_id.line_ids
        statutory_lines = template_lines.filtered(lambda line: line.amount_type == 'fixed')
        schedule_lines = template_lines.filtered(lambda line: line.amount_type == 'percentage')
        due_pool = schedule_lines.filtered('due_date').sorted('due_date')
        seq_pool = schedule_lines.filtered(lambda line: not line.due_date).sorted('sequence')

        if len(due_pool) + len(seq_pool) > self.total_installments:
            raise ValidationError(_(
                'Total installments (%(count)s) is smaller than the number of payment lines '
                'defined on the offer template (%(lines)s).',
                count=self.total_installments, lines=len(due_pool) + len(seq_pool)))

        values = []
        used_due_ids = set()
        seq_index = 0
        consumed_percent = 0.0
        leftover_indexes = []
        sequence = 1

        for line in statutory_lines:
            values.append({
                'sequence': sequence,
                'name': line.name,
                'due_date': line.due_date or self.start_date,
                'amount_type': 'fixed',
                'percentage': 0.0,
                'amount': line.fixed_amount,
                'source_line_id': line.id,
            })
            sequence += 1

        sequence = 10
        for slot in range(1, self.total_installments + 1):
            window_end = self.start_date + relativedelta(months=slot)
            candidate = next((cand for cand in due_pool
                              if cand.id not in used_due_ids and cand.due_date <= window_end), None)
            if candidate:
                used_due_ids.add(candidate.id)
                due_date, name, percent = candidate.due_date, candidate.name, candidate.percentage
                source_id = candidate.id
            elif seq_index < len(seq_pool):
                candidate = seq_pool[seq_index]
                seq_index += 1
                due_date, name, percent = window_end, candidate.name, candidate.percentage
                source_id = candidate.id
            else:
                leftover_indexes.append(len(values))
                due_date, name, percent, source_id = window_end, _('Monthly Installment'), 0.0, False

            consumed_percent += percent
            values.append({
                'sequence': sequence,
                'name': name,
                'due_date': due_date,
                'amount_type': 'percentage',
                'percentage': percent,
                'amount': self.currency_id.round(self.unit_price * percent / 100.0),
                'source_line_id': source_id,
            })
            sequence += 10

        remaining_percent = 1 - consumed_percent
        if leftover_indexes:
            each_percent = remaining_percent / len(leftover_indexes)
            for index in leftover_indexes:
                values[index]['percentage'] = each_percent
                values[index]['amount'] = self.currency_id.round(self.unit_price * each_percent / 100.0)
        elif abs(remaining_percent) > 0.01:
            raise ValidationError(_(
                'The offer template only accounts for %(percent).2f%% of the unit price and there '
                'are no remaining installments left to spread the rest over. Increase the total '
                'installments.', percent=consumed_percent))

        percentage_values = [value for value in values if value['amount_type'] == 'percentage']
        if percentage_values:
            generated_total = sum(value['amount'] for value in percentage_values)
            rounding_diff = self.unit_price - generated_total
            if rounding_diff:
                percentage_values[-1]['amount'] += rounding_diff

        self.env['property.details.offers.line'].create(
            [dict(value, offer_id=self.id) for value in values])
