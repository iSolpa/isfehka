from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMoveCancelReason(models.TransientModel):
    _name = 'account.move.cancel.reason'
    _description = 'Invoice Cancellation Reason'

    move_id = fields.Many2one('account.move', string='Invoice', required=True)
    motivo_anulacion = fields.Text(string='Motivo de Anulación', required=True)

    def action_confirm_cancel(self):
        self.ensure_one()
        if not self.motivo_anulacion:
            raise UserError(_('Debe especificar el motivo de anulación'))

        # Write the reason first
        self.move_id.write({'motivo_anulacion': self.motivo_anulacion})
        # Then call the cancel action
        return self.move_id.action_cancel_hka()
