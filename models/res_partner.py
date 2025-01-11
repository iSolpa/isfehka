from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class ResPartner(models.Model):
    _inherit = 'res.partner'

    country_id = fields.Many2one(
        'res.country',
        string='Country',
        default=lambda self: self.env.ref('base.pa', raise_if_not_found=False) or 172
    )

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
    
    tipo_cliente_fe = fields.Selection([
        ('01', 'Contribuyente'),
        ('02', 'Consumidor Final'),
        ('03', 'Gobierno'),
        ('04', 'Extranjero')
    ], string='Tipo de Cliente FE',
        help='Tipo de receptor de la Factura Electrónica')

    ruc_verified = fields.Boolean(
        string='RUC Verificado',
        default=False,
        readonly=False
    )
    ruc_verification_date = fields.Datetime(
        string='Fecha de Verificación',
        readonly=False
    )

    # Location Fields
    l10n_pa_distrito_id = fields.Many2one('res.distrito.pa', 'Distrito',
        domain="[('state_id', '=', state_id)]")
    l10n_pa_corregimiento_id = fields.Many2one('res.corregimiento.pa', 'Corregimiento',
        domain="[('distrito_id', '=', l10n_pa_distrito_id)]")
    codigo_ubicacion = fields.Char('Código de Ubicación', compute='_compute_codigo_ubicacion', store=True)

    @api.depends('state_id', 'l10n_pa_distrito_id', 'l10n_pa_corregimiento_id')
    def _compute_codigo_ubicacion(self):
        """Compute location code in format provincia-distrito-corregimiento"""
        for partner in self:
            if partner.state_id and partner.l10n_pa_distrito_id and partner.l10n_pa_corregimiento_id:
                partner.codigo_ubicacion = f"{partner.state_id.code}-{partner.l10n_pa_distrito_id.code}-{partner.l10n_pa_corregimiento_id.code}"
            else:
                partner.codigo_ubicacion = False

    @api.onchange('state_id')
    def _onchange_state_id(self):
        """Clear distrito and corregimiento when provincia changes"""
        self.l10n_pa_distrito_id = False
        self.l10n_pa_corregimiento_id = False

    @api.onchange('l10n_pa_distrito_id')
    def _onchange_distrito_id(self):
        """Clear corregimiento when distrito changes"""
        self.l10n_pa_corregimiento_id = False

    @api.onchange('country_id')
    def _onchange_country_id(self):
        """Set tipo_cliente_fe to Extranjero when country is not Panama"""
        if self.country_id and self.country_id.code != 'PA':
            self.tipo_cliente_fe = '04'  # Extranjero
        elif self.tipo_cliente_fe == '04':
            self.tipo_cliente_fe = '02'  # Default back to Consumidor Final

    @api.onchange('tipo_contribuyente', 'ruc')
    def _onchange_contribuyente_data(self):
        """Update tipo_cliente_fe when tipo_contribuyente or RUC changes"""
        if self.tipo_contribuyente == '2' or (self.tipo_contribuyente == '1' and self.ruc):
            self.tipo_cliente_fe = '01'  # Contribuyente
        elif self.tipo_cliente_fe == '01':
            self.tipo_cliente_fe = '02'  # Default back to Consumidor Final

    @api.constrains('ruc')
    def _check_ruc_format(self):
        """Check RUC format, allowing special case for Consumidor Final"""
        for partner in self:
            if partner.ruc:
                if partner.ruc == 'CF':  # Special case for Consumidor Final
                    continue
                # Remove hyphens and spaces for validation
                ruc_clean = partner.ruc.replace('-', '').replace(' ', '')
                # Extract the base RUC number (before any hyphens)
                base_ruc = ruc_clean.split('-')[0] if '-' in partner.ruc else ruc_clean
                if not base_ruc.isdigit():
                    raise ValidationError(_('El RUC debe contener solo números, guiones y espacios'))
                if len(base_ruc) < 1 or len(base_ruc) > 20:
                    raise ValidationError(_('El número base del RUC debe tener entre 1 y 20 dígitos'))

    def action_verify_ruc(self):
        """Verify RUC with HKA service"""
        self.ensure_one()
        
        # Skip verification for Consumidor Final
        if self.ruc == 'CF':  
            self.write({
                'ruc_verified': True,
                'ruc_verification_date': fields.Datetime.now(),
                'dv': '00',
                'tipo_cliente_fe': '02',  
                'name': 'CONSUMIDOR FINAL',  
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _('Cliente Consumidor Final verificado'),
                    'type': 'success',
                }
            }

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('ruc'):
                vals['ruc'] = vals['ruc'].strip()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('ruc'):
            vals['ruc'] = vals['ruc'].strip()
            # Only reset verification fields if they're not being explicitly set
            if 'ruc_verified' not in vals:
                vals['ruc_verified'] = False
            if 'ruc_verification_date' not in vals:
                vals['ruc_verification_date'] = False
        return super().write(vals) 
