from odoo import http, _
from odoo.http import request, Response
from odoo.exceptions import ValidationError, UserError
import json

class ApiInventorunternalTransfer(http.Controller):

    @http.route('/api/internal-transfer/detail', type='http', auth='public', methods=['GET'], csrf=False)
    def get_internal_transfer_detail(self, **params):
        """
        API GET untuk ambil semua data Inventory Transfer Product Detail berdasarkan transfer_id (nama dokumen picking).
        Contoh pemanggilan:
        GET /api/internal?transfer_id=WH/INT/00010
        """

        transfer_name = params.get('transfer_id')

        if not transfer_name:
            return Response(
                json.dumps({'error': 'Parameter transfer_id wajib diisi'}),
                status=400,
                headers=[('Content-Type', 'application/json')]
            )

        # Cari picking berdasarkan name (bukan ID)
        transfer = request.env['stock.picking'].sudo().search([('name', '=', transfer_name)], limit=1)
        if not transfer:
            return Response(
                json.dumps({'error': f'Transfer dengan ID {transfer_name} tidak ditemukan'}),
                status=404,
                headers=[('Content-Type', 'application/json')]
            )

        # Ambil record transfer product detail berdasarkan picking
        records = request.env['inventory.transfer.product.detail'].sudo().search([
            ('transfer_id', '=', transfer.id)
        ])

        result = []
        for rec in records:
            result.append({
                'id': rec.id,
                'transfer_id': rec.transfer_id.name if rec.transfer_id else '',
                'barcode': rec.barcode,
                'product_id': rec.product_id.id if rec.product_id else '',
                'product_name': rec.product_id.display_name if rec.product_id else '',
                'code_product': rec.code_product,
                'unique_code': rec.unique_code,
                'from_warehouse_id': rec.from_warehouse_id.id if rec.from_warehouse_id else '',
                'from_warehouse_name': rec.from_warehouse_id.name if rec.from_warehouse_id else '',
                'from_warehouse_code': rec.from_warehouse_id.code if rec.from_warehouse_id else '',
                'to_warehouse_id': rec.to_warehouse_id.id if rec.to_warehouse_id else '',
                'to_warehouse_name': rec.to_warehouse_id.name if rec.to_warehouse_id else '',
                'to_warehouse_code': rec.to_warehouse_id.code if rec.to_warehouse_id else '',
                'status_product': rec.product_detail_id.status_product if rec.product_detail_id else '',
            })

        return Response(
            json.dumps({
                'status': 'success',
                'message': 'Data transfer product detail fetched successfully.',
                'count': len(result),
                'data': result
            }),
            status=200,
            headers=[('Content-Type', 'application/json')]
        )
    

    # @http.route('/api/internal-transfer/create', type='http', auth='public', methods=['POST'], csrf=False)
    # def create_internal_transfer(self, **params):
    #     """
    #     Endpoint HTTP untuk create data internal transfer dari barcode product receipt.
    #     Param:
    #         POST /api/internal-transfer/create?barcode=1234567890
    #     """
    #     product_barcode = params.get('barcode')

    #     if not product_barcode:
    #         return Response(
    #                 json.dumps({
    #                     "status": "error",
    #                     "message": "Missing required parameter: barcode",
    #                     "code": "400"
    #                 }),
    #                 headers=[('Content-Type', 'application/json')],
    #                 status=400
    #             )

    #     # --- Cari product detail ---
    #     product_detail = request.env['inventory.receipt.product.detail'].sudo().search([
    #         ('barcode', '=', product_barcode),
    #         ('status_product', '=', 'available')
    #     ], limit=1)

    #     if not product_detail:
    #         return Response(
    #                 json.dumps({
    #                     "status": "error",
    #                     "message": f"Product with barcode '{product_barcode}' not found or not available.",
    #                     "code": "404"
    #                 }),
    #                 headers=[('Content-Type', 'application/json')],
    #                 status=404
    #             )

    #     from_wh = product_detail.warehouse_id
    #     if not from_wh:
    #         return Response(
    #                 json.dumps({
    #                     "status": "error",
    #                     "message": "Warehouse asal produk tidak ditemukan.",
    #                     "code": "400"
    #                 }),
    #                 headers=[('Content-Type', 'application/json')],
    #                 status=400
    #             )

    #     # --- Cari dokumen internal transfer aktif ---
    #     picking = request.env['stock.picking'].sudo().search([
    #         ('picking_type_id.code', '=', 'internal'),
    #         ('state', '=', 'draft'),
    #         ('location_id', '=', from_wh.lot_stock_id.id)
    #     ], order='id desc', limit=1)

    #     if not picking:
    #         return Response(
    #                 json.dumps({
    #                     "status": "error",
    #                     "message": f"Tidak ada dokumen internal transfer aktif dari warehouse {from_wh.name}.",
    #                     "code": "404"
    #                 }),
    #                 headers=[('Content-Type', 'application/json')],
    #                 status=404
    #             )

    #     # --- Tentukan to warehouse ---
    #     to_wh = request.env['stock.warehouse'].sudo().search([
    #         ('lot_stock_id', '=', picking.location_dest_id.id)
    #     ], limit=1)

    #     if not to_wh:
    #         return Response(
    #                 json.dumps({
    #                     "status": "error",
    #                     "message": "Warehouse tujuan tidak ditemukan.",
    #                     "code": "400"
    #                 }),
    #                 headers=[('Content-Type', 'application/json')],
    #                 status=400
    #             )

    #     # --- Buat record internal transfer product detail ---
    #     transfer = request.env['inventory.transfer.product.detail'].sudo().create({
    #         'transfer_id': picking.id,
    #         'product_detail_id': product_detail.id,
    #         'from_warehouse_id': from_wh.id,
    #         'to_warehouse_id': to_wh.id
    #     })

    #     # --- Update status product ---
    #     product_detail.sudo().write({
    #         'status_product': 'scanned',
    #         'scan_process': 'transfer'
    #     })

    #     return Response(
    #         json.dumps({
    #             'status': 'success',
    #             'message': f"Transfer created successfully with ID {transfer.id} on picking {picking.name}",
    #             'data': {
    #                 'transfer_id': transfer.id,
    #                 'picking_name': picking.name,
    #                 'barcode': product_detail.barcode,
    #                 'product_id': product_detail.product_id.id if product_detail.product_id else '',
    #                 'product_name': product_detail.product_id.display_name if product_detail.product_id else '',
    #                 'from_warehouse': from_wh.name,
    #                 'to_warehouse': to_wh.name,
    #                 'status_product': product_detail.status_product
    #             }
    #         }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=200
    #         )


    @http.route('/api/internal-transfer/create', type='http', auth='public', methods=['POST'], csrf=False)
    def create_internal_transfer(self, **params):
        """
        Endpoint HTTP untuk create data internal transfer dari barcode product receipt.
        Param:
            POST /api/internal-transfer/create?barcode=1234567890&transfer_id=WH/INT/00013
        """
        product_barcode = params.get('barcode')
        transfer_name = params.get('transfer_id')  # <-- Tambahan parameter baru

        if not product_barcode:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Missing required parameter: barcode",
                    "code": "400"
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Cari product detail ---
        product_detail = request.env['inventory.receipt.product.detail'].sudo().search([
            ('barcode', '=', product_barcode),
            ('status_product', '=', 'available')
        ], limit=1)

        if not product_detail:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Product with barcode '{product_barcode}' not found or not available.",
                    "code": "404"
                }),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        from_wh = product_detail.warehouse_id
        if not from_wh:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Warehouse asal produk tidak ditemukan.",
                    "code": "400"
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Cari dokumen internal transfer aktif ---
        if transfer_name:
            # Gunakan picking berdasarkan transfer_id jika diberikan
            picking = request.env['stock.picking'].sudo().search([
                ('name', '=', transfer_name),
                ('picking_type_id.code', '=', 'internal'),
                ('state', '=', 'draft')
            ], limit=1)
            if not picking:
                return Response(
                    json.dumps({
                        "status": "error",
                        "message": f"Internal transfer '{transfer_name}' tidak ditemukan.",
                        "code": "404"
                    }),
                    headers=[('Content-Type', 'application/json')],
                    status=404
                )
        else:
            # Fallback: ambil picking aktif dari warehouse asal
            picking = request.env['stock.picking'].sudo().search([
                ('picking_type_id.code', '=', 'internal'),
                ('state', '=', 'draft'),
                ('location_id', '=', from_wh.lot_stock_id.id)
            ], order='id desc', limit=1)
            if not picking:
                return Response(
                    json.dumps({
                        "status": "error",
                        "message": f"Tidak ada dokumen internal transfer aktif dari warehouse {from_wh.name}.",
                        "code": "404"
                    }),
                    headers=[('Content-Type', 'application/json')],
                    status=404
                )

        # --- Tentukan to warehouse ---
        to_wh = request.env['stock.warehouse'].sudo().search([
            ('lot_stock_id', '=', picking.location_dest_id.id)
        ], limit=1)

        if not to_wh:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Warehouse tujuan tidak ditemukan.",
                    "code": "400"
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Buat record internal transfer product detail ---
        transfer = request.env['inventory.transfer.product.detail'].sudo().create({
            'transfer_id': picking.id,
            'product_detail_id': product_detail.id,
            'from_warehouse_id': from_wh.id,
            'to_warehouse_id': to_wh.id
        })

        # --- Update status product ---
        product_detail.sudo().write({
            'status_product': 'scanned',
            'scan_process': 'transfer'
        })

        return Response(
            json.dumps({
                'status': 'success',
                'message': f"Transfer created successfully with ID {transfer.id} on picking {picking.name}",
                'data': {
                    'transfer_id': transfer.id,
                    'picking_name': picking.name,
                    'barcode': product_detail.barcode,
                    'product_id': product_detail.product_id.id if product_detail.product_id else '',
                    'product_name': product_detail.product_id.display_name if product_detail.product_id else '',
                    'from_warehouse': from_wh.name,
                    'to_warehouse': to_wh.name,
                    'status_product': product_detail.status_product
                }
            }),
            headers=[('Content-Type', 'application/json')],
            status=200
        )
    

    @http.route('/api/internal-transfer/transfer-product', type='http', auth='public', methods=['PATCH'], csrf=False)
    def transfer_product(self):
        try:
            # --- Ambil dan parse JSON dari body ---
            raw_data = request.httprequest.data
            try:
                payload = json.loads(raw_data)
            except Exception:
                raise ValidationError(_("Format JSON tidak valid."))

            transfer_id_str = payload.get('transfer_id')
            barcodes = payload.get('barcodes', [])

            if not transfer_id_str or not barcodes:
                raise ValidationError(_("'transfer_id' dan 'barcodes' wajib diisi."))

            # --- Cari dokumen internal transfer ---
            picking = request.env['stock.picking'].sudo().search([
                ('name', '=', transfer_id_str),
                ('state', '=', 'draft'),
                ('picking_type_id.code', '=', 'internal')
            ], limit=1)

            if not picking:
                raise UserError(_("Transfer ID %s tidak ditemukan atau statusnya bukan draft.") % transfer_id_str)

            # --- Jalankan tombol Mark as Todo jika belum done/cancel ---
            try:
                if picking.state not in ('done', 'cancel'):
                    picking.action_confirm()
            except Exception as e:
                return Response(
                    json.dumps({
                        "status": "error",
                        "message": f"Failed to validate picking: {str(e)}",
                        "code": "500"
                    }),
                    headers=[('Content-Type', 'application/json')],
                    status=500
                )

            # --- Cari transfer detail ---
            transfer_details = request.env['inventory.transfer.product.detail'].sudo().search([
                ('transfer_id', '=', picking.id),
                ('barcode', 'in', barcodes)
            ])

            if not transfer_details:
                raise UserError(_("Tidak ada data transfer product detail yang cocok dengan barcode tersebut."))

            # --- Update warehouse_id pada receipt detail ---
            updated_barcodes = []
            for detail in transfer_details:
                receipt_detail = request.env['inventory.receipt.product.detail'].sudo().search([
                    ('barcode', '=', detail.barcode)
                ], limit=1)

                if receipt_detail:
                    receipt_detail.write({
                        # 'warehouse_id': detail.to_warehouse_id.id,
                        'status_product': 'moving',
                        'scan_process': False
                    })
                    updated_barcodes.append(detail.barcode)

            return Response(
                json.dumps({
                    "status": "success",
                    "message": "Informasi detail product transfer berhasil dibuat.",
                    "data": {
                        "transfer_id": transfer_id_str,
                        "updated_barcodes": updated_barcodes,
                        "status": receipt_detail.status_product
                    }
                    
                }),
                headers=[('Content-Type', 'application/json')],
                status=200
            )

        except Exception as e:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": str(e),
                    "code": "500"
                }),
                headers=[('Content-Type', 'application/json')],
                status=500
            )
        
    
    # @http.route('/api/internal-transfer/validate-transfer-product', type='http', auth='public', methods=['PATCH'], csrf=False)
    # def validate_transfer_product(self):
    #     try:
    #         # --- Ambil dan parse JSON dari body ---
    #         raw_data = request.httprequest.data
    #         try:
    #             payload = json.loads(raw_data)
    #         except Exception:
    #             raise ValidationError(_("Format JSON tidak valid."))

    #         transfer_id_str = payload.get('transfer_id')

    #         # --- Cari dokumen internal transfer ---
    #         picking = request.env['stock.picking'].sudo().search([
    #             ('name', '=', transfer_id_str),
    #             ('picking_type_id.code', '=', 'internal')
    #         ], limit=1)

    #         if not picking:
    #             raise UserError(_("Transfer ID %s tidak ditemukan.") % transfer_id_str)

    #         # --- Jalankan tombol Mark as Todo jika belum done/cancel ---
    #         try:
    #             if picking.state not in ('done', 'cancel'):
    #                 picking.action_confirm()
    #         except Exception as e:
    #             return Response(
    #                 json.dumps({
    #                     "status": "error",
    #                     "message": f"Failed to validate picking: {str(e)}",
    #                     "code": "500"
    #                 }),
    #                 headers=[('Content-Type', 'application/json')],
    #                 status=500
    #             )

    #         # --- Cari transfer detail ---
    #         transfer_details = request.env['inventory.transfer.product.detail'].sudo().search([
    #             ('transfer_id', '=', picking.id),
    #         ])

    #         if not transfer_details:
    #             raise UserError(_("Tidak ada data transfer product detail yang cocok dengan barcode tersebut."))

    #         return Response(
    #             json.dumps({
    #                 "status": "success",
    #                 "message": "Informasi detail product transfer berhasil dibuat.",
    #                 "data": {
    #                     "transfer_id": transfer_id_str
    #                 }
                    
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=200
    #         )

    #     except Exception as e:
    #         return Response(
    #             json.dumps({
    #                 "status": "error",
    #                 "message": str(e),
    #                 "code": "500"
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=500
    #         )