from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class PosConfig(models.Model):
    _inherit = 'pos.config'

    hka_pos_code = fields.Char(
        string='HKA POS Code',
        default='001',
        size=10,
        help='Point of Sale code for HKA integration (up to 10 digits)'
    )

    use_hka_pdf_receipt = fields.Boolean(
        string='Use HKA PDF Receipt',
        default=False,
        help='When enabled, the POS will use the PDF receipt from HKA instead of the default receipt format'
    )

    hka_tipo_documento = fields.Selection([
        ('01', 'Factura de Operación Interna'),
        ('02', 'Factura de Importación'),
        ('03', 'Factura de Exportación'),
        ('04', 'Nota de Crédito'),
        ('05', 'Nota de Débito'),
        ('06', 'Nota de Crédito Genérica'),
        ('07', 'Nota de Débito Genérica'),
        ('08', 'Factura de Zona Franca'),
        ('09', 'Factura de Reembolso')
    ], string='Tipo de Documento por Defecto', default='01', required=True,
        help='Tipo de documento por defecto para facturas generadas desde este punto de venta')

    hka_naturaleza_operacion = fields.Selection([
        ('01', 'Venta'),
        ('02', 'Exportación'),
        ('03', 'Transferencia'),
        ('04', 'Devolución')
    ], string='Naturaleza de Operación por Defecto', default='01', required=True,
        help='Naturaleza de operación por defecto para facturas generadas desde este punto de venta')

    @api.constrains('hka_pos_code')
    def _check_hka_pos_code(self):
        for config in self:
            if config.hka_pos_code and (not config.hka_pos_code.isdigit() or len(config.hka_pos_code) < 1 or len(config.hka_pos_code) > 10):
                raise ValidationError(_('HKA POS Code must be between 1 and 10 digits'))