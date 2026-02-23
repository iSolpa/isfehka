from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountMoveRegisterHka(models.TransientModel):
    _name = 'account.move.register.hka'
    _description = 'Register Existing HKA Document'

    move_id = fields.Many2one('account.move', string='Invoice', required=True)
    numero_documento_fiscal = fields.Char(
        string='Número Documento Fiscal',
        required=True,
        size=10,
        help='Número del documento fiscal asignado por HKA'
    )
    hka_cufe = fields.Char(
        string='CUFE',
        required=True,
        help='Código Único de Factura Electrónica'
    )
    tipo_documento = fields.Selection(
        related='move_id.tipo_documento',
        string='Tipo de Documento',
        readonly=False,
    )
    naturaleza_operacion = fields.Selection(
        related='move_id.naturaleza_operacion',
        string='Naturaleza de Operación',
        readonly=False,
    )

    @api.constrains('numero_documento_fiscal')
    def _check_numero_documento_fiscal(self):
        for record in self:
            if record.numero_documento_fiscal:
                if not record.numero_documento_fiscal.isdigit():
                    raise UserError(_('El número de documento fiscal debe contener solo dígitos.'))
                if len(record.numero_documento_fiscal) != 10:
                    raise UserError(_('El número de documento fiscal debe tener exactamente 10 dígitos.'))

    def action_confirm_register(self):
        self.ensure_one()
        if not self.hka_cufe:
            raise UserError(_('Debe especificar el CUFE del documento.'))
        if not self.numero_documento_fiscal:
            raise UserError(_('Debe especificar el número de documento fiscal.'))

        move = self.move_id
        if move.hka_status == 'sent':
            raise UserError(_('Esta factura ya está registrada como enviada a HKA.'))
        if move.state != 'posted':
            raise UserError(_('La factura debe estar confirmada antes de registrar el documento HKA.'))

        vals = {
            'hka_status': 'sent',
            'hka_cufe': self.hka_cufe,
            'numero_documento_fiscal': self.numero_documento_fiscal,
            'hka_message': _('Documento registrado manualmente — ya existía en el portal fiscal.'),
        }
        # Write tipo_documento and naturaleza_operacion if set on wizard
        if self.tipo_documento:
            vals['tipo_documento'] = self.tipo_documento
        if self.naturaleza_operacion:
            vals['naturaleza_operacion'] = self.naturaleza_operacion

        move.write(vals)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Documento Registrado'),
                'message': _('El documento fiscal ha sido registrado exitosamente en Odoo.'),
                'sticky': False,
                'type': 'success',
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
