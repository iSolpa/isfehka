from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    hka_branch_code = fields.Char(
        string='HKA Branch Code',
        default='0000',
        size=10,
        help='Branch code for HKA integration (up to 10 digits)'
    )

    hka_pos_code = fields.Char(
        string='HKA POS Code',
        default='001',
        size=10,
        help='Default Point of Sale code for HKA integration (up to 10 digits). Used when POS module is not installed.'
    )

    hka_default_tipo_documento = fields.Selection([
        ('01', 'Factura de Operación Interna'),
        ('02', 'Factura de Importación'),
        ('03', 'Factura de Exportación'),
        ('04', 'Nota de Crédito'),
        ('05', 'Nota de Débito'),
        ('06', 'Nota de Crédito Genérica'),
        ('07', 'Nota de Débito Genérica'),
        ('08', 'Factura de Zona Franca'),
        ('09', 'Factura de Reembolso')
    ], string='Tipo de Documento por Defecto',
       default='01',
       help='Tipo de documento por defecto para facturas electrónicas de esta compañía'
    )

    @api.constrains('hka_branch_code', 'hka_pos_code')
    def _check_hka_codes(self):
        for company in self:
            if company.hka_branch_code and (not company.hka_branch_code.isdigit() or len(company.hka_branch_code) < 1 or len(company.hka_branch_code) > 10):
                raise ValidationError(_('HKA Branch Code must be between 1 and 10 digits'))
            if company.hka_pos_code and (not company.hka_pos_code.isdigit() or len(company.hka_pos_code) < 1 or len(company.hka_pos_code) > 10):
                raise ValidationError(_('HKA POS Code must be between 1 and 10 digits'))