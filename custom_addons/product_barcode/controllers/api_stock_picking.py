from odoo import http, fields
from odoo.http import request, Response
import json
from .utils.auth import authenticate_token

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
                json.dumps({
                    'status': 'success',
                    'message': 'Data fetched successfully.',
                    'warehouse': warehouse_code,
                    'total': len(result),
                    'data': result
                    }),
                status=200,
                headers=[('Content-Type', 'application/json')]
            )
        
        except Exception as e:
            return Response(
                json.dumps({'error': str(e)}),
                status=500,
                headers=[('Content-Type', 'application/json')]
            )
    

    @http.route('/api/internal-transfer', type='http', auth='public', methods=['GET'], csrf=False)
    def get_internal_transfers(self, **params):
        """
        API GET untuk menampilkan list internal transfer berdasarkan warehouse.
        Contoh:
        GET /api/internal-transfer?warehouse=WH
        """
        warehouse_code = params.get('warehouse')
        if not warehouse_code:
            response = {
                'status': 400,
                'message': 'Parameter "warehouse" wajib diisi'
            }
            return request.make_response(
                json.dumps(response),
                headers=[('Content-Type', 'application/json')]
            )

        # Cari picking type internal transfer untuk warehouse terkait
        picking_type = request.env['stock.picking.type'].sudo().search([
            ('warehouse_id.code', '=', warehouse_code),
            ('code', '=', 'internal')
        ], limit=1)

        if not picking_type:
            response = {
                'status': 404,
                'message': f'Warehouse dengan code {warehouse_code} tidak ditemukan atau tidak punya internal transfer'
            }
            return request.make_response(
                json.dumps(response),
                headers=[('Content-Type', 'application/json')]
            )

        # Ambil semua stock.picking untuk tipe internal transfer tersebut
        pickings = request.env['stock.picking'].sudo().search([
            ('picking_type_id', '=', picking_type.id)
        ], order='id desc')

        data = []
        for p in pickings:
            data.append({
                'id': p.id,
                'reference': p.name,
                'from_location': p.location_id.complete_name if p.location_id else '',
                'to_location': p.location_dest_id.complete_name if p.location_dest_id else '',
                'partner': p.partner_id.name if p.partner_id else '',
                'scheduled_date': p.scheduled_date.strftime('%Y-%m-%d %H:%M:%S') if p.scheduled_date else '',
                'source_document': p.origin or '',
                'company': p.company_id.name if p.company_id else '',
                'status': p.state
            })

        response = {
            'status': 'success',
            'message': 'Data fetched successfully.',
            'warehouse': warehouse_code,
            'total': len(data),
            'data': data
        }

        return request.make_response(
            json.dumps(response),
            headers=[('Content-Type', 'application/json')]
        )


    @http.route('/api/delivery-orders', type='http', auth='public', methods=['GET'], csrf=False)
    def get_delivery_orders(self, **params):
        """
        API GET untuk menampilkan list Delivery Orders berdasarkan warehouse code.
        Contoh: GET /api/delivery-orders?warehouse=WH
        """
        warehouse_code = params.get('warehouse')
        if not warehouse_code:
            response = {
                'status': 400,
                'message': 'Parameter "warehouse" wajib diisi'
            }
            return request.make_response(
                json.dumps(response),
                headers=[('Content-Type', 'application/json')]
            )

        # Cari picking type untuk delivery orders (outgoing) dari warehouse tersebut
        picking_type = request.env['stock.picking.type'].sudo().search([
            ('warehouse_id.code', '=', warehouse_code),
            ('code', '=', 'outgoing')
        ], limit=1)

        if not picking_type:
            response = {
                'status': 404,
                'message': f'Warehouse dengan kode {warehouse_code} tidak ditemukan atau tidak punya Delivery Order'
            }
            return request.make_response(
                json.dumps(response),
                headers=[('Content-Type', 'application/json')]
            )

        # Ambil semua DO (stock.picking) dengan picking_type_id tersebut
        delivery_orders = request.env['stock.picking'].sudo().search([
            ('picking_type_id', '=', picking_type.id)
        ], order='id desc')

        data = []
        for do in delivery_orders:
            data.append({
                'id': do.id,
                'reference': do.name,
                'from_location': do.location_id.complete_name if do.location_id else '',
                'to_location': do.location_dest_id.complete_name if do.location_dest_id else '',
                'partner': do.partner_id.name if do.partner_id else '',
                'scheduled_date': do.scheduled_date.strftime('%Y-%m-%d %H:%M:%S') if do.scheduled_date else '',
                'source_document': do.origin or '',
                'company': do.company_id.name if do.company_id else '',
                'status': do.state
            })

        response = {
            'status': 'success',
            'message': 'Data fetched successfully.',
            'warehouse': warehouse_code,
            'total': len(data),
            'data': data
        }

        return request.make_response(
            json.dumps(response),
            headers=[('Content-Type', 'application/json')]
        )


    @http.route('/api/inventory/overview', type='http', auth='public', methods=['GET'], csrf=False)
    def get_inventory_overview(self, **params):
        """
        API GET untuk menampilkan ringkasan Inventory Overview:
        - Receipts
        - Internal Transfers
        - Delivery Orders
        Per warehouse + warehouse code.
        Contoh: GET /api/inventory/overview
        """

        # kode untuk login user, saat ini dimatikan dulu
        # user = authenticate_token()
        # if not user:
        #     return request.make_response(
        #         json.dumps({
        #             'status': 401,
        #             'message': 'Unauthorized: Invalid or expired token'
        #         }),
        #         headers=[('Content-Type', 'application/json')]
        #     )

        picking_types = request.env['stock.picking.type'].sudo().search([])
        result = []

        for picking_type in picking_types:
            warehouse = picking_type.warehouse_id

            # Hitung picking yang belum diproses
            to_process_count = request.env['stock.picking'].sudo().search_count([
                ('picking_type_id', '=', picking_type.id),
                ('state', 'in', ['confirmed', 'assigned', 'waiting'])
            ])

            # Hitung picking yang terlambat
            late_count = request.env['stock.picking'].sudo().search_count([
                ('picking_type_id', '=', picking_type.id),
                ('scheduled_date', '<', fields.Datetime.now()),
                ('state', 'in', ['confirmed', 'assigned', 'waiting'])
            ])

            # Hitung picking yang waiting
            waiting_count = request.env['stock.picking'].sudo().search_count([
                ('picking_type_id', '=', picking_type.id),
                ('state', '=', 'waiting')
            ])

            result.append({
                'warehouse_name': warehouse.name if warehouse else '',
                'warehouse_code': warehouse.code if warehouse else '',
                'picking_type': picking_type.name,
                'picking_code': picking_type.code,
                'to_process': to_process_count,
                'waiting': waiting_count,
                'late': late_count,
            })

        response_data = {
            'status': 200,
            'message': 'Inventory overview retrieved successfully',
            'data': result
        }

        return request.make_response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')]
        )