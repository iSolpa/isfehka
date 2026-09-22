"""FE pending notice (opt-in).

Since a failed POS FE no longer discards the sale (the posted invoice is kept with
hka_status='error'), the cashier sees no error. This lists/notifies customer invoices
whose FE was never accepted so staff can resend them (button_send_to_hka).

Everything here is inert by default:
  * the cron ``isfehka.ir_cron_fe_notice`` ships INACTIVE;
  * nothing is sent to HKA/DGI -- the cron only creates/closes mail.activity records.
Config (ir.config_parameter, all optional):
  * isfehka.fe_notice_user_id  -- res.users id that receives the activities
                                  (fallback: first isfehka Administrador user)
  * isfehka.fe_notice_since    -- YYYY-MM-DD; ignore invoices dated before this
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

FE_NOTICE_SUMMARY = 'FE pendiente de envío'
FE_NOTICE_MIN_AGE_MINUTES = 30


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.model
    def _isfehka_fe_pending_domain(self):
        """Posted customer invoices/refunds whose FE was never accepted.

        'draft' is included on purpose: a failed back-office send leaves the invoice
        in hka_status='draft' (only POS / auto-send mark 'error'). Invoices without a
        tipo_documento are not FE documents and are ignored.
        """
        return [
            ('state', '=', 'posted'),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('hka_status', 'in', ('draft', 'error')),
            ('tipo_documento', '!=', False),
        ]

    @api.model
    def _isfehka_fe_notice_user(self):
        ICP = self.env['ir.config_parameter'].sudo()
        user = self.env['res.users']
        uid = ICP.get_param('isfehka.fe_notice_user_id')
        if uid and str(uid).isdigit():
            user = user.browse(int(uid)).exists().filtered('active')
        if not user:
            group = self.env.ref('isfehka.group_isfehka_manager', raise_if_not_found=False)
            if group:
                user = group.user_ids.filtered(lambda u: u.active and not u.share).sorted('id')[:1]
        return user

    @api.model
    def _cron_isfehka_fe_notice(self):
        """Create one to-do activity per pending FE invoice; close ours once resolved."""
        todo_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not todo_type:
            return
        Activity = self.env['mail.activity'].sudo()
        ours = [
            ('res_model', '=', 'account.move'),
            ('activity_type_id', '=', todo_type.id),
            ('summary', '=', FE_NOTICE_SUMMARY),
        ]

        # 1) Close our activities whose invoice is no longer pending (sent, cancelled, reset...).
        open_acts = Activity.search(ours)
        if open_acts:
            still_pending = set(self.sudo().search(
                self._isfehka_fe_pending_domain() + [('id', 'in', open_acts.mapped('res_id'))]
            ).ids)
            resolved = open_acts.filtered(lambda a: a.res_id not in still_pending)
            if resolved:
                resolved.action_feedback(feedback='FE resuelta')

        # 2) Notify new pending invoices (older than a few minutes, not already notified).
        user = self._isfehka_fe_notice_user()
        if not user:
            _logger.warning('isfehka FE notice: no responsible user configured; skipping.')
            return
        domain = self._isfehka_fe_pending_domain() + [
            ('create_date', '<', fields.Datetime.now() - timedelta(minutes=FE_NOTICE_MIN_AGE_MINUTES)),
        ]
        since = self.env['ir.config_parameter'].sudo().get_param('isfehka.fe_notice_since')
        if since:
            domain.append(('invoice_date', '>=', since))
        already = set(Activity.search(ours).mapped('res_id'))
        moves = self.sudo().search(domain, order='invoice_date, id').filtered(lambda m: m.id not in already)
        for move in moves:
            note = move.hka_message or ''
            move.with_context(mail_activity_quick_update=True).activity_schedule(
                'mail.mail_activity_data_todo',
                summary=FE_NOTICE_SUMMARY,
                note=note[:500],
                user_id=user.id,
            )
        if moves:
            _logger.info('isfehka FE notice: %s pending FE invoice(s) notified to %s', len(moves), user.login)
