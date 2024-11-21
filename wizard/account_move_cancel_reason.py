from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMoveCancelReason(models.TransientModel):
    _name = 'account.move.cancel.reason'
    _description = 'Invoice Cancellation Reason'

    move_id = fields.Many2one('account.move', string='Invoice', required=True)
    motivo_anulacion = fields.Text(string='Motivo de Anulación', required=True)

    @api.constrains('motivo_anulacion')
    def _check_motivo_anulacion_length(self):
        for record in self:
            if record.motivo_anulacion and (len(record.motivo_anulacion) < 15 or len(record.motivo_anulacion) > 1000):
                raise UserError(_('El motivo de anulación debe tener entre 15 y 1000 caracteres.'))

    def action_confirm_cancel(self):
        self.ensure_one()
        if not self.motivo_anulacion:
            raise UserError(_('Debe especificar el motivo de anulación'))
        if len(self.motivo_anulacion) < 15 or len(self.motivo_anulacion) > 1000:
            raise UserError(_('El motivo de anulación debe tener entre 15 y 1000 caracteres.'))

        # Write the reason first
        self.move_id.write({'motivo_anulacion': self.motivo_anulacion})
        # Then call the cancel action
        return self.move_id.action_cancel_hka()
