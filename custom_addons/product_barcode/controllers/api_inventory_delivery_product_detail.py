from odoo import http, _
from odoo.http import request, Response
from odoo.exceptions import ValidationError, UserError
import json

class ApiInventoryDeliveryProductDetail(http.Controller):

    @http.route('/api/delivery/update-stock', type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_status_product_sold(self):
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
                ('barcode', 'in', barcodes)
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
                        'status_product': 'sold'
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