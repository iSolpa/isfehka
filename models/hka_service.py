from odoo import models, fields, api, _
from odoo.exceptions import UserError
import zeep
import logging
import base64

_logger = logging.getLogger(__name__)

class HKAService(models.AbstractModel):
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
            # Log request data for debugging
            if self.env.user.has_group('base.group_no_one'):
                _logger.info('ISFEHKA RUC Verification Request: %s', {
                    'tokenEmpresa': credentials['tokenEmpresa'],
                    'tipoRuc': tipo_ruc,
                    'ruc': ruc,
                })

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
        """Send invoice to HKA"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            # Log request data for debugging
            if self.env.user.has_group('base.group_no_one'):
                _logger.info('ISFEHKA Request Data: %s', {
                    'tokenEmpresa': credentials['tokenEmpresa'],
                    'documento': invoice_data
                })

            # Update request structure to match WSDL exactly
            response = client.service.Enviar(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                documento=invoice_data.get('documento', {})  # Get the documento object directly
            )
            result = self._process_response(response)
            
            # If invoice was sent successfully, get XML and PDF
            if result.get('success'):
                documento = invoice_data['documento']  # Get first level
                datos_transaccion = documento['datosTransaccion']  # Get second level
                
                datos_documento = {
                    'codigoSucursalEmisor': documento['codigoSucursalEmisor'],
                    'tipoDocumento': datos_transaccion['tipoDocumento'],
                    'numeroDocumentoFiscal': datos_transaccion['numeroDocumentoFiscal'],
                    'puntoFacturacionFiscal': datos_transaccion['puntoFacturacionFiscal'],
                    'tipoEmision': datos_transaccion['tipoEmision'],
                }
                
                # Log the extracted datos_documento for debugging
                if self.env.user.has_group('base.group_no_one'):
                    _logger.info('ISFEHKA Extracted Document Data for PDF/XML: %s', datos_documento)
                
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
            # Log request data for debugging
            if self.env.user.has_group('base.group_no_one'):
                _logger.info('ISFEHKA Cancel Request: %s', {
                    'tokenEmpresa': credentials['tokenEmpresa'],
                    'documento': cancel_data
                })

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

    def get_pdf_document(self, datos_documento):
        """Get PDF document from HKA service"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            # Log request data for debugging
            if self.env.user.has_group('base.group_no_one'):
                _logger.info('ISFEHKA PDF Request Data: %s', {
                    'tokenEmpresa': credentials['tokenEmpresa'],
                    'datosDocumento': datos_documento
                })

            # According to WSDL, DescargaPDF expects tokenEmpresa, tokenPassword and datosDocumento
            response = client.service.DescargaPDF(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                datosDocumento=datos_documento
            )
            
            # Check response structure from WSDL
            if response and hasattr(response, 'codigo') and response.codigo in ['200', '201']:
                # Log success response
                if self.env.user.has_group('base.group_no_one'):
                    _logger.info('ISFEHKA PDF Response: %s', response)
                
                # WSDL shows documento is base64 encoded string
                if hasattr(response, 'documento') and response.documento:
                    # Convert from base64 string to bytes
                    try:
                        return base64.b64decode(response.documento)
                    except Exception as e:
                        _logger.error('Error decoding PDF base64: %s', str(e))
                        return False
                _logger.warning('PDF document not found in response')
            else:
                _logger.warning('Invalid response from HKA PDF service: %s', 
                              getattr(response, 'mensaje', 'Unknown error'))
            return False
        except Exception as e:
            _logger.error('PDF download error: %s', str(e))
            return False

    def get_xml_document(self, datos_documento):
        """Get XML document from HKA service"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            # Log request data for debugging
            if self.env.user.has_group('base.group_no_one'):
                _logger.info('ISFEHKA XML Request Data: %s', {
                    'tokenEmpresa': credentials['tokenEmpresa'],
                    'datosDocumento': datos_documento
                })

            # According to WSDL, DescargaXML expects tokenEmpresa, tokenPassword and datosDocumento
            response = client.service.DescargaXML(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                datosDocumento=datos_documento
            )
            
            # Check response structure from WSDL
            if response and hasattr(response, 'codigo') and response.codigo in ['200', '201']:
                # Log success response
                if self.env.user.has_group('base.group_no_one'):
                    _logger.info('ISFEHKA XML Response: %s', response)
                
                # WSDL shows documento is base64 encoded string
                if hasattr(response, 'documento') and response.documento:
                    # Convert from base64 string to bytes
                    try:
                        return base64.b64decode(response.documento)
                    except Exception as e:
                        _logger.error('Error decoding XML base64: %s', str(e))
                        return False
                _logger.warning('XML document not found in response')
            else:
                _logger.warning('Invalid response from HKA XML service: %s', 
                              getattr(response, 'mensaje', 'Unknown error'))
            return False
        except Exception as e:
            _logger.error('XML download error: %s', str(e))
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