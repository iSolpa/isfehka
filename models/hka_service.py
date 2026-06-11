from odoo import models, api, _
from odoo.exceptions import UserError
import base64
import logging
import re
import unicodedata

_logger = logging.getLogger(__name__)


class HKADriver(models.AbstractModel):
    """The Factory HKA (SOAP) PAC driver for the neutral ``isfe_base`` layer.

    Concrete implementation of the abstract ``isfe.driver`` interface. This is
    the ONLY place in the HKA integration that knows the HKA wire format: it
    serializes the neutral document produced by
    ``account.move._prepare_fe_document()`` into HKA's structured SOAP payload
    (``Enviar``), talks SOAP via ``zeep``, and translates HKA's responses back
    into the NEUTRAL result contract documented on ``isfe.driver``.

    The base dispatches per-company via
    ``isfe.configuration._resolve_driver(company)`` -> this model
    (``isfe.driver.hka``), so HKA can coexist with another PAC driver in the
    same database (multi-company multi-PAC — the Ferretería Miki shape:
    Miki -> Digifact, Inversora -> HKA).

    Credentials live on ``isfe.configuration`` (driver-extension fields
    ``hka_token_empresa`` / ``hka_token_password`` / ``hka_wsdl_url``), resolved
    via ``self.env.company.fe_configuration_id`` (the base binds the driver to
    the emitting company with ``with_company``).

    DELIBERATELY NOT ported from the legacy line builder: the implicit
    "pricelist discount" inference (``price_unit < product.lst_price`` =>
    fabricate precioUnitarioDescuento). A price level is NOT a discount;
    Aduanas rejected those payloads and they diverged from the legal invoice.
    ``precioUnitario`` is the REAL unit price and the discount comes ONLY from
    the line's explicit discount percentage (plus document-level discount
    lines), exactly as the neutral document carries them.
    """
    _name = 'isfe.driver.hka'
    _inherit = 'isfe.driver'
    _description = 'The Factory HKA PAC Driver'

    # Neutral fe_payment_type (base catalog) -> HKA formaPagoFact codes.
    _PAYMENT_TYPE_MAP = {
        '01': '02',  # Efectivo                  -> 02 Efectivo
        '02': '09',  # Cheque                    -> 09 Cheque
        '03': '03',  # Tarjeta de Crédito        -> 03 Tarjeta Crédito
        '04': '04',  # Tarjeta de Débito         -> 04 Tarjeta Débito
        '05': '08',  # Transferencia             -> 08 Transf/Depósito cta.
        '06': '08',  # Depósito                  -> 08 Transf/Depósito cta.
        '07': '07',  # Bonos/Cert. de Regalo     -> 07 Tarjeta de Regalo
        '08': '05',  # Puntos de Fidelización    -> 05 Tarjeta Fidelización
        '09': '01',  # Crédito del Establecim.   -> 01 Crédito
        '10': '99',  # Pago Móvil                -> 99 Otro
        '99': '99',  # Otro                      -> 99 Otro
    }

    # ------------------------------------------------------------------
    # Configuration / SOAP plumbing
    # ------------------------------------------------------------------
    def _get_config(self):
        config = self.env.company.fe_configuration_id
        if not config:
            raise UserError(_('No hay una configuración FE asignada a la compañía.'))
        return config

    def _get_client(self, config):
        """Configured zeep SOAP client for the HKA service."""
        import zeep  # external dependency of THIS driver only
        wsdl_url = config.hka_wsdl_url
        if not wsdl_url:
            raise UserError(_('Configure la URL del WSDL de HKA en la configuración FE.'))
        try:
            return zeep.Client(wsdl=wsdl_url)
        except Exception as e:
            _logger.error('Error creating HKA SOAP client: %s', str(e))
            raise UserError(_('No se pudo conectar al servicio HKA: %s') % str(e))

    def _get_credentials(self, config):
        if not config.hka_token_empresa or not config.hka_token_password:
            raise UserError(_('Configure el Token Empresa y Token Password de HKA en la configuración FE.'))
        return {
            'tokenEmpresa': config.hka_token_empresa,
            'tokenPassword': config.hka_token_password,
        }

    # ------------------------------------------------------------------
    # Interface: send_invoice
    # ------------------------------------------------------------------
    @api.model
    def send_invoice(self, doc):
        """Serialize the NEUTRAL document to HKA's SOAP structure, submit it,
        and return the neutral result contract (see ``isfe.driver``)."""
        config = self._get_config()
        client = self._get_client(config)
        credentials = self._get_credentials(config)
        documento = self._build_hka_documento(doc)

        try:
            import json
            log_data = {
                'tokenEmpresa': (credentials['tokenEmpresa']
                                 if self.env.user.has_group('base.group_no_one')
                                 else '***MASKED***'),
                'documento': documento,
            }
            _logger.info('ISFEHKA Request Data: %s',
                         json.dumps(log_data, indent=2, ensure_ascii=False, default=str))
        except Exception:
            pass

        try:
            response = client.service.Enviar(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                documento=documento,
            )
        except Exception as e:
            _logger.error('HKA invoice submission error: %s', str(e))
            raise UserError(_('Error al enviar la factura a HKA: %s') % str(e))

        result = self._process_response(response)

        # Fetch the official files only when the document actually registered.
        if result.get('success'):
            datos_documento = self._hka_datos_documento({
                'branch_code': doc.get('branch_code'),
                'tipo_documento': doc.get('doc_type'),
                'numero_documento_fiscal': doc.get('numero_documento_fiscal'),
                'pos_code': doc.get('pos_code'),
            })
            result['pdf'] = self._download_document(client, credentials, 'DescargaPDF', datos_documento)
            result['xml'] = self._download_document(client, credentials, 'DescargaXML', datos_documento)
        return result

    # ------------------------------------------------------------------
    # Interface: cancel_document
    # ------------------------------------------------------------------
    @api.model
    def cancel_document(self, data):
        """Cancel a document at HKA. ``data`` is the neutral document ref +
        ``reason`` (HKA addresses by branch/type/number/point, not by CUFE)."""
        config = self._get_config()
        client = self._get_client(config)
        credentials = self._get_credentials(config)
        try:
            response = client.service.AnulacionDocumento(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                motivoAnulacion=data.get('reason') or data.get('motivoAnulacion') or '',
                datosDocumento=self._hka_datos_documento(data),
            )
        except Exception as e:
            _logger.error('HKA document cancellation error: %s', str(e))
            raise UserError(_('Error al anular el documento en HKA: %s') % str(e))
        return self._process_response(response)

    # ------------------------------------------------------------------
    # Interface: document retrieval
    # ------------------------------------------------------------------
    @api.model
    def get_pdf_document(self, data):
        """Official PDF bytes for a document ref, or False."""
        config = self._get_config()
        client = self._get_client(config)
        credentials = self._get_credentials(config)
        return self._download_document(client, credentials, 'DescargaPDF',
                                       self._hka_datos_documento(data))

    @api.model
    def get_xml_document(self, data):
        """Official XML bytes for a document ref, or False."""
        config = self._get_config()
        client = self._get_client(config)
        credentials = self._get_credentials(config)
        return self._download_document(client, credentials, 'DescargaXML',
                                       self._hka_datos_documento(data))

    # ------------------------------------------------------------------
    # Interface: verify_ruc
    # ------------------------------------------------------------------
    @api.model
    def verify_ruc(self, ruc, tipo, tipo_contribuyente=None):
        """RUC verification against HKA's ConsultarRucDV.

        CF / Extranjero verify trivially (no PAC lookup possible); a regular
        contribuyente is checked at the PAC using ``tipo_contribuyente``
        ('1' Natural / '2' Jurídico) as HKA's ``tipoRuc``."""
        ruc = (ruc or '').strip()
        if tipo in ('02', '04') or ruc.upper() == 'CF':
            return {
                'verified': True,
                'dv': '00',
                'message': _('Cliente sin verificación de RUC requerida (Consumidor Final / Extranjero).'),
                'tipo_cliente_fe': False,
            }
        if not ruc or not tipo_contribuyente:
            return {'verified': False, 'dv': False,
                    'message': _('Ingrese el RUC y el tipo de contribuyente para verificar.'),
                    'tipo_cliente_fe': False}

        config = self._get_config()
        client = self._get_client(config)
        credentials = self._get_credentials(config)
        try:
            response = client.service.ConsultarRucDV(
                consultarRucDVRequest={
                    'tokenEmpresa': credentials['tokenEmpresa'],
                    'tokenPassword': credentials['tokenPassword'],
                    'tipoRuc': tipo_contribuyente,
                    'ruc': ruc,
                }
            )
        except Exception as e:
            _logger.error('HKA RUC verification error: %s', str(e))
            raise UserError(_('Error verificando el RUC: %s') % str(e))

        result = self._process_response(response)
        if not result.get('success'):
            return {'verified': False, 'dv': False,
                    'message': result.get('message') or _('No se pudo verificar el RUC.'),
                    'tipo_cliente_fe': False}
        data = result.get('data') or {}
        return {
            'verified': True,
            'dv': data.get('dv') or False,
            'message': result.get('message') or _('RUC verificado exitosamente.'),
            'tipo_cliente_fe': False,
        }

    # ------------------------------------------------------------------
    # HKA response -> neutral result
    # ------------------------------------------------------------------
    def _process_response(self, response):
        """Translate an HKA SOAP response into the neutral result contract."""
        import json
        try:
            response_dict = {
                'codigo': getattr(response, 'codigo', None),
                'resultado': getattr(response, 'resultado', None),
                'mensaje': getattr(response, 'mensaje', None),
                'cufe': getattr(response, 'cufe', None),
                'qr': getattr(response, 'qr', None),
                'fechaRecepcionDGI': getattr(response, 'fechaRecepcionDGI', None),
                'nroProtocoloAutorizacion': getattr(response, 'nroProtocoloAutorizacion', None),
            }
            _logger.info('ISFEHKA Response: %s',
                         json.dumps(response_dict, indent=2, ensure_ascii=False, default=str))
        except Exception:
            _logger.info('ISFEHKA Response: %s', response)

        codigo = getattr(response, 'codigo', None)
        mensaje = getattr(response, 'mensaje', '') or ''
        if codigo is None:
            return {
                'success': False,
                'data': {},
                'message': _('Respuesta inválida del servicio HKA'),
                'pdf': False, 'xml': False,
                'error_details': [],
                'duplicate_number': False,
            }

        if str(codigo) in ('200', '201'):
            data = {}
            info_ruc = getattr(response, 'infoRuc', None)
            if info_ruc:
                data = {
                    'dv': getattr(info_ruc, 'dv', ''),
                    'razonSocial': getattr(info_ruc, 'razonSocial', ''),
                    'tipoRuc': getattr(info_ruc, 'tipoRuc', ''),
                    'ruc': getattr(info_ruc, 'ruc', ''),
                }
            elif getattr(response, 'cufe', None):
                data = {
                    'cufe': response.cufe,
                    'qr': getattr(response, 'qr', '') or '',
                    'fecha_recepcion': getattr(response, 'fechaRecepcionDGI', '') or '',
                    'protocolo': getattr(response, 'nroProtocoloAutorizacion', '') or '',
                }
            return {
                'success': True,
                'data': data,
                'message': mensaje or _('Operación exitosa'),
                'pdf': False, 'xml': False,
                'error_details': [],
                'duplicate_number': False,
            }

        # Failure: surface HKA's code as a structured neutral error item and
        # translate the duplicate-fiscal-number signal so the base can
        # regenerate the number and retry once.
        return {
            'success': False,
            'data': {},
            'message': mensaje or _('Error procesando la solicitud en HKA'),
            'pdf': False, 'xml': False,
            'error_details': [{'code': str(codigo), 'message': mensaje, 'field': ''}],
            'duplicate_number': bool(re.search(r'duplicad|ya\s+existe|ya\s+fue\s+registrad',
                                               mensaje, re.IGNORECASE)),
        }

    def _download_document(self, client, credentials, operation, datos_documento):
        """Call DescargaPDF / DescargaXML and return raw bytes or False."""
        try:
            service_op = getattr(client.service, operation)
            response = service_op(
                tokenEmpresa=credentials['tokenEmpresa'],
                tokenPassword=credentials['tokenPassword'],
                datosDocumento=datos_documento,
            )
            if response is not None and str(getattr(response, 'codigo', '')) in ('200', '201'):
                documento = getattr(response, 'documento', None)
                if documento:
                    try:
                        return base64.b64decode(documento)
                    except Exception as e:
                        _logger.error('Error decoding %s base64: %s', operation, str(e))
                        return False
                _logger.warning('%s: document not found in HKA response', operation)
            else:
                _logger.warning('Invalid response from HKA %s: %s', operation,
                                getattr(response, 'mensaje', 'Unknown error'))
            return False
        except Exception as e:
            _logger.error('%s download error: %s', operation, str(e))
            return False

    @staticmethod
    def _hka_datos_documento(data):
        """HKA document address block from the neutral document ref."""
        return {
            'codigoSucursalEmisor': data.get('branch_code') or '',
            'tipoDocumento': data.get('tipo_documento') or '',
            'numeroDocumentoFiscal': data.get('numero_documento_fiscal') or '',
            'puntoFacturacionFiscal': data.get('pos_code') or '',
            'tipoEmision': '01',
        }

    # ------------------------------------------------------------------
    # Neutral doc -> HKA 'documento' payload
    # ------------------------------------------------------------------
    def _build_hka_documento(self, doc):
        """Serialize the neutral FE document into HKA's ``documento`` block."""
        # NOTE: the legacy module stamped the (naive UTC) timestamp with a
        # literal -05:00 offset; preserved as-is for payload parity with years
        # of accepted production documents.
        fecha = doc.get('issue_datetime')
        fecha_str = (fecha.strftime('%Y-%m-%dT%H:%M:%S-05:00')
                     if fecha else '')
        buyer = doc.get('buyer') or {}
        items = self._build_items(doc)

        config = self.env.company.fe_configuration_id
        documento = {
            'codigoSucursalEmisor': doc.get('branch_code') or '',
            'tipoSucursal': (config and config.tipo_sucursal) or '1',
            'datosTransaccion': {
                'tipoEmision': '01',
                'tipoDocumento': doc.get('doc_type') or '01',
                'numeroDocumentoFiscal': doc.get('numero_documento_fiscal') or '',
                'puntoFacturacionFiscal': doc.get('pos_code') or '',
                'naturalezaOperacion': doc.get('nature') or '01',
                'tipoOperacion': '1',
                # DestinoOperacion describes the OPERATION, not the buyer's
                # nationality: only an export invoice (doc type '03') is
                # destino 2. Partner country data is unreliable (prod
                # extranjeros carry country=PA), so never key this off it.
                'destinoOperacion': '2' if doc.get('doc_type') == '03' else '1',
                'formatoCAFE': '1',
                'entregaCAFE': '1',
                'envioContenedor': '1',
                'procesoGeneracion': '1',
                'tipoVenta': '',
                'fechaEmision': fecha_str,
                'fechaSalida': fecha_str,
                'cliente': self._build_client(buyer),
            },
            'listaItems': {
                'item': items,
            },
            'totalesSubTotales': self._build_totals(doc, items),
        }

        # Referenced-document block for NC referente a FE ('04').
        if doc.get('doc_type') == '04':
            ref = doc.get('reference') or {}
            if not ref.get('cufe'):
                raise UserError(_('La factura referenciada debe tener un CUFE válido'))
            ref_dt = ref.get('date')
            fecha_ref = (ref_dt.strftime('%Y-%m-%dT%H:%M:%S-05:00')
                         if hasattr(ref_dt, 'strftime') else (fecha_str or ''))
            dt = documento['datosTransaccion']
            dt['informacionInteres'] = 'Factura de nota de credito referenciada'
            dt['listaDocsFiscalReferenciados'] = {
                'docFiscalReferenciado': [{
                    'fechaEmisionDocFiscalReferenciado': fecha_ref,
                    'cufeFEReferenciada': ref['cufe'],
                    'nroFacturaPapel': '',
                    'nroFacturaImpFiscal': '',
                }]
            }
        return documento

    def _build_client(self, buyer):
        """HKA ``cliente`` block from the neutral buyer party."""
        ruc = (buyer.get('ruc') or '').strip()
        # Consumidor Final
        if ruc.upper() == 'CF':
            return {
                'tipoClienteFE': '02',
                'razonSocial': buyer.get('name') or '',
                'direccion': '',
                'telefono1': '',
                'correoElectronico1': '',
                'pais': 'PA',
            }
        # Extranjero
        if buyer.get('tipo_cliente_fe') == '04':
            return {
                'tipoClienteFE': '04',
                'tipoIdentificacion': '99',
                'nroIdentificacionExtranjero': ruc,
                'razonSocial': buyer.get('name') or '',
                'correoElectronico1': buyer.get('email') or '',
                'telefono1': buyer.get('phone') or '',
                'pais': 'ZZ',
                'paisOtro': buyer.get('country_name') or '',
            }
        # Regular contribuyente
        state = buyer.get('state') or {}
        distrito = buyer.get('distrito') or {}
        corregimiento = buyer.get('corregimiento') or {}
        codigo_ubicacion = buyer.get('codigo_ubicacion') or (
            '%s-%s-%s' % (state.get('code') or '0',
                          distrito.get('code') or '0',
                          corregimiento.get('code') or '0'))
        return {
            'tipoClienteFE': buyer.get('tipo_cliente_fe') or '01',
            'tipoContribuyente': buyer.get('tipo_contribuyente') or '1',
            'numeroRUC': ruc,
            'digitoVerificadorRUC': str(buyer.get('dv') or '').zfill(2),
            'razonSocial': buyer.get('name') or '',
            'direccion': buyer.get('street') or '',
            'codigoUbicacion': codigo_ubicacion,
            'provincia': state.get('name') or '',
            'distrito': distrito.get('name') or '',
            'corregimiento': corregimiento.get('name') or '',
            'correoElectronico1': buyer.get('email') or '',
            'telefono1': buyer.get('phone') or '',
            'pais': 'PA',
        }

    @staticmethod
    def _split_negative_items(doc):
        """Partition neutral items into (positive, negative).

        Negative-price lines (POS loyalty/coupon rewards) cannot be HKA items
        (negative precioUnitario is rejected); the legacy module reported them
        in ``listaDescBonificacion``. Credit-note items arrive already
        absolute from the base, so the neutral ``is_negative`` flag (captured
        before the abs()) is what makes the split work inside an NC too."""
        positive, negative = [], []
        for it in (doc.get('items') or []):
            unit_price = it.get('unit_price') or 0.0
            price_total = it.get('price_total') or 0.0
            if it.get('is_negative') or unit_price < 0 or price_total < 0:
                negative.append(it)
            else:
                positive.append(it)
        return positive, negative

    def _build_items(self, doc):
        """HKA item list from the neutral items.

        The discount comes ONLY from the explicit ``discount_pct`` (see class
        docstring: no pricelist-discount fabrication)."""
        items = []
        positive_items, _negative = self._split_negative_items(doc)
        for it in positive_items:
            quantity = it.get('quantity') or 0.0
            unit_price = it.get('unit_price') or 0.0
            discount_pct = it.get('discount_pct') or 0.0
            discount_amount = (unit_price * discount_pct / 100.0) if discount_pct else 0.0
            price_after_discount = unit_price - discount_amount
            precio_item = price_after_discount * quantity
            valor_itbms = abs(it.get('tax_amount') or 0.0)
            valor_total = precio_item + valor_itbms
            items.append({
                'descripcion': self._sanitize_text(it.get('description')),
                'cantidad': '{:.3f}'.format(quantity),
                'precioUnitario': '{:.3f}'.format(unit_price),
                'precioUnitarioDescuento': '{:.3f}'.format(discount_amount),
                'precioItem': '{:.2f}'.format(precio_item),
                'valorTotal': '{:.2f}'.format(valor_total),
                'tasaITBMS': self._tax_rate_code(it.get('tax_rate')),
                'valorITBMS': '{:.2f}'.format(valor_itbms),
            })

        # Rounding-up adjustment as an extra zero-tax item (rounding down is
        # handled as a discount in the totals block).
        rounding = self._rounding_amount(doc)
        if rounding > 0.01:
            items.append({
                'descripcion': 'Ajuste por Redondeo',
                'cantidad': '1.000',
                'precioUnitario': '{:.3f}'.format(abs(rounding)),
                'precioUnitarioDescuento': '0.000',
                'precioItem': '{:.2f}'.format(abs(rounding)),
                'valorTotal': '{:.2f}'.format(abs(rounding)),
                'tasaITBMS': '00',
                'valorITBMS': '0.00',
            })
        return items

    def _build_totals(self, doc, items):
        """HKA ``totalesSubTotales`` block from the neutral totals/payments."""
        totals = doc.get('totals') or {}
        rounding = self._rounding_amount(doc)

        # Document-level discounts + negative (loyalty/coupon) lines, which the
        # HKA payload reports as descuentos/bonificaciones instead of items.
        _positive, negative_items = self._split_negative_items(doc)
        discounts = list(totals.get('discounts') or []) + [{
            'description': n.get('description') or 'Descuento',
            'amount': abs(n.get('price_total') or 0.0),
        } for n in negative_items if abs(n.get('price_total') or 0.0) > 0]

        total_todos_items = sum(float(i['valorTotal']) for i in items)
        total_precio_neto = sum(float(i['precioItem']) for i in items)
        total_itbms = sum(float(i.get('valorITBMS', '0.00')) for i in items)

        total_discounts = sum(d.get('amount') or 0.0 for d in discounts)
        if rounding < -0.01:
            total_discounts += abs(rounding)

        total_factura = total_todos_items - total_discounts

        payment_methods, total_payments, change_amount = self._build_payments(
            doc, total_factura)

        data = {
            'totalPrecioNeto': '{:.2f}'.format(total_precio_neto),
            'totalITBMS': '{:.2f}'.format(total_itbms),
            'totalMontoGravado': '{:.2f}'.format(total_itbms),
            'totalDescuento': '{:.2f}'.format(total_discounts) if total_discounts > 0 else '',
            'totalFactura': '{:.2f}'.format(total_factura),
            'totalValorRecibido': '{:.2f}'.format(total_payments),
            'vuelto': '{:.2f}'.format(change_amount),
            'tiempoPago': '1',
            'nroItems': str(len(items)),
            'totalTodosItems': '{:.2f}'.format(total_todos_items),
            'listaFormaPago': {
                'formaPago': payment_methods,
            }
        }

        discount_bonifications = []
        for d in discounts:
            desc = self._sanitize_text(d.get('description') or 'Descuento', max_length=30)
            discount_bonifications.append({
                'descDescuento': desc or 'Descuento',
                'montoDescuento': '{:.2f}'.format(abs(d.get('amount') or 0.0)),
            })
        if rounding < -0.01:
            discount_bonifications.append({
                'descDescuento': 'Ajuste por Redondeo',
                'montoDescuento': '{:.2f}'.format(abs(rounding)),
            })
        if discount_bonifications:
            data['listaDescBonificacion'] = {
                'descuentoBonificacion': discount_bonifications,
            }
        return data

    def _build_payments(self, doc, total_factura):
        """HKA payment list from the neutral payments block.

        Credit notes keep the legacy behavior (single cash refund line). The
        received total may exceed the invoice total (cash tendered at POS);
        the difference is reported as ``vuelto``."""
        if doc.get('is_credit_note'):
            refund_amount = abs(total_factura)
            return ([{
                'formaPagoFact': '02',
                'descFormaPago': '',
                'valorCuotaPagada': '{:.2f}'.format(refund_amount),
            }], refund_amount, 0.0)

        payment_methods = []
        total_payments = 0.0
        for pay in (doc.get('payments') or []):
            amount = pay.get('amount') or 0.0
            source = pay.get('payment_method') or pay.get('journal')
            neutral = getattr(source, 'fe_payment_type', False) or '01'
            forma_pago = self._PAYMENT_TYPE_MAP.get(neutral, '99')
            desc = ''
            if forma_pago == '99':
                desc = (getattr(source, 'name', '') or '')[:20]
            payment_methods.append({
                'formaPagoFact': forma_pago,
                'descFormaPago': desc,
                'valorCuotaPagada': '{:.2f}'.format(amount),
            })
            total_payments += amount

        if not payment_methods:
            payment_methods.append({
                'formaPagoFact': '02',
                'descFormaPago': '',
                'valorCuotaPagada': '{:.2f}'.format(total_factura),
            })
            total_payments = total_factura

        change_amount = total_payments - total_factura
        if change_amount < 0.01:
            change_amount = 0.0
        return payment_methods, total_payments, change_amount

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _rounding_amount(doc):
        """POS cash-rounding delta: document total vs raw line totals.

        The neutral totals carry ``total`` (the legal document total, cash
        rounding applied) while the items/discounts carry raw line values; any
        difference is the rounding adjustment HKA must see explicitly. Items
        sum SIGNED (negative loyalty lines subtract, as in the legacy
        all-lines sum); document-level discount lines re-add their amount
        because the base excludes them from items but they are part of the
        accounting total."""
        totals = (doc.get('totals') or {})
        total = totals.get('total') or 0.0
        items_total = sum(i.get('price_total') or 0.0 for i in (doc.get('items') or []))
        discounts_total = sum(d.get('amount') or 0.0 for d in (totals.get('discounts') or []))
        return total - (items_total - discounts_total)

    @staticmethod
    def _tax_rate_code(rate):
        """HKA tasaITBMS code from a raw percentage."""
        try:
            rate = float(rate or 0.0)
        except (TypeError, ValueError):
            return '00'
        if abs(rate - 7.0) < 0.01:
            return '01'
        if abs(rate - 10.0) < 0.01:
            return '02'
        if abs(rate - 15.0) < 0.01:
            return '03'
        return '00'

    @staticmethod
    def _sanitize_text(text, max_length=50):
        """ASCII-normalize and clip free text for HKA fields."""
        if not text:
            return 'Descuento'
        text = unicodedata.normalize('NFD', str(text))
        text = ''.join(ch for ch in text if unicodedata.category(ch) != 'Mn')
        sanitized = re.sub(r'[^\w\s.-]', '', text)
        sanitized = re.sub(r'\[.*?\]', '', sanitized)
        sanitized = ' '.join(sanitized.split())
        sanitized = sanitized[:max_length] if sanitized else ''
        return sanitized.strip() or 'Descuento'[:max_length]
