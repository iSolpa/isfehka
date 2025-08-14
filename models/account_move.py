from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
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
    
    hka_qr = fields.Text(
        string='QR Code',
        readonly=True,
        help='QR Code oficial de DGI para verificación de CUFE'
    )
    
    hka_nro_protocolo_autorizacion = fields.Char(
        string='Número de Protocolo de Autorización',
        readonly=True,
        help='Número de protocolo de autorización de DGI'
    )
    
    hka_fecha_recepcion_dgi = fields.Datetime(
        string='Fecha de Recepción DGI',
        readonly=True,
        help='Fecha de autorización ante la DGI'
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
    ], string='Tipo de Documento', required=True,
       default=lambda self: self.env['ir.config_parameter'].sudo().get_param('isfehka.default_tipo_documento', '01'))

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

    def _post(self, soft=True):
        """Override to send invoice to HKA when posting"""
        res = super()._post(soft)
        for move in self.filtered(lambda m: m.move_type in ('out_invoice', 'out_refund')):
            # Ensure correct HKA document settings for POS-origin invoices before sending
            try:
                if hasattr(move, 'pos_order_ids') and move.pos_order_ids:
                    pos_order = move.pos_order_ids[0]
                    if getattr(move, 'amount_total_signed', move.amount_total) < 0:
                        move.write({
                            'tipo_documento': '04',
                            'naturaleza_operacion': '04',
                        })
                    else:
                        tipo = getattr(pos_order.config_id, 'hka_tipo_documento', move.tipo_documento) or move.tipo_documento
                        nat = getattr(pos_order.config_id, 'hka_naturaleza_operacion', move.naturaleza_operacion) or move.naturaleza_operacion
                        move.write({
                            'tipo_documento': tipo,
                            'naturaleza_operacion': nat,
                        })
            except Exception as e:
                _logger.warning('Failed to set HKA POS fields on move %s: %s', move.name or move.id, e)
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
                # Parse the authorization date from HKA response
                fecha_recepcion = result['data'].get('fechaRecepcionDGI', '')
                parsed_fecha = False
                if fecha_recepcion:
                    try:
                        # Parse ISO format datetime with timezone: 2025-07-28T09:08:13-05:00
                        dt_with_tz = datetime.fromisoformat(fecha_recepcion.replace('Z', '+00:00'))
                        # Convert to naive datetime (remove timezone) as Odoo expects
                        parsed_fecha = dt_with_tz.replace(tzinfo=None)
                    except (ValueError, AttributeError) as e:
                        _logger.warning(f"Could not parse fechaRecepcionDGI '{fecha_recepcion}': {e}")
                        parsed_fecha = False
                
                self.write({
                    'hka_status': 'sent',
                    'hka_cufe': result['data'].get('cufe', ''),
                    'hka_qr': result['data'].get('qr', ''),
                    'hka_nro_protocolo_autorizacion': result['data'].get('nroProtocoloAutorizacion', ''),
                    'hka_fecha_recepcion_dgi': parsed_fecha,
                    'hka_message': _('Documento enviado exitosamente'),
                })
                self.env.cr.commit()  # Commit the transaction to ensure we don't lose the status
                
                # Trigger sync to POS orders if isfehka_cafe module is installed
                try:
                    self._sync_cufe_to_pos_orders()
                except AttributeError:
                    # Method doesn't exist if isfehka_cafe module is not installed
                    pass

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
                # In case of error, keep status as draft and log the error
                self.write({
                    'hka_status': 'draft',  # Keep as draft instead of error
                    'hka_message': result['message']
                })
                self.env.cr.rollback()  # Rollback transaction to ensure draft state
                raise UserError(result['message'])

        except Exception as e:
            # In case of any other error, keep as draft and rollback
            self.write({
                'hka_status': 'draft',  # Keep as draft instead of error
                'hka_message': str(e)
            })
            self.env.cr.rollback()  # Rollback transaction to ensure draft state
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

    def button_send_to_hka(self):
        """Manual button to send invoice to HKA"""
        self.ensure_one()
        
        # Check if invoice is posted
        if self.state != 'posted':
            raise UserError(_('Solo se pueden enviar facturas confirmadas a HKA'))
        
        # Check if already sent
        if self.hka_status == 'sent':
            raise UserError(_('Esta factura ya ha sido enviada a HKA'))
        
        try:
            self._send_to_hka()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Éxito'),
                    'message': _('Factura enviada exitosamente a HKA'),
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

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

    def _sanitize_hka_text(self, text, max_length=50):
        """Sanitize text for HKA integration with length enforcement"""
        import re
        if not text:
            return 'Descuento'
        # Remove any special characters except alphanumeric, spaces, periods, and hyphens
        sanitized = re.sub(r'[^\w\s.-]', '', text)
        # Remove square brackets and their contents
        sanitized = re.sub(r'\[.*?\]', '', sanitized)
        # Replace multiple spaces with a single space and strip
        sanitized = ' '.join(sanitized.split())
        # Enforce maximum length
        sanitized = sanitized[:max_length] if sanitized else ''
        # If empty after sanitization, return default (also enforcing max length)
        return sanitized.strip() or 'Descuento'[:max_length]

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

            # Use the HKA reception date (when CUFE was generated) if available to match CUFE date
            ref_dt = self.reversed_entry_id.hka_fecha_recepcion_dgi or self.reversed_entry_id.invoice_date
            fecha_ref_str = ref_dt.strftime('%Y-%m-%dT%H:%M:%S-05:00') if ref_dt else fields.Datetime.now().strftime('%Y-%m-%dT%H:%M:%S-05:00')

            data['documento']['datosTransaccion']['informacionInteres'] = 'Factura de nota de credito referenciada'
            data['documento']['datosTransaccion']['listaDocsFiscalReferenciados'] = {
                'docFiscalReferenciado': [{
                    'fechaEmisionDocFiscalReferenciado': fecha_ref_str,
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
        if partner.ruc == 'CF':
            return {
                'tipoClienteFE': '02',
                'razonSocial': partner.name,
                'direccion': '',
                'telefono1': '',
                'correoElectronico1': '',
                'pais': 'PA',
            }
        
        # Special case for Extranjero
        if partner.tipo_cliente_fe == '04':
            return {
                'tipoClienteFE': '04',
                'tipoIdentificacion': '99',  # Default for Extranjero
                'nroIdentificacionExtranjero': partner.ruc,
                'razonSocial': partner.name,
                'correoElectronico1': partner.email or '',
                'telefono1': partner.phone or '',
                'pais': 'ZZ',
                'paisOtro': partner.country_id.name or '',
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

    def _is_global_discount_line(self, line):
        """Check if a line represents a global discount from POS"""
        if not line.product_id:
            return False
        # Check if product is marked as global discount in POS config
        if hasattr(line.product_id, 'is_global_discount') and line.product_id.is_global_discount:
            _logger.debug(f"Line {line.id} marked as global discount via product flag.")
            return True
        # Check if product is used in any POS global discount program
        if hasattr(self, 'pos_order_ids') and self.pos_order_ids:
            pos_config = self.pos_order_ids[0].config_id
            if hasattr(pos_config, 'discount_product_id') and pos_config.discount_product_id == line.product_id:
                _logger.debug(f"Line {line.id} marked as global discount via POS config.")
                return True
        return False


    def _prepare_hka_items_data(self):
        """Prepare invoice lines data for HKA"""
        items = []
        
        # First process regular lines
        for line in self.invoice_line_ids:
            # Skip lines with quantity 0 and global discount lines (for both invoices and credit notes)
            if not line.quantity or self._is_global_discount_line(line):
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
            precio_item = price_after_discount * line.quantity
            precio_item_str = '{:.2f}'.format(precio_item)

            # Calculate tax amount
            valor_itbms = line.price_total - line.price_subtotal
            valor_itbms_str = '{:.2f}'.format(valor_itbms)

            # Calculate total value including taxes
            valor_total = precio_item + valor_itbms
            valor_total_str = '{:.2f}'.format(valor_total)

            items.append({
                'descripcion': self._sanitize_hka_text(line.name),
                'cantidad': cantidad,
                'precioUnitario': precio_unitario,
                'precioUnitarioDescuento': precio_unitario_descuento,
                'precioItem': precio_item_str,
                'valorTotal': valor_total_str,
                'tasaITBMS': self._get_tax_rate(line),
                'valorITBMS': valor_itbms_str,
            })

        # Handle rounding (add rounding up as an extra item; rounding down is treated as discount in totals)
        rounding_amount = self.amount_total - sum(l.price_total for l in self.invoice_line_ids)
        if abs(rounding_amount) >= 0.01:
            if rounding_amount > 0:  # Rounding up - add as a line item
                items.append({
                    'descripcion': 'Ajuste por Redondeo',
                    'cantidad': '1.000',
                    'precioUnitario': '{:.3f}'.format(abs(rounding_amount)),
                    'precioUnitarioDescuento': '0.000',
                    'precioItem': '{:.2f}'.format(abs(rounding_amount)),
                    'valorTotal': '{:.2f}'.format(abs(rounding_amount)),
                    'tasaITBMS': '00',  # No tax
                    'valorITBMS': '0.00',
                })

        return items

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

    def _prepare_hka_totals_data(self):
        """Compute totals, payments, and discounts for HKA payload."""
        self.ensure_one()

        # Items (already include rounding up if applicable)
        items_data = self._prepare_hka_items_data()

        # Calculate aggregates
        total_todos_items = sum(float(item['valorTotal']) for item in items_data)
        total_precio_neto = sum(float(item['precioItem']) for item in items_data)
        total_itbms = sum(float(item.get('valorITBMS', '0.00')) for item in items_data)

        # Calculate discounts
        global_discount_lines = self.invoice_line_ids.filtered(lambda l: self._is_global_discount_line(l))
        total_global_discounts = abs(sum(line.price_subtotal for line in global_discount_lines))

        rounding_amount = self.amount_total - sum(l.price_total for l in self.invoice_line_ids)
        total_discounts = total_global_discounts
        if rounding_amount < -0.01:  # Only add negative rounding (rounding down)
            total_discounts += abs(rounding_amount)

        # Totals
        total_factura = total_todos_items - total_discounts

        # Item count (include rounding up item if present)
        has_rounding_line = rounding_amount > 0.01
        regular_items = len(self.invoice_line_ids.filtered(lambda l: l.quantity > 0 and not self._is_global_discount_line(l)))
        total_items = regular_items + (1 if has_rounding_line else 0)

        # Prepare payment methods
        payment_methods = []
        total_payments = 0.0
        change_amount = 0.00

        if self.tipo_documento == '04':  # Credit note
            refund_amount = abs(total_factura)
            payment_methods.append({
                'formaPagoFact': '02',  # Cash for refunds
                'descFormaPago': '',
                'valorCuotaPagada': '{:.2f}'.format(refund_amount)
            })
            total_payments = refund_amount
        elif hasattr(self, 'pos_order_ids') and self.pos_order_ids:
            pos_order = self.pos_order_ids[0]
            change_payments = pos_order.payment_ids.filtered(lambda p: p.amount < 0)
            if change_payments:
                change_amount = abs(sum(change_payments.mapped('amount')))
            for payment in pos_order.payment_ids.filtered(lambda p: p.amount > 0):
                payment_method = payment.payment_method_id
                amount = payment.amount
                forma_pago = payment_method.hka_payment_type or '99'
                desc_forma_pago = (payment_method.name or '')[:20] if forma_pago == '99' else ''
                payment_methods.append({
                    'formaPagoFact': forma_pago,
                    'descFormaPago': desc_forma_pago,
                    'valorCuotaPagada': '{:.2f}'.format(amount)
                })
                total_payments += amount
        else:
            payment_methods.append({
                'formaPagoFact': '02',
                'descFormaPago': '',
                'valorCuotaPagada': '{:.2f}'.format(total_factura)
            })
            total_payments = total_factura

        data = {
            'totalPrecioNeto': '{:.2f}'.format(total_precio_neto),
            'totalITBMS': '{:.2f}'.format(total_itbms),
            'totalMontoGravado': '{:.2f}'.format(total_itbms),
            'totalDescuento': '{:.2f}'.format(total_discounts) if total_discounts > 0 else '',
            'totalFactura': '{:.2f}'.format(total_factura),
            'totalValorRecibido': '{:.2f}'.format(total_payments),
            'vuelto': '{:.2f}'.format(change_amount),
            'tiempoPago': '1',
            'nroItems': str(total_items),
            'totalTodosItems': '{:.2f}'.format(total_todos_items),
            'listaFormaPago': {
                'formaPago': payment_methods
            }
        }

        # Discount/bonification list
        discount_bonifications = []
        if global_discount_lines:
            for line in global_discount_lines:
                discount_bonifications.append({
                    'descDescuento': self._sanitize_hka_text(line.name, max_length=30),
                    'montoDescuento': '{:.2f}'.format(abs(line.price_subtotal))
                })
        if rounding_amount < -0.01:
            discount_bonifications.append({
                'descDescuento': 'Ajuste por Redondeo',
                'montoDescuento': '{:.2f}'.format(abs(rounding_amount))
            })
        if discount_bonifications:
            data['listaDescBonificacion'] = {
                'descuentoBonificacion': discount_bonifications
            }

        return data

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

    def get_hka_pdf_receipt(self):
        """Get the HKA PDF receipt for POS printing"""
        self.ensure_one()
        if not self.hka_pdf:
            return False
        return self.hka_pdf

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

        # Special validation for Consumidor Final and Extranjero
        if partner.tipo_cliente_fe in ['02', '04']:
            if not self.invoice_line_ids:
                errors.append(_('La factura debe tener al menos una línea.'))
            
            # Additional validations for Extranjero
            if partner.tipo_cliente_fe == '04':
                if not partner.ruc:
                    errors.append(_('El número de identificación extranjera es requerido.'))
                if not partner.name:
                    errors.append(_('La razón social del cliente es requerida.'))
                if not partner.country_id:
                    errors.append(_('El país es requerido.'))
                
                if errors:
                    raise ValidationError('\n'.join(errors))
                # Mark the partner as verified for Extranjero clients if all validations pass
                partner.ruc_verified = True
                partner.ruc_verification_date = fields.Datetime.now()
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