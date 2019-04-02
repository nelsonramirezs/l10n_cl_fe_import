# -*- coding: utf-8 -*-
# Part of Konos. See LICENSE file for full copyright and licensing details.

import tempfile
import binascii
import logging
from datetime import datetime
from odoo.exceptions import Warning
from odoo import models, fields, api, exceptions, _
from odoo.osv import expression
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT as DF
from io import StringIO
import io

_logger = logging.getLogger(__name__)
try:
    import csv
except ImportError:
    _logger.debug('Cannot `import csv`.')
try:
    import xlwt
except ImportError:
    _logger.debug('Cannot `import xlwt`.')
try:
    import cStringIO
except ImportError:
    _logger.debug('Cannot `import cStringIO`.')
try:
    import base64
except ImportError:
    _logger.debug('Cannot `import base64`.')
try:
    import xlrd
except ImportError:
    _logger.debug('Cannot `import xlrd`.')


class account_account_invoice_wizard(models.TransientModel):
    _name= "account.invoice.import.wizard"

    file = fields.Binary('File')
    file_opt = fields.Selection([('excel','Excel'),('csv','CSV')], default='csv')
    sii_opt = fields.Selection([('mipyme','MiPyme'),('propio','Propio'),('rcv','RCV')], default='propio')
    invoice_opt = fields.Selection([('compra','Compra'),('venta','Venta')], default='compra')

    @api.multi
    def import_file(self):
        if self.file_opt == 'csv':
            ##  Tipo Docto. RUT Contraparte Folio   Fecha Docto.    Monto Exento    Monto Neto  Tasa Impuesto   Monto IVA Recuperable   Monto Total
            #keys = ['Cant','tipo_doc','vat','partner','memo','amount','currency']   
            if self.sii_opt == 'mipyme':
                keys = ['cant','tipo_doc','vat','folio','fecha','monto_exento','monto_neto','tasa_impuesto','iva_recuperable','monto_total','anulado',
            'iva_retenido_total','iva_retenido_parcial','iva_no_retenido','iva_propio','16','17','18','19','20','21','22','23','24','otro_imp','valor_imp','27',
            '28','29','30','31','32','33','34','35','36','37','38','39','40','41','42','43','44','45','tipo_impuesto','nombre','48','49','50','51','52']
            elif self.sii_opt == 'rcv':
            	keys = ['cant','tipo_doc','3','vat','nombre','folio','fecha','8','9','monto_exento','monto_neto','iva_recuperable','13','14','monto_total','16','17','18','19','20','21','22','23','24','otro_imp','valor_imp','27']
            else: 
                keys = ['cant', 'vat','nombre','tipo_doc','folio','fecha','monto_total','fecha_recep','track_id']
            data = base64.b64decode(self.file)
            file_input = io.StringIO(data.decode("latin-1"))
            file_input.seek(0)
            reader_info = []
            reader = csv.reader(file_input, delimiter=';')
            try:
                reader_info.extend(reader)
            except Exception:
                raise exceptions.Warning(_("Not a valid file!"))
            values = {}
            for i in range(len(reader_info)):
                field = list(map(str, reader_info[i]))
                values = dict(zip(keys, field))
                if values:
                    if self.sii_opt == 'mipyme':
                        if i <= 8:
                            continue
                        else:
                            res = self._create_invoice(values)
                    elif self.sii_opt == 'rcv':
                        if i <= 0:
                            continue
                        else:
                            res = self._create_invoice(values)                         
                    else:
                        if i <= 1:
                            continue
                        else:
                            res = self._create_invoice(values)
        return res

    @api.multi
    def _create_invoice(self,val):

        #Reviso Que exista

        partner_id = self._find_partner(val.get('vat'))
        company_id = self.env['res.company'].search([], limit=1)


        #Si no lo creo
        if not partner_id:
            data = {
            'name' : val.get('nombre'),
            'vat': self.format_rut(val.get('vat')),
            'document_type_id': self.env.ref('l10n_cl_fe.dt_RUT').id,
            'responsability_id': self.env.ref('l10n_cl_fe.res_IVARI').id,
            'document_number': val.get('vat'),
            'company_type': 'company',
            }
            partner_id = self._create_partner(data)


        #Tipo de Factura
        tipo_factura = 'in_invoice'
        if self.invoice_opt == "venta":
            tipo_factura = 'out_invoice'
        if val.get('tipo_doc') in  ['54', '61']:
            tipo_factura = 'in_refund'
        if self.invoice_opt == "venta":
            tipo_factura = "out_refund"

        #Tipo de Documento en Mipyme y Propio vienen en dos formatos
        fecha_fact = ""
        if self.sii_opt == 'propio':
            fecha_fact = datetime.strptime(val.get('fecha'), '%Y-%m-%d').strftime('%Y-%m-%d')
            fecha_origen= datetime.strptime(val.get('fecha'), '%Y-%m-%d').strftime('%m-%Y')
            if val.get('tipo_doc')=='Factura Electronica':
                tipo_doc='33'
            elif val.get('tipo_doc')=='Nota de Credito Electronica':
                tipo_doc='61'
            elif val.get('tipo_doc')=='Nota de Débito Electrónica':
                tipo_doc='56'
            else:
                tipo_doc='34'     

        elif self.sii_opt == 'rcv':
            fecha_fact = datetime.strptime(val.get('fecha'), '%d/%m/%Y').strftime('%Y-%m-%d')
            fecha_origen= datetime.strptime(val.get('fecha'), '%d/%m/%Y').strftime('%m-%Y')
            tipo_doc=val.get('tipo_doc')

        else:
            fecha_fact = datetime.strptime(val.get('fecha'), '%d-%m-%Y').strftime('%Y-%m-%d')
            fecha_origen= datetime.strptime(val.get('fecha'), '%d-%m-%Y').strftime('%m-%Y')
            tipo_doc=val.get('tipo_doc')






        #Revisar si Factura Existe
        inv_exist = self.env['account.invoice'].search(
            [
                ('reference', '=', val.get('folio')),
                ('sii_document_class_id.sii_code', '=', tipo_doc),
                ('partner_id.vat', '=', self.format_rut(val.get('vat'))),
            ])

        if inv_exist:
            _logger.warning("factura existente")
        else:
            #Creo Instancia de Factura y líneas
            invoice_obj = self.env["account.invoice"]
            invoice_line_obj = self.env["account.invoice.line"]

            #TipoDTE 33
            #Busca el Diario que contiene este Doc
            journal_document_class_id = self._get_journal(tipo_doc)


            #Datos de la factura
            curr_invoice = {
                'origin' : "Carga Inicial: " + self.sii_opt + " " + fecha_origen + " " + val.get('cant'),
                'reference': val.get('folio'),
                'partner_id' : partner_id,
                'state': 'draft',
                'date_invoice': fecha_fact,
                'journal_id': journal_document_class_id.journal_id.id,
                'sii_document_class_id': journal_document_class_id.sii_document_class_id.id,
                'journal_document_class_id': journal_document_class_id.id,
                'type': tipo_factura,
                        }

            #Crea Factura
            inv_ids = invoice_obj.create(curr_invoice)



            #Busco Producto Afecto Genérico
            query = [('default_code', '=', 'PRODUCTO_AFECTO')]
            product_id = self.env['product.product'].search(query)

            #Primera Cuenta Contable que aparezca
            invoice_line_account = self.env['account.account'].search([('user_type_id', '=', self.env.ref('account.data_account_type_expenses').id)], limit=1).id
            IndAfec = 0
            IndExe = 0

            #Casos Factura Afecta y Exenta
            if self.sii_opt == 'propio':
                if tipo_doc =='34':
                    IndExe = int(val.get('monto_total'))
                elif tipo_doc =='33':
                    IndAfec = int(val.get('monto_total'))/1.19
                else:
                    IndAfec = int(val.get('monto_total'))
                    IndExe = 0
            else:
                #Monto Exento
                IndExe = int(val.get('monto_exento'))
                IndAfec = int(val.get('monto_neto'))
            
            


            # Si tiene exento
            if IndExe > 0:
                amount = 0
                sii_code = 0
                sii_type = False
                imp = self._buscar_impuesto(amount=amount, sii_code=sii_code, sii_type=sii_type, IndExe=True)

                #Datos de líneas de factura
                linea = {
                'product_id': product_id.id,
                'account_id': invoice_line_account,
                'name': 'Producto Exento',
                'price_unit': IndExe,  
                'quantity': 1.0,  
                'invoice_id': inv_ids.id, 
                'price_subtotal': IndExe, 
                'invoice_line_tax_ids': [(6, 0, imp.ids)],   
                }
                curr_invoice_line = invoice_line_obj.create(linea) 


            #Si tiene afecto entonces buscamos el impuesto
            if IndAfec > 0:
                amount = 19
                sii_code = 14
                sii_type = False
                imp = self._buscar_impuesto(amount=amount, sii_code=sii_code, sii_type=sii_type, IndExe=False)
                linea = {
                'product_id': product_id.id,
                'account_id': invoice_line_account,
                'name': 'Producto Afecto',
                'price_unit': IndAfec,  
                'quantity': 1.0,  
                'invoice_id': inv_ids.id,  
                'price_subtotal': IndAfec, 
                'invoice_line_tax_ids': [(6, 0, imp.ids)],   
                }
                curr_invoice_line = invoice_line_obj.create(linea) 
                
                #Por ahora cargaremos cualquier otro impuesto como un producto
            if val.get('otro_imp'):
                sii_code = [val.get('otro_imp')]
                sii_type = False
                imp = self._buscar_impuestos(amount=amount, sii_code=sii_code, sii_type=sii_type, IndExe=False)
                linea = {
                'product_id': product_id.id,
                'account_id': invoice_line_account,
                'name': 'Otro Impuesto',
                'price_unit': val.get('valor_imp'),  
                'quantity': 1.0,  
                'invoice_id': inv_ids.id,  
                'price_subtotal': val.get('valor_imp'), 
                'invoice_line_tax_ids': [(6, 0, imp.ids)],   
                }
                curr_invoice_line = invoice_line_obj.create(linea) 


            inv_ids.compute_taxes()
            #Revision de impuestos fijos
            #if inv_ids.tax_line_ids:
            #    for tax_line in inv_ids.tax_line_ids:
            #        if tax_line.name in ['Impuesto especifico diesel']:
            #            tax_line.amount_total = val.get('valor_imp')

            return True

    def _find_partner(self,rut):
        partner_id = self.env['res.partner'].search(
            [
                ('active','=', True),
                ('parent_id', '=', False),
                ('vat','=', self.format_rut(rut))
            ])
        if partner_id:
            return partner_id.id
        else:
            return

    def format_rut(self, RUTEmisor=None):
        rut = RUTEmisor.replace('-', '')
        if int(rut[:-1]) < 10000000:
            try:
                rut = '0' + str(int(rut))
            except:
                rut = '0' + str(rut)
        rut = 'CL' + rut
        return rut


    def _get_journal(self, sii_code):
        type = 'purchase'
        if self.invoice_opt == 'ventas':
            type = 'sale'
        journal_sii = self.env['account.journal.sii_document_class'].search(
            [
                ('sii_document_class_id.sii_code', '=', sii_code),
                ('journal_id.type', '=', type)
            ],
            limit=1,
        )
        return journal_sii


    def _create_partner(self, data):
        partner_id = self.env['res.partner'].create(data)
        if partner_id:
            return partner_id.id
        else:
            return

    def _buscar_impuesto(self, name="Impuesto", amount=0, sii_code=0, sii_type=False, IndExe=False):
        query = [
            ('amount', '=', amount),
            ('sii_code', '=', sii_code),
            ('type_tax_use', '=', ('purchase' if self.invoice_opt == 'compra' else 'sale')),
            ('activo_fijo', '=', False),
        ]
        if IndExe:
            query.append(
                    ('sii_type', '=', False)
            )
        if amount == 0 and sii_code == 0 and not IndExe:
            query.append(
                    ('name', '=', name)
            )
        if sii_type:
            query.extend( [
                ('sii_type', '=', sii_type),
            ])
        imp = self.env['account.tax'].search( query, limit=1)
        if not imp:
            imp = self.env['account.tax'].sudo().create( {
                'amount': amount,
                'name': name,
                'sii_code': sii_code,
                'sii_type': sii_type,
                'type_tax_use': 'purchase',
            } )
        return imp

    def _buscar_impuestos(self, name="Impuesto", amount=0, sii_code=0, sii_type=False, IndExe=False):
        query = [
            ('sii_code', 'in', sii_code),
            ('type_tax_use', '=', ('purchase' if self.invoice_opt == 'compra' else 'sale')),
            ('activo_fijo', '=', False),
        ]
        if IndExe:
            query.append(
                    ('sii_type', '=', False)
            )
        if amount == 0 and sii_code == 0 and not IndExe:
            query.append(
                    ('name', '=', name)
            )
        if sii_type:
            query.extend( [
                ('sii_type', '=', sii_type),
            ])
        imp = self.env['account.tax'].search(query)

        if not imp:
            imp = self.env['account.tax'].sudo().create( {
                'amount': amount,
                'name': name,
                'sii_code': sii_code,
                'sii_type': sii_type,
                'type_tax_use': 'purchase',
            } )
        return imp
