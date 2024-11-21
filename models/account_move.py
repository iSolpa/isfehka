from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class AccountMove(models.Model):
    _inherit = 'account.move'

    # HKA Fields
    hka_status = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviado'),
        ('cancelled', 'Anulado'),
        ('error', 'Error')
    ], string='Estado HKA', default='draft', tracking=True)

    hka_cufe = fields.Char(
        string='CUFE',
        readonly=True,
        help='Código Único de Factura Electrónica'
    )

    numero_documento_fiscal = fields.Char(
        string='Número Documento Fiscal',
        readonly=True,
        size=10,
        help='Número del documento fiscal asignado por HKA'
    )

    hka_message = fields.Text(
        string='Mensaje HKA',
        readonly=True
    )

    tipo_documento = fields.Selection([
        ('01', 'Factura de Operación Interna'),
        ('02', 'Factura de Importación'),
        ('03', 'Factura de Exportación'),
        ('04', 'Nota de Crédito'),
        ('05', 'Nota de Débito'),
        ('06', 'Nota de Crédito Genérica'),
        ('07', 'Nota de Débito Genérica'),
        ('08', 'Factura de Zona Franca'),
        ('09', 'Factura de Reembolso')
    ], string='Tipo de Documento', default='01', required=True)

    naturaleza_operacion = fields.Selection([
        ('01', 'Venta'),
        ('02', 'Exportación'),
        ('03', 'Transferencia'),
        ('04', 'Devolución')
    ], string='Naturaleza de Operación', default='01')

    motivo_anulacion = fields.Text(
        string='Motivo de Anulación',
        help='Razón por la cual se anula el documento'
    )

    @api.constrains('partner_id')
    def _check_partner_ruc(self):
        for move in self:
            if move.move_type in ('out_invoice', 'out_refund'):
                if not move.partner_id.ruc_verified:
                    raise ValidationError(_('El RUC del cliente debe estar verificado antes de crear una factura electrónica.'))

    def action_post(self):
        """Override to send invoice to HKA when posting"""
        res = super().action_post()
        for move in self.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund')):
            move._send_to_hka()
        return res

    def _send_to_hka(self):
        """Send invoice to HKA"""
        self.ensure_one()
        if self.hka_status == 'sent':
            raise UserError(_('Esta factura ya ha sido enviada a HKA'))

        # Validate required data before sending
        self._validate_hka_data()

        # Get the next fiscal number if needed
        if not self.numero_documento_fiscal:
            fiscal_number = self._get_next_fiscal_number()
            if not fiscal_number:
                raise UserError(_('No se pudo obtener el próximo número fiscal.'))
            self.numero_documento_fiscal = fiscal_number

        try:
            hka_service = self.env['hka.service']
            invoice_data = self._prepare_hka_data()
            result = hka_service.send_invoice(invoice_data)

            if result['success']:
                self.write({
                    'hka_status': 'sent',
                    'hka_cufe': result['data'].get('cufe', ''),
                    'hka_message': _('Documento enviado exitosamente')
                })
            else:
                self.write({
                    'hka_status': 'error',
                    'hka_message': result['message']
                })
                raise UserError(result['message'])

        except Exception as e:
            self.write({
                'hka_status': 'error',
                'hka_message': str(e)
            })
            raise UserError(str(e))

    def action_cancel_hka(self):
        """Cancel document in HKA"""
        self.ensure_one()
        if not self.motivo_anulacion:
            raise UserError(_('Debe especificar el motivo de anulación'))

        if self.hka_status != 'sent':
            raise UserError(_('Solo se pueden anular documentos enviados'))

        try:
            hka_service = self.env['hka.service']
            cancel_data = self._prepare_cancel_data()
            result = hka_service.cancel_document(cancel_data)

            if result['success']:
                self.write({
                    'hka_status': 'cancelled',
                    'hka_message': _('Documento anulado exitosamente')
                })
            else:
                raise UserError(result['message'])

        except Exception as e:
            raise UserError(str(e))

    def _get_hka_branch(self):
        """Get the branch code to use for HKA integration"""
        self.ensure_one()
        
        if not self.company_id.hka_branch_code:
            raise UserError(_('Please configure an HKA Branch Code in company settings'))
        return self.company_id.hka_branch_code

    def _get_hka_pos_code(self):
        """Get the POS code to use for HKA integration"""
        self.ensure_one()
        
        # If invoice comes from POS
        if hasattr(self, 'pos_order_ids') and self.pos_order_ids:
            pos_config = self.pos_order_ids[0].config_id
            if pos_config.hka_pos_code:
                return pos_config.hka_pos_code

        # Fallback to company's POS code
        if not self.company_id.hka_pos_code:
            raise UserError(_('Please configure an HKA POS Code in company settings'))
        return self.company_id.hka_pos_code

    def _prepare_hka_data(self):
        """Prepare invoice data for HKA"""
        self.ensure_one()
        branch = self._get_hka_branch()
            
        return {
            'documento': {
                'codigoSucursalEmisor': branch,
                'tipoSucursal': '1',
                'datosTransaccion': {
                    'tipoEmision': '01',
                    'tipoDocumento': self.tipo_documento,
                    'numeroDocumentoFiscal': self.numero_documento_fiscal,
                    'puntoFacturacionFiscal': self._get_hka_pos_code(),
                    'naturalezaOperacion': self.naturaleza_operacion,
                    'tipoOperacion': '1',
                    'destinoOperacion': '1' if self.partner_id.country_id.code == 'PA' else '2',
                    'formatoCAFE': '1',
                    'entregaCAFE': '1',
                    'envioContenedor': '1',
                    'procesoGeneracion': '1',
                    'tipoVenta': '1',
                    'fechaEmision': fields.Datetime.now().strftime('%Y-%m-%dT%H:%M:%S-05:00'),
                    'cliente': self._prepare_hka_client_data(),
                },
                'listaItems': {
                    'item': self._prepare_hka_items_data()
                },
                'totalesSubTotales': self._prepare_hka_totals_data()
            }
        }

    def _get_next_fiscal_number(self):
        """Get and increment the next fiscal number using SQL for concurrency control."""
        self.ensure_one()
        if self.hka_status != 'draft':
            return False

        self.env.cr.execute("""
            SELECT value FROM ir_config_parameter 
            WHERE key = 'isfehka.next_number' 
            FOR UPDATE NOWAIT
        """)
        current_number = self.env.cr.fetchone()
        if not current_number:
            raise UserError(_('No se ha configurado el próximo número fiscal en los ajustes de HKA.'))
        
        next_number = current_number[0]
        # Update the next number
        new_number = str(int(next_number) + 1).zfill(10)
        self.env.cr.execute("""
            UPDATE ir_config_parameter 
            SET value = %s 
            WHERE key = 'isfehka.next_number'
        """, [new_number])
        
        return next_number

    def _prepare_hka_client_data(self):
        """Prepare client data for HKA"""
        partner = self.partner_id
        # Construct location code using IDs with dashes
        codigo_ubicacion = f"{partner.state_id.code or '0'}-{partner.l10n_pa_distrito_id.code or '0'}-{partner.l10n_pa_corregimiento_id.code or '0'}"
        
        return {
            'tipoClienteFE': '02' if partner.tipo_contribuyente == '1' else '01',
            'tipoContribuyente': partner.tipo_contribuyente,
            'numeroRUC': partner.ruc,
            'digitoVerificadorRUC': str(partner.dv).zfill(2),  # Ensure 2 digits with left padding
            'razonSocial': partner.name,
            'direccion': partner.street,
            'codigoUbicacion': codigo_ubicacion,
            'provincia': partner.state_id.name,
            'distrito': partner.l10n_pa_distrito_id.name,
            'corregimiento': partner.l10n_pa_corregimiento_id.name,
            'correoElectronico1': partner.email or '',
            'telefono1': partner.phone or '',
            'pais': 'PA',
        }

    def _prepare_hka_items_data(self):
        """Prepare invoice lines data for HKA"""
        items = []
        for line in self.invoice_line_ids:
            # Format numeric values according to HKA specifications
            cantidad = '{:.3f}'.format(line.quantity)  # N|13,3 format
            precio_unitario = '{:.3f}'.format(line.price_unit)  # N|13,3 format
            precio_item = '{:.2f}'.format(line.price_subtotal)  # N|13,2 format
            valor_total = '{:.2f}'.format(line.price_total)  # N|13,2 format
            valor_itbms = '{:.2f}'.format(line.price_total - line.price_subtotal)  # N|13,2 format

            items.append({
                'descripcion': line.name,
                'cantidad': cantidad,
                'precioUnitario': precio_unitario,
                'precioUnitarioDescuento': '',
                'precioItem': precio_item,
                'valorTotal': valor_total,
                'codigoGTIN': line.product_id.barcode or '0',
                'tasaITBMS': self._get_tax_rate(line),
                'valorITBMS': valor_itbms,
            })
        return items

    def _prepare_hka_totals_data(self):
        """Prepare totals data for HKA"""
        return {
            'totalPrecioNeto': '{:.2f}'.format(self.amount_untaxed),  # N|13,2 format
            'totalITBMS': '{:.2f}'.format(self.amount_tax),  # N|13,2 format
            'totalISC': '0.00',  # Required field, set to 0
            'totalMontoGravado': '{:.2f}'.format(self.amount_tax),  # N|13,2 format
            'totalFactura': '{:.2f}'.format(self.amount_total),  # N|13,2 format
            'totalValorRecibido': '{:.2f}'.format(self.amount_total),  # N|13,2 format
            'vuelto': '0.00',
            'tiempoPago': '1',
            'nroItems': str(len(self.invoice_line_ids)),
            'totalTodosItems': '{:.2f}'.format(self.amount_total),  # N|13,2 format
            'listaFormaPago': {
                'formaPago': [{
                    'formaPagoFact': '02',  # Fixed as 'Efectivo' for now
                    'descFormaPago': '',
                    'valorCuotaPagada': '{:.2f}'.format(self.amount_total)  # N|13,2 format
                }]
            }
        }

    def _prepare_cancel_data(self):
        """Prepare cancellation data for HKA"""
        return {
            'datosDocumento': {
                'codigoSucursalEmisor': self._get_hka_branch(),
                'numeroDocumentoFiscal': self.numero_documento_fiscal,
                'puntoFacturacionFiscal': self._get_hka_pos_code(),
                'tipoDocumento': self.tipo_documento,
                'tipoEmision': '01',
            },
            'motivoAnulacion': self.motivo_anulacion,
        }

    def _get_tax_rate(self, line):
        """Get ITBMS tax rate for invoice line"""
        for tax in line.tax_ids:
            if tax.amount == 7:
                return '01'
            elif tax.amount == 10:
                return '02'
            elif tax.amount == 15:
                return '03'
        return '00' 

    def _prepare_hka_document(self):
        """Prepare the document for HKA submission."""
        self.ensure_one()
        
        # Only get a new number if we don't already have one
        if not self.numero_documento_fiscal:
            fiscal_number = self._get_next_fiscal_number()
            if not fiscal_number:
                raise UserError(_('No se pudo obtener el próximo número fiscal.'))
            self.numero_documento_fiscal = fiscal_number
        
        # Continue with existing preparation logic

    def _validate_hka_data(self):
        """Validate required data before sending to HKA"""
        self.ensure_one()
        partner = self.partner_id
        errors = []

        # Validate partner data
        if not partner.tipo_contribuyente:
            errors.append(_('El tipo de contribuyente del cliente es requerido.'))
        if not partner.ruc:
            errors.append(_('El RUC del cliente es requerido.'))
        if not partner.dv:
            errors.append(_('El dígito verificador del cliente es requerido.'))
        if not partner.name:
            errors.append(_('La razón social del cliente es requerida.'))
        if not partner.street:
            errors.append(_('La dirección del cliente es requerida.'))
        
        # Validate location data
        if not partner.state_id:
            errors.append(_('La provincia del cliente es requerida.'))
        if not partner.l10n_pa_distrito_id:
            errors.append(_('El distrito del cliente es requerido.'))
        if not partner.l10n_pa_corregimiento_id:
            errors.append(_('El corregimiento del cliente es requerido.'))

        # Validate invoice data
        if not self.invoice_line_ids:
            errors.append(_('La factura debe tener al menos una línea.'))
        
        if errors:
            raise ValidationError('\n'.join(errors))