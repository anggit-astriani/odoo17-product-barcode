from odoo import fields
from odoo.http import request

def authenticate_token():
    """
    Validasi Bearer token dari header Authorization.
    Mengembalikan user (res.users) jika token valid, None jika tidak valid.
    """
    
    # Ambil header 'Authorization' dari request HTTP
    auth_header = request.httprequest.headers.get('Authorization')
    
    # Jika header tidak ada atau tidak diawali 'Bearer ', maka token dianggap tidak valid
    if not auth_header or not auth_header.startswith('Bearer '):
        return None  # Kembalikan None, artinya autentikasi gagal

    # Ambil token dari header, hapus kata 'Bearer ' dan spasi di sekitarnya
    token = auth_header.split(' ')[1].strip()
    
    # Cari record token di model 'api.access.token' berdasarkan token yang dikirim
    token_record = request.env['api.access.token'].sudo().search([('token', '=', token)], limit=1)

    # Validasi token:
    # - Apakah record token ditemukan
    # - Apakah token belum kadaluarsa (expires lebih besar dari waktu sekarang)
    if not token_record or token_record.expires <= fields.Datetime.now():
        return None  # Token tidak valid atau sudah expired

    # Jika valid, kembalikan user terkait token tersebut (field user_id)
    return token_record.user_id
