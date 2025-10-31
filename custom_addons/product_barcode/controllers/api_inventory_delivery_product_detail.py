from odoo import http, _
from odoo.http import request, Response
from odoo.exceptions import ValidationError, UserError
import json

class ApiInventoryDeliveryProductDetail(http.Controller):

    @http.route('/api/delivery/scan-barcode', type='http', auth='public', methods=['POST'], csrf=False)
    def scan_barcode_delivery(self):
        """
        Param:
            POST /api/delivery/scan-barcode
        Body (JSON):
        {
            "delivery_id": "WH/OUT/00026",
            "barcodes": ["484673445723"]
        }
        """
        try:
            # --- Ambil dan parse JSON body ---
            raw_data = request.httprequest.data
            try:
                payload = json.loads(raw_data)
            except Exception:
                raise ValidationError(_("Format JSON tidak valid."))

            delivery_id = payload.get('delivery_id')
            barcodes = payload.get('barcodes', [])

            if not delivery_id or not barcodes:
                raise ValidationError(_("'delivery_id' dan 'barcodes' wajib diisi."))

            # --- Cari dokumen Delivery ---
            picking = request.env['stock.picking'].sudo().search([
                ('name', '=', delivery_id),
                ('picking_type_id.code', '=', 'outgoing')
            ], limit=1)

            if not picking:
                raise UserError(_("Delivery ID %s tidak ditemukan.") % delivery_id)

            # --- Ambil warehouse dari delivery_id ---
            warehouse = picking.picking_type_id.warehouse_id
            if not warehouse:
                raise UserError(_("Warehouse tidak ditemukan dari delivery_id."))

            created_data = []

            for barcode in barcodes:
                # --- Cari data receipt product detail berdasarkan barcode ---
                receipt_detail = request.env['inventory.receipt.product.detail'].sudo().search([
                    ('barcode', '=', barcode),
                    ('status_product', '=', 'available')
                ], limit=1)

                if not receipt_detail:
                    continue  # skip jika tidak ditemukan / tidak available

                # --- Cek apakah barcode ini sudah pernah di-scan untuk delivery tersebut ---
                existing_detail = request.env['inventory.delivery.product.detail'].sudo().search([
                    ('delivery_id', '=', picking.id),
                    ('barcode', '=', barcode)
                ], limit=1)
                if existing_detail:
                    continue

                # --- Buat data delivery detail ---
                delivery_detail = request.env['inventory.delivery.product.detail'].sudo().create({
                    'delivery_id': picking.id,
                    'receipt_code_product': receipt_detail.id,
                    'warehouse_id': warehouse.id,
                })

                # --- Update status di receipt detail ---
                receipt_detail.sudo().write({
                    'status_product': 'scanned',
                    'scan_process': 'delivery',
                    'delivery_id': picking.id
                })

                created_data.append({
                    "delivery_id": picking.name,
                    "product_barcode": receipt_detail.barcode,
                    "product_code": receipt_detail.code_product,
                    "warehouse": warehouse.name,
                    "receipt": receipt_detail.receipt_id.name if receipt_detail.receipt_id else None,
                    "status_product": receipt_detail.status_product
                })

            if not created_data:
                raise UserError(_("Tidak ada barcode yang valid atau belum di-scan."))

            return Response(
                json.dumps({
                    "status": "success",
                    "message": "Barcode berhasil di-scan dan data delivery dibuat.",
                    "data": created_data
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
        
    @http.route('/api/delivery/detail', type='http', auth='public', methods=['GET'], csrf=False)
    def get_delivery_detail(self, delivery_id=None, **kwargs):
        """
        Param:
            GET /api/delivery/detail?delivery_id=WH/OUT/00020
        """
        try:
            if not delivery_id:
                raise ValueError(_("Parameter 'delivery_id' wajib diisi."))

            # --- Cari delivery picking ---
            picking = request.env['stock.picking'].sudo().search([
                ('name', '=', delivery_id),
                ('picking_type_id.code', '=', 'outgoing')
            ], limit=1)

            if not picking:
                raise ValueError(_("Delivery ID %s tidak ditemukan.") % delivery_id)

            # --- Ambil semua delivery product detail ---
            delivery_details = request.env['inventory.delivery.product.detail'].sudo().search([
                ('delivery_id', '=', picking.id)
            ])

            data = []
            for detail in delivery_details:
                data.append({
                    "delivery_id": picking.name,
                    "product_barcode": detail.barcode,
                    "product_code": detail.code_product,
                    "product_name": detail.product_id.name if detail.product_id else None,
                    "warehouse": detail.warehouse_id.name if detail.warehouse_id else None,
                    "status_product": detail.status_product,
                    "receipt": detail.receipt_code_product.receipt_id.name if detail.receipt_code_product and detail.receipt_code_product.receipt_id else None
                })

            return Response(
                json.dumps({
                    "status": "success",
                    "message": "Detail delivery product berhasil diambil.",
                    "data": data
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
        
    @http.route('/api/delivery/update-stock', type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_status_product_sold(self):
        """
        Contoh pemanggilan:
            PATCH /api/delivery/update-stock
        Body (JSON):
        {
            "delivery_id": "WH/OUT/00026",
            "barcodes": ["484673445723"]
        }
        """
        try:
            # --- Ambil dan parse JSON dari body ---
            raw_data = request.httprequest.data
            try:
                payload = json.loads(raw_data)
            except Exception:
                raise ValidationError(_("Format JSON tidak valid."))

            delivery_id = payload.get('delivery_id')
            barcodes = payload.get('barcodes', [])

            if not delivery_id or not barcodes:
                raise ValidationError(_("'delivery_id' dan 'barcodes' wajib diisi."))

            # --- Cari dokumen Delivery ---
            picking = request.env['stock.picking'].sudo().search([
                ('name', '=', delivery_id),
                # ('picking_type_id.code', '=', 'outgoing')
            ], limit=1)

            if not picking:
                raise UserError(_("Delivery ID %s tidak ditemukan.") % delivery_id)

            # --- Jalankan tombol Validate jika belum done/cancel ---
            try:
                if picking.state not in ('done', 'cancel'):
                    picking.button_validate()
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

            # --- Cari Delivery detail ---
            delivery_details = request.env['inventory.delivery.product.detail'].sudo().search([
                ('delivery_id', '=', picking.id),
                ('barcode', 'in', barcodes),
                ('status_product', '=', 'scanned')
            ])

            if not delivery_details:
                raise UserError(_("Tidak ada data delivery product detail yang cocok dengan barcode tersebut."))

            # --- Update warehouse_id pada receipt detail ---
            updated_barcodes = []
            for detail in delivery_details:
                receipt_detail = request.env['inventory.receipt.product.detail'].sudo().search([
                    ('barcode', '=', detail.barcode)
                ], limit=1)

                if receipt_detail:
                    receipt_detail.write({
                        'status_product': 'sold',
                        'scan_process': False,
                    })
                    updated_barcodes.append(detail.barcode)

            return Response(
                json.dumps({
                    "status": "success",
                    "message": "Picking divalidasi dan status product berhasil diperbarui.",
                    "data": {
                        "delivery_id": delivery_id,
                        "updated_barcodes": updated_barcodes,
                        "status" : receipt_detail.status_product
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