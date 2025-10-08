from odoo import http
from odoo.http import request, Response
import json

class ApiStockPicking(http.Controller):

    @http.route('/api/receipts', type='http', auth='public', methods=['GET'], csrf=False)
    def get_receipts(self, **params):
        """
        API GET untuk mengambil data stock.picking (Receipts) berdasarkan Warehouse.
        Contoh URL:
        /api/receipts?warehouse=WH
        """
        try:
            warehouse_code = params.get('warehouse')
            if not warehouse_code:
                return Response(
                    json.dumps({'error': 'Parameter warehouse is required'}),
                    status=400,
                    headers=[('Content-Type', 'application/json')]
                )
            
            warehouse = request.env['stock.warehouse'].sudo().search([('code', '=', warehouse_code)], limit=1)
            if not warehouse:
                return Response(
                    json.dumps({'error': f'Warehouse with code {warehouse_code} not found'}),
                    status=404,
                    headers=[('Content-Type', 'application/json')]
                )
            
            picking_type = request.env['stock.picking.type'].sudo().search([
                ('code', '=', 'incoming'),
                ('warehouse_id', '=', warehouse.id)
            ], limit=1)
            if not picking_type:
                return Response(
                    json.dumps({'error': f'No incoming picking type found for warehouse {warehouse_code}'}),
                    status=404,
                    headers=[('Content-Type', 'application/json')]
                )
            
            receipts = request.env['stock.picking'].sudo().search([
                ('picking_type_id', '=', picking_type.id)
            ])

            result = []
            for receipt in receipts:
                result.append({
                    'id': receipt.id,
                    'reference': receipt.name,
                    'location_from': receipt.location_id.display_name,
                    'location_to': receipt.location_dest_id.display_name,
                    'partner': receipt.partner_id.name or '',
                    'scheduled_date': receipt.scheduled_date.strftime('%Y-%m-%d %H:%M:%S') if receipt.scheduled_date else None,
                    'source_document': receipt.origin or '',
                    'warehouse': warehouse.name,
                    'company': warehouse.company_id.name,
                    'status': receipt.state,
                })

            return Response(
                json.dumps({'data': result}),
                status=200,
                headers=[('Content-Type', 'application/json')]
            )
        
        except Exception as e:
            return Response(
                json.dumps({'error': str(e)}),
                status=500,
                headers=[('Content-Type', 'application/json')]
            )
            
        