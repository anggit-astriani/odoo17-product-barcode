from odoo import http
from odoo.http import request
import json
import secrets
import hashlib
from datetime import datetime, timedelta

class ApiAuthorization(http.Controller):
    
    @http.route('/api/auth/login', type='http', auth='public', methods=['POST'], csrf=False)
    def login(self, **kwargs):
        """
        API endpoint untuk login Odoo dengan bearer token
        
        Form Data atau JSON Body:
        {
            "username": "anggit@gmail.com",
            "password": "user123"
        }
        
        Response Success:
        {
            "success": true,
            "message": "Login successful",
            "data": {
                "access_token": "bearer_token_here",
                "token_type": "Bearer",
                "expires_in": 3600,
                "user_id": 1,
                "username": "anggit@gmail.com",
                "name": "User Name"
            }
        }
        """
        try:
            # Ambil data dari request body (JSON) atau form data
            if request.httprequest.is_json:
                data = request.httprequest.get_json()
            else:
                data = request.params
            
            username = data.get('username')
            password = data.get('password')
            
            # Validasi input
            if not username or not password:
                response = {
                    'success': False,
                    'message': 'Username and password are required',
                    'error': 'missing_credentials'
                }
                return request.make_json_response(response, status=400)
            
            # Authenticate user
            try:
                uid = request.session.authenticate(
                    request.session.db,
                    username,
                    password
                )
            except Exception as e:
                response = {
                    'success': False,
                    'message': 'Invalid credentials',
                    'error': 'authentication_failed'
                }
                return request.make_json_response(response, status=401)
            
            if not uid:
                response = {
                    'success': False,
                    'message': 'Invalid credentials',
                    'error': 'authentication_failed'
                }
                return request.make_json_response(response, status=401)
            
            # Generate bearer token
            access_token = secrets.token_urlsafe(32)
            expires_in = 3600  # 1 hour
            expiry_date = datetime.now() + timedelta(seconds=expires_in)
            
            # Get user info
            user = request.env['res.users'].sudo().browse(uid)
            
            # Get company info
            company = user.company_id
            company_data = {
                'id': company.id,
                'name': company.name,
                'currency': company.currency_id.name if company.currency_id else None,
                'street': company.street or '',
                'city': company.city or '',
                'country': company.country_id.name if company.country_id else None,
                'phone': company.phone or '',
                'email': company.email or '',
            }
            
            # Get warehouse info (default warehouse for user)
            # default_warehouse = request.env['stock.warehouse'].sudo().search([
            #     ('company_id', '=', company.id)
            # ], limit=1)
            default_warehouse = user.property_warehouse_id
            
            warehouse_data = None
            if default_warehouse:
                warehouse_data = {
                    'id': default_warehouse.id,
                    'name': default_warehouse.name,
                    'code': default_warehouse.code,
                    'partner_id': default_warehouse.partner_id.id if default_warehouse.partner_id else None,
                    'address': default_warehouse.partner_id.contact_address if default_warehouse.partner_id else '',
                }
            
            # Get all warehouses for the company
            all_warehouses = request.env['stock.warehouse'].sudo().search([
                ('company_id', '=', company.id)
            ])
            
            warehouses_list = []
            for wh in all_warehouses:
                warehouses_list.append({
                    'id': wh.id,
                    'name': wh.name,
                    'code': wh.code,
                    'partner_id': wh.partner_id.id if wh.partner_id else None,
                    'address': wh.partner_id.contact_address if wh.partner_id else '',
                })
            
            # Store token in database
            token_record = request.env['api.access.token'].sudo().create({
                'user_id': uid,
                'token': access_token,
                'expires': expiry_date
            })
            
            response = {
                'success': True,
                'message': 'Login successful',
                'data': {
                    'access_token': access_token,
                    'token_type': 'Bearer',
                    'expires_in': expires_in,
                    'user_id': uid,
                    'username': user.login,
                    'name': user.name,
                    'company': company_data,
                    'default_warehouse': warehouse_data,
                    'warehouses': warehouses_list
                }
            }
            return request.make_json_response(response, status=200)
            
        except Exception as e:
            response = {
                'success': False,
                'message': str(e),
                'error': 'server_error'
            }
            return request.make_json_response(response, status=500)
    
    
    @http.route('/api/auth/logout', type='http', auth='public', methods=['POST'], csrf=False)
    def logout(self, **kwargs):
        """
        API endpoint untuk logout dan invalidate token
        
        Headers:
        Authorization: Bearer {access_token}
        """
        try:
            # Get token from header
            auth_header = request.httprequest.headers.get('Authorization')
            
            if not auth_header or not auth_header.startswith('Bearer '):
                response = {
                    'success': False,
                    'message': 'No token provided',
                    'error': 'missing_token'
                }
                return request.make_json_response(response, status=401)
            
            token = auth_header.replace('Bearer ', '')
            
            # Find and delete token
            token_record = request.env['api.access.token'].sudo().search([
                ('token', '=', token)
            ], limit=1)
            
            if token_record:
                token_record.unlink()
                response = {
                    'success': True,
                    'message': 'Logout successful'
                }
                return request.make_json_response(response, status=200)
            else:
                response = {
                    'success': False,
                    'message': 'Invalid token',
                    'error': 'invalid_token'
                }
                return request.make_json_response(response, status=401)
                
        except Exception as e:
            response = {
                'success': False,
                'message': str(e),
                'error': 'server_error'
            }
            return request.make_json_response(response, status=500)
    
    
    # @http.route('/api/auth/verify', type='http', auth='public', methods=['POST', 'GET'], csrf=False)
    # def verify_token(self, **kwargs):
    #     """
    #     API endpoint untuk verify bearer token
        
    #     Headers:
    #     Authorization: Bearer {access_token}
    #     """
    #     try:
    #         # Get token from header
    #         auth_header = request.httprequest.headers.get('Authorization')
            
    #         if not auth_header or not auth_header.startswith('Bearer '):
    #             response = {
    #                 'success': False,
    #                 'message': 'No token provided',
    #                 'error': 'missing_token'
    #             }
    #             return request.make_json_response(response, status=401)
            
    #         token = auth_header.replace('Bearer ', '')
            
    #         # Verify token
    #         token_record = request.env['api.access.token'].sudo().search([
    #             ('token', '=', token),
    #             ('expires', '>', datetime.now())
    #         ], limit=1)
            
    #         if token_record:
    #             user = token_record.user_id
    #             response = {
    #                 'success': True,
    #                 'message': 'Token is valid',
    #                 'data': {
    #                     'user_id': user.id,
    #                     'username': user.login,
    #                     'name': user.name,
    #                     'expires': token_record.expires.isoformat()
    #                 }
    #             }
    #             return request.make_json_response(response, status=200)
    #         else:
    #             response = {
    #                 'success': False,
    #                 'message': 'Invalid or expired token',
    #                 'error': 'invalid_token'
    #             }
    #             return request.make_json_response(response, status=401)
                
    #     except Exception as e:
    #         response = {
    #             'success': False,
    #             'message': str(e),
    #             'error': 'server_error'
    #         }
    #         return request.make_json_response(response, status=500)


# Middleware untuk protected routes
def check_bearer_token():
    """
    Function helper untuk check bearer token di protected routes
    Usage dalam controller lain:
    
    from . import auth_api
    
    @http.route('/api/protected/resource', type='http', auth='public', methods=['GET'], csrf=False)
    def get_resource(self, **kwargs):
        auth_result = auth_api.check_bearer_token()
        if not auth_result['success']:
            return request.make_json_response(auth_result, status=401)
        
        user_id = auth_result['user_id']
        # Your logic here
        response = {'success': True, 'data': 'your_data'}
        return request.make_json_response(response)
    """
    auth_header = request.httprequest.headers.get('Authorization')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return {
            'success': False,
            'message': 'No token provided',
            'error': 'missing_token',
            'user_id': None
        }
    
    token = auth_header.replace('Bearer ', '')
    
    token_record = request.env['api.access.token'].sudo().search([
        ('token', '=', token),
        ('expires', '>', datetime.now())
    ], limit=1)
    
    if token_record:
        return {
            'success': True,
            'user_id': token_record.user_id.id,
            'user': token_record.user_id
        }
    else:
        return {
            'success': False,
            'message': 'Invalid or expired token',
            'error': 'invalid_token',
            'user_id': None
        }