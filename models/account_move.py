from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import base64
import logging
import pytz
from datetime import datetime, timedelta

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
    
    hka_qr = fields.Char(
        string='QR URL',
        readonly=True,
        help='URL del código QR de la DGI para validación'
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

    @api.model
    def _default_tipo_documento(self):
        move_type = self.env.context.get('default_move_type', 'entry')
        if move_type not in ('out_invoice', 'out_refund'):
            return False
        company_id = self.env.context.get('default_company_id') or self.env.company.id
        company = self.env['res.company'].browse(company_id)
        config = company.hka_configuration_id
        return config.default_tipo_documento if config else '01'

    @api.model
    def _default_naturaleza_operacion(self):
        move_type = self.env.context.get('default_move_type', 'entry')
        if move_type not in ('out_invoice', 'out_refund'):
            return False
        return '01'

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
    ], string='Tipo de Documento',
       default=lambda self: self._default_tipo_documento())

    naturaleza_operacion = fields.Selection([
        ('01', 'Venta'),
        ('02', 'Exportación'),
        ('03', 'Transferencia'),
        ('04', 'Devolución')
    ], string='Naturaleza de Operación',
       default=lambda self: self._default_naturaleza_operacion())

    motivo_anulacion = fields.Text(
        string='Motivo de Anulación',
        help='Razón por la cual se anula el documento'
    )

    def action_post(self):
        """Override action_post to optionally auto-send customer invoices to HKA.
        
        When hka_auto_send_on_post is enabled on the company, customer invoices
        are automatically sent to HKA after posting. This covers:
        - POS invoices (tipo_documento/naturaleza set from POS config)
        - Subscription renewals
        - Any other automated invoicing flow
        """
        res = super().action_post()
        for move in self.filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund')
            and m.state == 'posted'
            and m.hka_status != 'sent'
            and m.company_id.hka_auto_send_on_post
            and m.tipo_documento
        ):
            # For POS invoices, apply tipo_documento/naturaleza from POS config
            if hasattr(move, 'pos_order_ids') and move.pos_order_ids:
                pos_order = move.pos_order_ids[0]
                if pos_order.config_id:
                    vals = {}
                    if pos_order.amount_total < 0:
                        vals['tipo_documento'] = '04'
                        vals['naturaleza_operacion'] = '04'
                    else:
                        if pos_order.config_id.hka_tipo_documento:
                            vals['tipo_documento'] = pos_order.config_id.hka_tipo_documento
                        if pos_order.config_id.hka_naturaleza_operacion:
                            vals['naturaleza_operacion'] = pos_order.config_id.hka_naturaleza_operacion
                    if vals:
                        move.write(vals)
            try:
                move._send_to_hka()
            except Exception as e:
                _logger.warning('Auto-send to HKA failed for %s: %s', move.name or move.id, e)
                move.write({
                    'hka_status': 'error',
                    'hka_message': str(e),
                })
        return res

    def _send_to_hka(self):
        """Send invoice to HKA"""
        self.ensure_one()
        if self.hka_status == 'sent':
            raise UserError(_('Esta factura ya ha sido enviada a HKA'))

        # Validate required data before sending
        self._validate_hka_data()
        self._get_hka_configuration()

        # Get the next fiscal number if needed
        if not self.numero_documento_fiscal:
            fiscal_number = self._get_next_fiscal_number()
            if not fiscal_number:
                raise UserError(_('No se pudo obtener el próximo número fiscal.'))
            self.numero_documento_fiscal = fiscal_number

        try:
            hka_service = self.env['hka.service'].with_company(self.company_id)
            invoice_data = self._prepare_hka_data()
            # Skip PDF/XML downloads if this is a POS order to avoid blocking
            skip_documents = bool(self.pos_order_ids)
            result = hka_service.send_invoice(invoice_data, skip_documents=skip_documents)

            if result['success']:
                # CRITICAL: Save essential HKA data first - never rollback after HKA succeeds
                try:
                    # Write critical fields that must be saved
                    self.write({
                        'hka_status': 'sent',
                        'hka_cufe': result['data'].get('cufe', ''),
                        'hka_qr': result['data'].get('qr', ''),
                        'hka_nro_protocolo_autorizacion': result['data'].get('nroProtocoloAutorizacion', ''),
                        'hka_message': _('Documento enviado exitosamente'),
                    })
                    self.env.cr.commit()  # Commit immediately - invoice exists in DGI now
                    _logger.info(f"CRITICAL HKA DATA SAVED for invoice {self.name} - CUFE: {result['data'].get('cufe', '')}")
                except Exception as e:
                    # If even this fails, log and try to save just CUFE
                    _logger.error(f"CRITICAL: Failed to save HKA data for {self.name}: {e}")
                    try:
                        self.write({
                            'hka_status': 'sent',
                            'hka_cufe': result['data'].get('cufe', ''),
                            'hka_message': _('Documento enviado - datos parciales: %s') % str(e),
                        })
                        self.env.cr.commit()
                    except:
                        _logger.critical(f"FAILED TO SAVE CUFE for {self.name} - CUFE: {result['data'].get('cufe', '')} - MANUAL RECOVERY NEEDED")
                
                # Now try to save optional date field separately
                try:
                    fecha_recepcion = False
                    if result['data'].get('fechaRecepcionDGI'):
                        # Parse ISO 8601 format: 2025-11-13T15:46:53-05:00
                        fecha_str = result['data']['fechaRecepcionDGI']
                        # Remove timezone info and parse
                        if 'T' in fecha_str:
                            fecha_str = fecha_str.split('-05:00')[0].split('+')[0]  # Remove timezone
                            fecha_recepcion = datetime.strptime(fecha_str, '%Y-%m-%dT%H:%M:%S')
                        
                        self.write({'hka_fecha_recepcion_dgi': fecha_recepcion})
                        self.env.cr.commit()
                except Exception as e:
                    _logger.warning(f"Could not save fechaRecepcionDGI for {self.name}: {e} - Continuing with other data")
                    # Don't fail - we already saved the critical data

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

    def button_register_hka_document(self):
        """Open wizard to register an existing HKA document without re-sending"""
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('La factura debe estar confirmada antes de registrar el documento HKA.'))
        if self.hka_status == 'sent':
            raise UserError(_('Esta factura ya está registrada como enviada a HKA.'))
        return {
            'name': _('Registrar Documento Fiscal'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.register.hka',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_id': self.id},
        }

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

        self._get_hka_configuration()

        try:
            hka_service = self.env['hka.service'].with_company(self.company_id)
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

    def _get_hka_configuration(self):
        """Get the configuration set used by this invoice's company"""
        self.ensure_one()
        config = self.company_id.hka_configuration_id
        if not config:
            raise UserError(_('Configure un conjunto de credenciales HKA para la compañía %s.')
                            % self.company_id.display_name)
        return config

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

            # Use the HKA reception date (when CUFE was generated) if available to match CUFE date
            # NOTE: hka_fecha_recepcion_dgi is stored as Panama time (not UTC) due to how HKA response is parsed
            # So we DON'T convert - just format directly with the Panama timezone offset
            ref_dt = self.reversed_entry_id.hka_fecha_recepcion_dgi or self.reversed_entry_id.invoice_date
            if ref_dt:
                if isinstance(ref_dt, datetime):
                    # hka_fecha_recepcion_dgi is already in Panama time, just format with offset
                    fecha_ref_str = ref_dt.strftime('%Y-%m-%dT%H:%M:%S-05:00')
                else:
                    # It's a date (invoice_date), format as midnight Panama time
                    fecha_ref_str = ref_dt.strftime('%Y-%m-%dT00:00:00-05:00')
            else:
                panama_tz = pytz.timezone('America/Panama')
                now_utc = pytz.utc.localize(datetime.utcnow())
                now_local = now_utc.astimezone(panama_tz)
                fecha_ref_str = now_local.strftime('%Y-%m-%dT%H:%M:%S-05:00')

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
        """Get and increment the next fiscal number using the shared configuration."""
        self.ensure_one()
        if self.hka_status not in ('draft', 'error'):
            return False
        config = self._get_hka_configuration()
        return config.get_and_increment_next_number()

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

    def _is_discount_line(self, line):
        """Check if a line represents a discount (global, loyalty, or coupon)
        
        For regular invoices, discount lines have negative prices.
        For credit notes, we only check for explicitly marked discount products (not price sign).
        """
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
        
        # For regular invoices only: check if line has negative price (loyalty/coupon discount)
        # Do NOT use this logic for credit notes as all lines are positive in refunds
        if self.move_type == 'out_invoice':
            if line.price_unit < 0 or line.price_subtotal < 0:
                _logger.debug(f"Line {line.id} detected as loyalty/discount line (negative price: unit={line.price_unit}, subtotal={line.price_subtotal}).")
                return True
        
        return False


    def _prepare_hka_items_data(self):
        """Prepare invoice lines data for HKA"""
        items = []
        
        # First process regular lines
        for line in self.invoice_line_ids:
            # Skip lines with quantity 0 and discount lines (global, loyalty, coupon) for both invoices and credit notes
            if not line.quantity or self._is_discount_line(line):
                continue

            # Format numeric values according to HKA specifications
            cantidad = '{:.3f}'.format(line.quantity)  # N|13,3 format
            
            # Determine the original price and discount amount
            # Handle both explicit discounts (discount field) and implicit pricelist discounts
            original_price = line.price_unit
            discount_amount = 0.0
            
            # First check if there's an explicit discount percentage
            if line.discount:
                # Explicit discount: price_unit is before discount, calculate discount amount
                discount_amount = (line.price_unit * line.discount) / 100
                _logger.debug(f"Line {line.id} has explicit discount: {line.discount}% on {line.price_unit}")
            elif line.product_id and line.product_id.lst_price > 0:
                # Check for implicit pricelist discount
                # Compare price_unit (actual selling price) with product list price
                list_price = line.product_id.lst_price
                if line.price_unit < list_price:
                    # Pricelist applied a discount
                    original_price = list_price
                    discount_amount = list_price - line.price_unit
                    implicit_discount_pct = (discount_amount / list_price) * 100
                    _logger.debug(f"Line {line.id} has implicit pricelist discount: {implicit_discount_pct:.2f}% (list: {list_price}, actual: {line.price_unit})")
            
            precio_unitario = '{:.3f}'.format(original_price)
            precio_unitario_descuento = '{:.3f}'.format(discount_amount)

            # Calculate price after discount per unit
            price_after_discount = original_price - discount_amount

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

        # Handle rounding
        rounding_amount = self.amount_total - sum(l.price_total for l in self.invoice_line_ids)
        if abs(rounding_amount) >= 0.01:  # Only process significant rounding
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

    def _sanitize_hka_text(self, text, max_length=50):
        """Sanitize text for HKA integration with length enforcement and ASCII normalization"""
        import re
        import unicodedata
        if not text:
            return 'Descuento'
        
        # Normalize unicode characters to ASCII (e.g., "específicos" -> "especificos")
        # NFD = Canonical Decomposition, then filter out combining marks
        text = unicodedata.normalize('NFD', text)
        text = ''.join(char for char in text if unicodedata.category(char) != 'Mn')
        
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

    def _get_hka_forma_pago_info(self, journal=None, payment_method_name=None, hka_payment_type=None, is_pos_cash=False):
        """Determine HKA formaPagoFact and descFormaPago for a payment.
        
        Priority:
        1. Explicitly configured hka_payment_type on the payment method/line/provider
        2. Infer from journal type (cash -> 02, bank -> 08)
        3. Infer from POS payment method characteristics
        4. Default to '02' (Efectivo) as safe fallback
        
        When formaPagoFact is '99' (Otro), descFormaPago is required by DGI
        and must be 4-50 characters.
        """
        forma_pago = hka_payment_type
        
        # If no explicit HKA type, infer from journal type
        if not forma_pago and journal:
            journal_type = journal.type if hasattr(journal, 'type') else None
            if journal_type == 'cash':
                forma_pago = '02'  # Efectivo
            elif journal_type == 'bank':
                forma_pago = '08'  # Transf/Deposito cta. Bancaria
        
        # POS cash-type payment methods default to cash
        if not forma_pago and is_pos_cash:
            forma_pago = '02'  # Efectivo
        
        # Final fallback: cash (safe default for manual/unmatched payments)
        if not forma_pago:
            forma_pago = '02'  # Efectivo
        
        # Build descFormaPago (only required when formaPagoFact = '99')
        desc_forma_pago = ''
        if forma_pago == '99':
            desc = (payment_method_name or 'Otro metodo de pago')[:50]
            # DGI requires minimum length for descFormaPago (at least 4 chars)
            if len(desc) < 4:
                desc = desc.ljust(4)
            desc_forma_pago = desc
        
        return forma_pago, desc_forma_pago

    def _prepare_hka_totals_data(self):
        """Prepare totals data for HKA"""
        # Calculate rounding amount
        rounding_amount = self.amount_total - sum(l.price_total for l in self.invoice_line_ids)
        has_rounding_line = rounding_amount > 0.01  # Track if we'll add a rounding line item
        
        # Prepare items data
        items_data = self._prepare_hka_items_data()

        # Calculate totalTodosItems as the sum of 'valorTotal' from all items
        total_todos_items = sum(
            float(item['valorTotal']) for item in items_data
        )

        # Calculate totalPrecioNeto as the sum of 'precioItem' from all items
        total_precio_neto = sum(
            float(item['precioItem']) for item in items_data
        )

        # Calculate totalITBMS as the sum of 'valorITBMS' from all items
        total_itbms = sum(
            float(item['valorITBMS']) for item in items_data
        )

        # Calculate all discounts (global, loyalty, coupon)
        discount_lines = self.invoice_line_ids.filtered(
            lambda l: self._is_discount_line(l)
        )
        # For totalDescuento field: use price_subtotal (without tax) to match listaDescBonificacion
        total_discounts_subtotal = abs(sum(
            line.price_subtotal
            for line in discount_lines
        ))
        # For totalFactura calculation: use price_total (with tax) since totalTodosItems includes tax
        total_discounts_with_tax = abs(sum(
            line.price_total
            for line in discount_lines
        ))

        # Handle rounding down as a discount
        # totalDescuento must include tax to match DGI's validation formula
        total_discounts = total_discounts_with_tax
        if rounding_amount < -0.01:  # Only add negative rounding (rounding down)
            total_discounts += abs(rounding_amount)

        # Calculate totalFactura
        # DGI validates: totalFactura = totalTodosItems - totalDescuento
        # Must use this formula even if it differs slightly from amount_total due to rounding
        total_factura = total_todos_items - total_discounts

        # Calculate number of items (including rounding line if present)
        regular_items = len(self.invoice_line_ids.filtered(lambda l: l.quantity > 0 and not self._is_discount_line(l)))
        total_items = regular_items + (1 if has_rounding_line else 0)

        # Prepare payment methods data
        payment_methods = []
        total_payments = 0.0
        change_amount = 0.00

        # For credit notes (refunds), handle payment differently
        if self.tipo_documento == '04':
            refund_amount = abs(total_factura)  # Get positive value of refund
            payment_methods.append({
                'formaPagoFact': '02',  # Use cash for refunds
                'descFormaPago': '',
                'valorCuotaPagada': '{:.2f}'.format(refund_amount)  # Put refund amount here
            })
            total_payments = refund_amount  # Set total payments to refund amount
            change_amount = 0.00  # No change for refunds
        # For POS orders, use the payment lines
        elif hasattr(self, 'pos_order_ids') and self.pos_order_ids:
            pos_order = self.pos_order_ids[0]
            
            # First pass to identify change payments (negative amounts)
            change_payments = pos_order.payment_ids.filtered(lambda p: p.amount < 0)
            if change_payments:
                change_amount = abs(sum(change_payments.mapped('amount')))
            
            # Second pass to add only positive payments
            for payment in pos_order.payment_ids.filtered(lambda p: p.amount > 0):
                payment_method = payment.payment_method_id
                amount = payment.amount

                # Use configured HKA payment type, or infer from journal type
                is_pos_cash = not payment_method.is_cash_count and not getattr(payment_method, 'use_payment_terminal', False)
                forma_pago, desc_forma_pago = self._get_hka_forma_pago_info(
                    journal=payment_method.journal_id if hasattr(payment_method, 'journal_id') else None,
                    payment_method_name=payment_method.name,
                    hka_payment_type=payment_method.hka_payment_type or None,
                    is_pos_cash=is_pos_cash,
                )

                payment_methods.append({
                    'formaPagoFact': forma_pago,
                    'descFormaPago': desc_forma_pago,
                    'valorCuotaPagada': '{:.2f}'.format(amount)
                })
                total_payments += amount
            
            # Recalculate change based on actual payment difference
            # Handles cases where customer overpays due to rounding
            if total_payments > total_factura:
                change_amount = total_payments - total_factura

        else:
            # Check for registered payments on the invoice (from sales orders, etc.)
            registered_payments = self._get_reconciled_payments()
            if registered_payments:
                for payment in registered_payments:
                    amount = payment.amount
                    # Check for payment provider's hka_payment_type first (ecommerce payments)
                    explicit_hka_type = None
                    if hasattr(payment, 'payment_transaction_id') and payment.payment_transaction_id:
                        provider = payment.payment_transaction_id.provider_id
                        if provider and hasattr(provider, 'hka_payment_type'):
                            explicit_hka_type = provider.hka_payment_type
                    # Fall back to payment method line's hka_payment_type
                    if not explicit_hka_type and hasattr(payment, 'payment_method_line_id') and payment.payment_method_line_id:
                        explicit_hka_type = getattr(payment.payment_method_line_id, 'hka_payment_type', None)
                    
                    payment_method_name = payment.payment_method_line_id.name if payment.payment_method_line_id else payment.journal_id.name
                    forma_pago, desc_forma_pago = self._get_hka_forma_pago_info(
                        journal=payment.journal_id,
                        payment_method_name=payment_method_name,
                        hka_payment_type=explicit_hka_type,
                    )
                    payment_methods.append({
                        'formaPagoFact': forma_pago,
                        'descFormaPago': desc_forma_pago,
                        'valorCuotaPagada': '{:.2f}'.format(amount)
                    })
                    total_payments += amount
                # If payments don't cover full amount, add remaining as credit
                remaining = total_factura - total_payments
                if remaining > 0.01:
                    payment_methods.append({
                        'formaPagoFact': '01',  # Credit for unpaid portion
                        'descFormaPago': '',
                        'valorCuotaPagada': '{:.2f}'.format(remaining)
                    })
                    total_payments = total_factura
            else:
                # No payments registered - default to credit (unpaid invoice)
                payment_methods.append({
                    'formaPagoFact': '01',  # Credit - invoice not yet paid
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

        # Add all discounts (global, loyalty, coupon) and rounding down to listaDescBonificacion if any exist
        discount_bonifications = []
        
        # Add discount lines if any
        if discount_lines:
            for line in discount_lines:
                # Ensure we have a valid description for the discount
                desc_text = line.name or line.product_id.name or 'Descuento'
                sanitized_desc = self._sanitize_hka_text(desc_text)
                # Ensure the description is not empty after sanitization
                if not sanitized_desc or sanitized_desc.strip() == '':
                    sanitized_desc = 'Descuento'
                
                # Use price_total (with tax) to match totalDescuento
                discount_bonifications.append({
                    'descDescuento': sanitized_desc[:30],  # Enforce 30 char max for HKA
                    'montoDescuento': '{:.2f}'.format(abs(line.price_total))
                })
        
        # Add rounding down as a discount if significant
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

        # Validate move type
        if self.move_type not in ('out_invoice', 'out_refund'):
            raise ValidationError(_('Solo se pueden enviar facturas de cliente y notas de crédito a HKA.'))

        # Validate HKA document fields
        if not self.tipo_documento:
            errors.append(_('El tipo de documento es requerido para enviar a HKA.'))
        if not self.naturaleza_operacion:
            errors.append(_('La naturaleza de operación es requerida para enviar a HKA.'))

        # Validate partner RUC is verified
        if not partner.ruc_verified:
            errors.append(_('El RUC del cliente debe estar verificado antes de enviar a HKA.'))

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

    @api.model
    def _cron_retrieve_missing_documents(self):
        """Cron job to retrieve missing PDF/XML documents for invoices sent via POS"""
        # Find invoices sent in the last 7 days that are missing documents
        date_limit = fields.Datetime.now() - timedelta(days=7)
        invoices = self.search([
            ('hka_status', '=', 'sent'),
            ('write_date', '>=', date_limit),
            '|',
            ('hka_pdf', '=', False),
            ('hka_xml', '=', False),
        ], limit=50)  # Process max 50 invoices per run
        
        if not invoices:
            return
            
        _logger.info(f'[HKA CRON] Found {len(invoices)} invoices with missing documents')
        
        for invoice in invoices:
            try:
                if invoice._needs_documents():
                    _logger.info(f'[HKA CRON] Retrieving documents for invoice {invoice.name}')
                    invoice.action_get_documents()
                    self.env.cr.commit()  # Commit after each invoice to avoid losing work
            except Exception as e:
                _logger.warning(f'[HKA CRON] Failed to retrieve documents for {invoice.name}: {e}')
                # Continue with next invoice
                continue

    def action_get_documents(self):
        """Retrieve PDF and XML documents from HKA"""
        self.ensure_one()
        if self.hka_status != 'sent':
            raise UserError(_('Solo se pueden recuperar documentos de facturas enviadas'))

        self._get_hka_configuration()

        try:
            hka_service = self.env['hka.service'].with_company(self.company_id)
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
