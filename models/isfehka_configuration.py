from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class IsfehkaConfiguration(models.Model):
    _name = 'isfehka.configuration'
    _description = 'HKA Configuration Set'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    token_empresa = fields.Char(
        string='Token Empresa',
        required=True,
        copy=False,
        help='Token provisto por HKA para identificar la empresa.'
    )
    token_password = fields.Char(
        string='Token Password',
        required=True,
        copy=False,
        help='Contraseña asociada al token de la empresa en HKA.'
    )
    wsdl_url = fields.Char(
        string='WSDL URL',
        required=True,
        default=lambda self: self._default_wsdl_url(),
        help='URL del servicio SOAP de HKA.'
    )
    test_mode = fields.Boolean(
        string='Modo de Pruebas',
        default=True,
        help='Indica si esta configuración utiliza el ambiente de pruebas de HKA.'
    )
    default_tipo_documento = fields.Selection([
        ('01', 'Factura de Operación Interna'),
        ('02', 'Factura de Importación'),
        ('03', 'Factura de Exportación'),
        ('04', 'Nota de Crédito'),
        ('05', 'Nota de Débito'),
        ('06', 'Nota de Crédito Genérica'),
        ('07', 'Nota de Débito Genérica'),
        ('08', 'Factura de Zona Franca'),
        ('09', 'Factura de Reembolso')
    ], string='Tipo de Documento por Defecto', default='01')
    next_number = fields.Char(
        string='Próximo Número Fiscal',
        default='0000000001',
        copy=False,
        help='Número fiscal a utilizar en la siguiente emisión (10 dígitos).'
    )
    company_ids = fields.One2many(
        'res.company',
        'hka_configuration_id',
        string='Compañías'
    )

    @api.model
    def _default_wsdl_url(self):
        return 'https://demoemision.thefactoryhka.com.pa/ws/obj/v1.0/Service.svc?singleWsdl'

    @api.constrains('next_number')
    def _check_next_number(self):
        for record in self:
            if record.next_number:
                if not record.next_number.isdigit():
                    raise ValidationError(_('El número fiscal debe contener solo dígitos.'))
                if len(record.next_number) != 10:
                    raise ValidationError(_('El número fiscal debe tener exactamente 10 dígitos.'))
                if int(record.next_number) < 1:
                    raise ValidationError(_('El número fiscal debe ser mayor que 0.'))

    def get_and_increment_next_number(self):
        self.ensure_one()
        if not self.next_number:
            raise UserError(_('Configure un próximo número fiscal en la configuración de HKA.'))

        table = self._table
        self.env.cr.execute(f"SELECT next_number FROM {table} WHERE id = %s FOR UPDATE NOWAIT", [self.id])
        row = self.env.cr.fetchone()
        if not row or not row[0]:
            raise UserError(_('No se encontró el próximo número fiscal configurado.'))

        next_number = row[0]
        if not next_number.isdigit():
            raise UserError(_('El número fiscal configurado no es válido.'))

        new_number = str(int(next_number) + 1).zfill(10)
        self.env.cr.execute(f"UPDATE {table} SET next_number = %s WHERE id = %s", [new_number, self.id])
        self.env.cr.commit()
        self.invalidate_recordset(['next_number'])
        return next_number
