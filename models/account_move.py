from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import base64
import logging

_logger = logging.getLogger(__name__)

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

    hka_pdf = fields.Binary(
        string='PDF HKA',
        readonly=True,
        attachment=True,
        help='PDF del documento fiscal'
    )

    hka_pdf_filename = fields.Char(
        string='Nombre PDF HKA',
        readonly=True
    )

    hka_xml = fields.Binary(
        string='XML HKA',
        readonly=True,
        attachment=True,
        help='XML del documento fiscal'
    )

    hka_xml_filename = fields.Char(
        string='Nombre XML HKA',
        readonly=True
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

    @api.constrains('tipo_documento', 'reversed_entry_id')
    def _check_credit_note_reference(self):
        for move in self:
            if move.tipo_documento == '04' and not move.reversed_entry_id:
                raise ValidationError(_('Debe seleccionar una factura a la cual aplicar la nota de crédito.'))

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
                # First save the basic response data
                self.env.cr.commit()  # Commit the transaction to ensure we don't lose the CUFE
                self.write({
                    'hka_status': 'sent',
                    'hka_cufe': result['data'].get('cufe', ''),
                    'hka_message': _('Documento enviado exitosamente'),
                })
                self.env.cr.commit()  # Commit the transaction to ensure we don't lose the status

                try:
                    # Then handle PDF and XML files with proper filenames
                    pdf_filename = f'FACT_{self.numero_documento_fiscal}.pdf'
                    xml_filename = f'FACT_{self.numero_documento_fiscal}.xml'
                    
                    if result.get('pdf'):
                        self.write({
                            'hka_pdf': base64.b64encode(result['pdf']),
                            'hka_pdf_filename': pdf_filename,
                        })
                        self.env.cr.commit()  # Commit PDF separately

                    if result.get('xml'):
                        self.write({
                            'hka_xml': base64.b64encode(result['xml']),
                            'hka_xml_filename': xml_filename,
                        })
                        self.env.cr.commit()  # Commit XML separately

                except Exception as e:
                    _logger.error('Error saving PDF/XML files: %s', str(e))
                    # Don't raise the error since we already have the CUFE and status
                    self.write({
                        'hka_message': _('Documento enviado pero hubo un error al guardar PDF/XML: %s') % str(e)
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

    def button_cancel_hka(self):
        """Open the cancellation reason wizard"""
        self.ensure_one()
        if self.hka_status != 'sent':
            raise UserError(_('Solo se pueden anular documentos enviados'))

        return {
            'name': _('Motivo de Anulación'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.cancel.reason',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_id': self.id,
            }
        }

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
            
        data = {
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
                    'tipoVenta': '',
                    'fechaEmision': fields.Datetime.now().strftime('%Y-%m-%dT%H:%M:%S-05:00'),
                    'fechaSalida': fields.Datetime.now().strftime('%Y-%m-%dT%H:%M:%S-05:00'),
                    'cliente': self._prepare_hka_client_data(),
                },
                'listaItems': {
                    'item': self._prepare_hka_items_data()
                },
                'totalesSubTotales': self._prepare_hka_totals_data()
            }
        }

        # Add referenced document data for credit notes
        if self.tipo_documento == '04' and self.reversed_entry_id:
            if not self.reversed_entry_id.hka_cufe:
                raise UserError(_('La factura referenciada debe tener un CUFE válido'))

            data['documento']['datosTransaccion']['informacionInteres'] = 'Factura de nota de credito referenciada'
            data['documento']['datosTransaccion']['listaDocsFiscalReferenciados'] = {
                'docFiscalReferenciado': [{
                    'fechaEmisionDocFiscalReferenciado': self.reversed_entry_id.invoice_date.strftime('%Y-%m-%dT%H:%M:%S-05:00'),
                    'cufeFEReferenciada': self.reversed_entry_id.hka_cufe,
                    'nroFacturaPapel': '',
                    'nroFacturaImpFiscal': '',
                }]
            }

        return data

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
        # Update the next number immediately
        new_number = str(int(next_number) + 1).zfill(10)
        self.env.cr.execute("""
            UPDATE ir_config_parameter 
            SET value = %s 
            WHERE key = 'isfehka.next_number'
        """, [new_number])
        self.env.cr.commit()  # Commit the transaction to ensure the number is updated
        
        return next_number

    def _prepare_hka_client_data(self):
        """Prepare client data for HKA"""
        partner = self.partner_id
        
        # Special case for Consumidor Final
        if partner.ruc == 'CF' and partner.name == 'CONSUMIDOR FINAL':
            return {
                'tipoClienteFE': '02',
                'razonSocial': 'CONSUMIDOR FINAL',
                'direccion': partner.street or 'Ciudad de Panama',
                'telefono1': partner.phone or '235-2352',
                'correoElectronico1': partner.email or '',
                'pais': 'PA',
            }
        
        # Regular case
        codigo_ubicacion = f"{partner.state_id.code or '0'}-{partner.l10n_pa_distrito_id.code or '0'}-{partner.l10n_pa_corregimiento_id.code or '0'}"
        
        return {
            'tipoClienteFE': partner.tipo_cliente_fe,
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
            # Skip lines with quantity 0
            if not line.quantity:
                continue

            # Format numeric values according to HKA specifications
            cantidad = '{:.3f}'.format(line.quantity)  # N|13,3 format
            precio_unitario = '{:.3f}'.format(line.price_unit)  # N|13,3 format
            
            # Calculate line discount
            precio_unitario_descuento = '0.000'
            if line.discount:
                discount_amount = (line.price_unit * line.discount) / 100
                precio_unitario_descuento = '{:.3f}'.format(discount_amount)
            
            # Calculate price after discount per unit
            price_after_discount = line.price_unit - float(precio_unitario_descuento)
            
            # Calculate total price for the line (quantity × price after discount)
            precio_item = '{:.2f}'.format(price_after_discount * line.quantity)
            
            # Calculate total value including taxes
            valor_total = '{:.2f}'.format(line.price_total)  # Price including taxes
            valor_itbms = '{:.2f}'.format(line.price_total - line.price_subtotal)  # Tax amount

            items.append({
                'descripcion': line.name,
                'cantidad': cantidad,
                'precioUnitario': precio_unitario,
                'precioUnitarioDescuento': precio_unitario_descuento,
                'precioItem': precio_item,
                'valorTotal': valor_total,
                'tasaITBMS': self._get_tax_rate(line),
                'valorITBMS': valor_itbms,
            })
        return items

    def _prepare_hka_totals_data(self):
        """Prepare totals data for HKA"""
        # Calculate line discounts
        total_line_discounts = sum(
            (line.price_unit * line.quantity * line.discount / 100)
            for line in self.invoice_line_ids.filtered(lambda l: l.quantity > 0)
        )
        
        # Get global discounts from global discount module if installed
        total_global_discounts = 0.0
        if hasattr(self, 'global_discount_ids'):
            # Global discounts are applied after line discounts
            base_for_global = self.amount_untaxed + total_line_discounts
            total_global_discounts = sum(
                (base_for_global * disc.discount / 100)
                for disc in self.global_discount_ids
            )
        
        total_discounts = total_line_discounts + total_global_discounts
        
        # Calculate total price before any discounts
        total_precio_neto = self.amount_untaxed + total_discounts
        
        data = {
            'totalPrecioNeto': '{:.2f}'.format(total_precio_neto),  # Price before any discounts
            'totalITBMS': '{:.2f}'.format(self.amount_tax),  # N|13,2 format
            'totalMontoGravado': '{:.2f}'.format(self.amount_tax),  # N|13,2 format
            'totalDescuento': '{:.2f}'.format(total_discounts) if total_discounts > 0 else '',  # Only include if there are discounts
            'totalFactura': '{:.2f}'.format(self.amount_total),  # N|13,2 format
            'totalValorRecibido': '{:.2f}'.format(self.amount_total),  # N|13,2 format
            'vuelto': '0.00',
            'tiempoPago': '1',
            'nroItems': str(len(self.invoice_line_ids.filtered(lambda l: l.quantity > 0))),
            'totalTodosItems': '{:.2f}'.format(self.amount_total),  # N|13,2 format
            'listaFormaPago': {
                'formaPago': [{
                    'formaPagoFact': '02',  # Fixed as 'Efectivo' for now
                    'descFormaPago': '',
                    'valorCuotaPagada': '{:.2f}'.format(self.amount_total)  # N|13,2 format
                }]
            }
        }
        
        # Add global discounts list if any exist
        if hasattr(self, 'global_discount_ids') and self.global_discount_ids:
            base_for_global = self.amount_untaxed + total_line_discounts
            data['listaDescBonificacion'] = {
                'descuentoBonificacion': [
                    {
                        'descDescuento': disc.name,
                        'montoDescuento': '{:.2f}'.format(base_for_global * disc.discount / 100)
                    }
                    for disc in self.global_discount_ids
                ]
            }
        
        return data

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

        # Validate credit note specific data
        if self.tipo_documento == '04':
            if not self.reversed_entry_id:
                errors.append(_('Debe seleccionar una factura a la cual aplicar la nota de crédito.'))
            elif not self.reversed_entry_id.hka_cufe:
                errors.append(_('La factura referenciada debe tener un CUFE válido.'))
            elif self.reversed_entry_id.hka_status != 'sent':
                errors.append(_('La factura referenciada debe estar en estado Enviado.'))
            elif self.reversed_entry_id.tipo_documento not in ['01', '02', '03', '08']:
                errors.append(_('La factura referenciada debe ser una factura (tipo 01, 02, 03, 08).'))

        # Special validation for Consumidor Final
        if partner.ruc == 'CF' and partner.name == 'CONSUMIDOR FINAL':
            if not partner.street:
                errors.append(_('La dirección del cliente es requerida.'))
            if not self.invoice_line_ids:
                errors.append(_('La factura debe tener al menos una línea.'))
            if errors:
                raise ValidationError('\n'.join(errors))
            return

        # Regular validation
        if not partner.tipo_contribuyente:
            errors.append(_('El tipo de contribuyente del cliente es requerido.'))
        if not partner.tipo_cliente_fe:
            errors.append(_('El tipo de cliente FE es requerido.'))
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

    def _needs_documents(self):
        """Check if the invoice needs PDF or XML documents"""
        self.ensure_one()
        return (self.hka_status == 'sent' and 
                (not self.hka_pdf or not self.hka_xml))

    def action_get_documents(self):
        """Retrieve PDF and XML documents from HKA"""
        self.ensure_one()
        if self.hka_status != 'sent':
            raise UserError(_('Solo se pueden recuperar documentos de facturas enviadas'))

        try:
            hka_service = self.env['hka.service']
            datos_documento = {
                'codigoSucursalEmisor': self._get_hka_branch(),
                'tipoDocumento': self.tipo_documento,
                'numeroDocumentoFiscal': self.numero_documento_fiscal,
                'puntoFacturacionFiscal': self._get_hka_pos_code(),
                'tipoEmision': '01',
            }

            # Get PDF and XML
            pdf_data = hka_service.get_pdf_document(datos_documento)
            xml_data = hka_service.get_xml_document(datos_documento)

            # Update the record with any documents received
            update_vals = {}
            if pdf_data:
                update_vals.update({
                    'hka_pdf': pdf_data,
                    'hka_pdf_filename': f'FACT_{self.numero_documento_fiscal}.pdf'
                })
            if xml_data:
                update_vals.update({
                    'hka_xml': xml_data,
                    'hka_xml_filename': f'FACT_{self.numero_documento_fiscal}.xml'
                })

            if update_vals:
                self.write(update_vals)
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Éxito'),
                        'message': _('Documentos recuperados exitosamente'),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Advertencia'),
                        'message': _('No se pudieron recuperar los documentos'),
                        'sticky': False,
                        'type': 'warning',
                    }
                }

        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': str(e),
                    'sticky': True,
                    'type': 'danger',
                }
            }

    @api.returns('self')
    def _reverse_moves(self, default_values_list=None, cancel=False):
        """Override to handle HKA fields when creating credit notes"""
        if not default_values_list:
            default_values_list = [{} for move in self]

        for move, default_values in zip(self, default_values_list):
            # Clear HKA fields for credit notes
            default_values.update({
                'hka_status': 'draft',
                'hka_cufe': False,
                'hka_pdf': False,
                'hka_pdf_filename': False,
                'hka_xml': False,
                'hka_xml_filename': False,
                'numero_documento_fiscal': False,
                'hka_message': False,
                'tipo_documento': '04',  # Set document type to credit note
                'naturaleza_operacion': '04',  # Set nature to 'Devolución'
            })

        return super()._reverse_moves(default_values_list, cancel)