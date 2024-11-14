from odoo import models, fields, api, _
from odoo.exceptions import UserError
import zeep
import logging

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
                    **credentials,
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
            response = client.service.Enviar(
                **credentials,
                **invoice_data
            )
            return self._process_response(response)
        except Exception as e:
            _logger.error('Invoice submission error: %s', str(e))
            raise UserError(_('Error sending invoice: %s') % str(e))

    def cancel_document(self, cancel_data):
        """Cancel document in HKA service"""
        client = self.get_client()
        credentials = self.get_credentials()
        
        try:
            response = client.service.AnulacionDocumento(
                **credentials,
                **cancel_data
            )
            return self._process_response(response)
        except Exception as e:
            _logger.error('Document cancellation error: %s', str(e))
            raise UserError(_('Error cancelling document: %s') % str(e))

    def _process_response(self, response):
        """Process HKA service response"""
        if hasattr(response, 'Codigo'):
            if response.Codigo == 200:
                return {
                    'success': True,
                    'data': response,
                }
            else:
                return {
                    'success': False,
                    'message': getattr(response, 'Mensaje', 'Unknown error'),
                }
        return {
            'success': False,
            'message': _('Invalid response from HKA service'),
        } 