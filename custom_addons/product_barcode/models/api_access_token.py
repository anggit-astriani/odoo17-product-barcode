from odoo import models, fields

class ApiAccessToken(models.Model):
    _name = 'api.access.token'
    _description = 'API Access Token'
    
    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade')
    token = fields.Char(string='Access Token', required=True, index=True)
    expires = fields.Datetime(string='Expiry Date', required=True)
    
    _sql_constraints = [
        ('token_unique', 'unique(token)', 'Token must be unique!')
    ]