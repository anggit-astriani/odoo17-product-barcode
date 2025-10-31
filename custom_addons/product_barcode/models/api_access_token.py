from odoo import models, fields

# ============================================================
# MODEL: API Access Token
# ============================================================
# Model ini digunakan untuk menyimpan token akses API bagi setiap user.
# Digunakan untuk autentikasi API berbasis token.
# ============================================================
class ApiAccessToken(models.Model):
    _name = 'api.access.token'
    _description = 'API Access Token'
    
    user_id = fields.Many2one('res.users', string='User', required=True, ondelete='cascade')
    token = fields.Char(string='Access Token', required=True, index=True)
    expires = fields.Datetime(string='Expiry Date', required=True)
    
    _sql_constraints = [
        # Pastikan setiap token bersifat unik
        ('token_unique', 'unique(token)', 'Token must be unique!')
    ]
    # => Constraint ini memastikan tidak ada dua token yang sama di database