from odoo import models, fields, api

class ResDistritoPa(models.Model):
    _name = 'res.distrito.pa'
    _description = 'Distritos de Panamá'
    _order = 'state_id, code'

    name = fields.Char('Nombre', required=True)
    code = fields.Char('Código', required=True)
    state_id = fields.Many2one('res.country.state', 'Provincia', required=True, 
        domain="[('country_id.code', '=', 'PA')]")
    corregimiento_ids = fields.One2many('res.corregimiento.pa', 'distrito_id', 'Corregimientos')

class ResCorregimientoPa(models.Model):
    _name = 'res.corregimiento.pa'
    _description = 'Corregimientos de Panamá'
    _order = 'distrito_id, code'

    name = fields.Char('Nombre', required=True)
    code = fields.Char('Código', required=True)
    distrito_id = fields.Many2one('res.distrito.pa', 'Distrito', required=True)
    state_id = fields.Many2one(related='distrito_id.state_id', store=True)
    active = fields.Boolean(default=True)

    def name_get(self):
        result = []
        for rec in self:
            name = f"{rec.state_id.name} - {rec.distrito_id.name} - {rec.name}"
            result.append((rec.id, name))
        return result