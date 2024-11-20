from odoo import models, fields, api, _
from odoo.exceptions import UserError
import zeep
import logging
import base64

_logger = logging.getLogger(__name__)

class HKAService(models.Model):
    _name = 'hka.service'
    _description = 'HKA Web Service Integration'

    name = fields.Char(string='Name', default='HKA Service')

    def get_client(self):
        """Get configured SOAP client for HKA service"""
        ICP = self.env['ir.config_parameter'].sudo()
        wsdl_url = ICP.get_param('isfehka.wsdl_url')
        if not wsdl_url:
            raise UserError(_('WSDL URL not configured. Please configure it in Electronic Invoice settings.'))
        
        try:
            return zeep.Client(wsdl=wsdl_url)
        except Exception as e:
            _logger.error('Error creating SOAP client: %s', str(e))
            raise UserError(_('Could not connect to HKA service: %s') % str(e))

    def get_credentials(self):
        """Get HKA credentials from settings"""
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'tokenEmpresa': ICP.get_param('isfehka.token_empresa'),
            'tokenPassword': ICP.get_param('isfehka.token_password'),
        }

    def verify_ruc(self, ruc, tipo_ruc):
        """Verify RUC number with HKA service"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            response = client.service.ConsultarRucDV(
                consultarRucDVRequest={
                    'tokenEmpresa': credentials['tokenEmpresa'],
                    'tokenPassword': credentials['tokenPassword'],
                    'tipoRuc': tipo_ruc,
                    'ruc': ruc,
                }
            )
            return self._process_response(response)
        except Exception as e:
            _logger.error('RUC verification error: %s', str(e))
            raise UserError(_('Error verifying RUC: %s') % str(e))

    def send_invoice(self, invoice_data):
        """Send invoice to HKA service"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            # Update request structure to match WSDL exactly
            response = client.service.Enviar(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                documento={
                    'codigoSucursalEmisor': invoice_data.get('codigoSucursalEmisor'),
                    'tipoSucursal': '1',  # Default to retail operations
                    'datosTransaccion': {
                        'tipoEmision': '01',  # Normal operation
                        'tipoDocumento': invoice_data.get('datosTransaccion', {}).get('tipoDocumento', '01'),
                        'numeroDocumentoFiscal': invoice_data.get('datosTransaccion', {}).get('numeroDocumentoFiscal'),
                        'puntoFacturacionFiscal': invoice_data.get('datosTransaccion', {}).get('puntoFacturacionFiscal'),
                        'fechaEmision': fields.Datetime.now().strftime('%Y-%m-%dT%H:%M:%S-05:00'),
                        'naturalezaOperacion': '01',  # Sale
                        'tipoOperacion': '1',  # Output/sale
                        'destinoOperacion': '1',  # Panama
                        'formatoCAFE': '1',  # No CAFE generation
                        'entregaCAFE': '1',  # No CAFE delivery
                        'envioContenedor': '1',  # Normal
                        'procesoGeneracion': '1',  # Generated by system
                        'tipoVenta': '1',  # Business line sale
                        'cliente': invoice_data.get('datosTransaccion', {}).get('cliente', {}),
                    },
                    'listaItems': invoice_data.get('listaItems', {'item': []}),
                    'totalesSubTotales': invoice_data.get('totalesSubTotales', {})
                }
            )
            result = self._process_response(response)
            
            # If invoice was sent successfully, get XML and PDF
            if result.get('success'):
                datos_documento = {
                    'codigoSucursalEmisor': invoice_data.get('codigoSucursalEmisor'),
                    'numeroDocumentoFiscal': invoice_data.get('datosTransaccion', {}).get('numeroDocumentoFiscal'),
                    'puntoFacturacionFiscal': invoice_data.get('datosTransaccion', {}).get('puntoFacturacionFiscal'),
                    'tipoDocumento': invoice_data.get('datosTransaccion', {}).get('tipoDocumento'),
                    'tipoEmision': invoice_data.get('datosTransaccion', {}).get('tipoEmision'),
                }
                result['xml'] = self.get_xml_document(datos_documento)
                result['pdf'] = self.get_pdf_document(datos_documento)
            
            return result
        except Exception as e:
            _logger.error('Invoice submission error: %s', str(e))
            raise UserError(_('Error sending invoice: %s') % str(e))

    def cancel_document(self, cancel_data):
        """Cancel document in HKA service"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            response = client.service.AnulacionDocumento(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                motivoAnulacion=cancel_data.get('motivoAnulacion'),
                datosDocumento=cancel_data.get('datosDocumento')
            )
            result = self._process_response(response)
            
            # If document was cancelled successfully, get XML and PDF of cancellation
            if result.get('success'):
                result['xml'] = self.get_xml_document(cancel_data.get('datosDocumento'))
                result['pdf'] = self.get_pdf_document(cancel_data.get('datosDocumento'))
            
            return result
        except Exception as e:
            _logger.error('Document cancellation error: %s', str(e))
            raise UserError(_('Error cancelling document: %s') % str(e))

    def get_xml_document(self, datos_documento):
        """Get XML document from HKA service"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            # According to WSDL, DescargaXML expects tokenEmpresa, tokenPassword and datosDocumento
            response = client.service.DescargaXML(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                datosDocumento=datos_documento
            )
            
            # Check response structure from WSDL
            if response and hasattr(response, 'codigo') and response.codigo in ['200', '201']:
                # WSDL shows documento is base64 encoded string
                if hasattr(response, 'documento') and response.documento:
                    try:
                        return base64.b64decode(response.documento)
                    except Exception as e:
                        _logger.error('Error decoding XML document: %s', str(e))
                _logger.warning('XML document not found in response')
            else:
                _logger.warning('Invalid response from HKA XML service: %s', 
                              getattr(response, 'mensaje', 'Unknown error'))
            return False
        except Exception as e:
            _logger.error('XML download error: %s', str(e))
            return False

    def get_pdf_document(self, datos_documento):
        """Get PDF document from HKA service"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            # According to WSDL, DescargaPDF expects tokenEmpresa, tokenPassword and datosDocumento
            response = client.service.DescargaPDF(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                datosDocumento=datos_documento
            )
            
            # Check response structure from WSDL
            if response and hasattr(response, 'codigo') and response.codigo in ['200', '201']:
                # WSDL shows documento is base64 encoded string
                if hasattr(response, 'documento') and response.documento:
                    try:
                        return base64.b64decode(response.documento)
                    except Exception as e:
                        _logger.error('Error decoding PDF document: %s', str(e))
                _logger.warning('PDF document not found in response')
            else:
                _logger.warning('Invalid response from HKA PDF service: %s', 
                              getattr(response, 'mensaje', 'Unknown error'))
            return False
        except Exception as e:
            _logger.error('PDF download error: %s', str(e))
            return False

    def _process_response(self, response):
        """Process HKA service response"""
        if self.env.user.has_group('base.group_no_one'):
            _logger.info('ISFEHKA Response: %s', response)

        # Check if response has codigo field
        if hasattr(response, 'codigo'):
            # Success codes are '200' or '201'
            if response.codigo in ['200', '201']:
                data = {}
                
                # Handle RUC verification response
                if hasattr(response, 'infoRuc') and response.infoRuc:
                    data = {
                        'dv': response.infoRuc.dv,
                        'razonSocial': response.infoRuc.razonSocial,
                        'tipoRuc': response.infoRuc.tipoRuc,
                        'ruc': response.infoRuc.ruc,
                    }
                
                # Handle invoice submission response
                elif hasattr(response, 'cufe'):
                    data = {
                        'cufe': response.cufe,
                        'qr': getattr(response, 'qr', ''),
                        'fechaRecepcionDGI': getattr(response, 'fechaRecepcionDGI', ''),
                        'nroProtocoloAutorizacion': getattr(response, 'nroProtocoloAutorizacion', ''),
                    }

                return {
                    'success': True,
                    'data': data,
                    'message': getattr(response, 'mensaje', 'Success')
                }
            else:
                return {
                    'success': False,
                    'message': getattr(response, 'mensaje', 'Error processing request')
                }

        return {
            'success': False,
            'message': _('Invalid response from HKA service')
        } 

    def prepare_invoice_data(self, invoice):
        """Prepare invoice data for HKA service from Odoo invoice"""
        partner = invoice.partner_id
        company = invoice.company_id
        
        # Prepare customer data with location fields
        cliente = {
            'tipoClienteFE': partner.tipo_cliente_fe or '01',  # Default to contributor
            'tipoContribuyente': partner.tipo_contribuyente or '1',  # Default to natural person
            'numeroRUC': partner.ruc,
            'digitoVerificadorRUC': partner.dv,
            'razonSocial': partner.name,
            'direccion': partner.street or '',
            'codigoUbicacion': partner.codigo_ubicacion or '',
            'provincia': partner.l10n_pa_provincia_id.name if partner.l10n_pa_provincia_id else '',
            'distrito': partner.l10n_pa_distrito_id.name if partner.l10n_pa_distrito_id else '',
            'corregimiento': partner.l10n_pa_corregimiento_id.name if partner.l10n_pa_corregimiento_id else '',
            'telefono1': partner.phone or '',
            'correoElectronico1': partner.email or '',
            'pais': partner.country_id.code or 'PA',
        }

        # Prepare items data
        items = []
        for line in invoice.invoice_line_ids:
            item = {
                'descripcion': line.name,
                'codigo': line.product_id.default_code or '',
                'cantidad': str(line.quantity),
                'precioUnitario': str(line.price_unit),
                'precioItem': str(line.price_subtotal),
                'valorTotal': str(line.price_total),
                'tasaITBMS': self._get_tax_rate(line),
                'valorITBMS': str(line.price_total - line.price_subtotal),
            }
            items.append(item)

        # Prepare totals
        totales = {
            'totalPrecioNeto': str(invoice.amount_untaxed),
            'totalITBMS': str(invoice.amount_tax),
            'totalMontoGravado': str(invoice.amount_tax),
            'totalFactura': str(invoice.amount_total),
            'totalValorRecibido': str(invoice.amount_total),
            'tiempoPago': '1',  # Immediate payment
            'nroItems': str(len(invoice.invoice_line_ids)),
            'totalTodosItems': str(invoice.amount_total),
            'listaFormaPago': {
                'formaPago': [{
                    'formaPagoFact': '02',  # Cash
                    'valorCuotaPagada': str(invoice.amount_total)
                }]
            }
        }

        return {
            'codigoSucursalEmisor': company.hka_branch_code,
            'datosTransaccion': {
                'tipoEmision': '01',
                'tipoDocumento': '01',
                'numeroDocumentoFiscal': invoice.name,
                'puntoFacturacionFiscal': invoice.journal_id.code or '001',
                'cliente': cliente,
            },
            'listaItems': {'item': items},
            'totalesSubTotales': totales,
        }

    def _get_tax_rate(self, line):
        """Get ITBMS tax rate for invoice line"""
        for tax in line.tax_ids:
            if tax.amount == 7:
                return '01'  # 7%
            elif tax.amount == 10:
                return '02'  # 10%
            elif tax.amount == 15:
                return '03'  # 15%
        return '00'  # Exempt 