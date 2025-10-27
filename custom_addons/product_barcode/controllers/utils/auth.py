from odoo import fields
from odoo.http import request

def authenticate_token():
    """
    Validasi Bearer token dari header Authorization.
    Mengembalikan user (res.users) jika token valid, None jika tidak valid.
    """
    auth_header = request.httprequest.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return None

    token = auth_header.split(' ')[1].strip()
    token_record = request.env['api.access.token'].sudo().search([('token', '=', token)], limit=1)

    # Validasi token ada & belum expired
    if not token_record or token_record.expires <= fields.Datetime.now():
        return None

    return token_record.user_id
