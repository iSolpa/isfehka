from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    ruc = fields.Char(
        string='RUC',
        help='Registro Único de Contribuyente'
    )
    dv = fields.Char(
        string='DV',
        help='Dígito Verificador'
    )
    tipo_contribuyente = fields.Selection([
        ('1', 'Natural'),
        ('2', 'Jurídico')
    ], string='Tipo de Contribuyente', default='1')
    
    ruc_verified = fields.Boolean(
        string='RUC Verificado',
        default=False,
        readonly=True
    )
    ruc_verification_date = fields.Datetime(
        string='Fecha de Verificación',
        readonly=True
    )

    @api.constrains('ruc')
    def _check_ruc_format(self):
        for partner in self:
            if partner.ruc:
                if not partner.ruc.isdigit():
                    raise ValidationError(_('El RUC debe contener solo números'))
                if len(partner.ruc) < 8 or len(partner.ruc) > 10:
                    raise ValidationError(_('El RUC debe tener entre 8 y 10 dígitos'))

    def action_verify_ruc(self):
        """Verify RUC with HKA service"""
        self.ensure_one()
        if not self.ruc or not self.tipo_contribuyente:
            raise UserError(_('Por favor ingrese el RUC y tipo de contribuyente'))

        hka_service = self.env['hka.service']
        result = hka_service.verify_ruc(self.ruc, self.tipo_contribuyente)

        if result['success']:
            self.write({
                'ruc_verified': True,
                'ruc_verification_date': fields.Datetime.now(),
                'dv': result['data'].get('dv', ''),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _('RUC verificado exitosamente'),
                    'type': 'success',
                }
            }
        else:
            raise UserError(result['message'])

    @api.model
    def create(self, vals):
        if vals.get('ruc'):
            vals['ruc'] = vals['ruc'].strip()
        return super().create(vals)

    def write(self, vals):
        if vals.get('ruc'):
            vals['ruc'] = vals['ruc'].strip()
            vals['ruc_verified'] = False
            vals['ruc_verification_date'] = False
        return super().write(vals) 