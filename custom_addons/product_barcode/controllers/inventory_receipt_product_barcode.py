from odoo import http
from odoo.http import request, Response
import json

class BarcodeScanController(http.Controller):
    # @http.route('/api/barcode/scan', type='json', auth='public', methods=['POST'], csrf=False)
    # def scan_barcode(self, **params):
    #     """
    #     API untuk scan barcode dan ambil data produk dari receipt.
    #     Input JSON:
    #     {
    #         "jsonrpc": "2.0",
    #         "method": "call",
    #         "params": {
    #             "barcode": "12912001917624"
    #         },
    #         "id": 1
    #         }
    #     """
    #     barcode = params.get('barcode')
    #     if not barcode:
    #         return {
    #             "success": False,
    #             "message": "Barcode is required"
    #         }

    #     # cari data barcode di model inventory.receipt.product.detail
    #     detail = request.env['inventory.receipt.product.detail'].sudo().search(
    #         [('barcode', '=', barcode)], limit=1
    #     )

    #     if not detail:
    #         return {
    #             "success": False,
    #             "message": f"Barcode '{barcode}' not found"
    #         }

    #     # ambil data produk dari product_id
    #     product = detail.product_id

    #     return {
    #         "success": True,
    #         "message": "Barcode found",
    #         "data": {
    #             "barcode": detail.barcode,
    #             "product_code": detail.code_product,
    #             "product_name": product.name,
    #             "purchase_price": product.standard_price,
    #             "vendor": detail.vendor_id.name,
    #             "vendor_code": detail.vendor_code,
    #             "warehouse": detail.warehouse_id.name,
    #             "receipt": detail.receipt_id.name,
    #         }
    #     }
    

    @http.route('/api/barcode/scan', type='http', auth='public', methods=['GET'], csrf=False)
    def scan_barcode_get(self, **params):
        """
        API GET untuk scan barcode dan ambil data produk dari receipt.
        Query parameter: ?barcode=12912001917624
        """
        barcode = params.get('barcode')
        if not barcode:
            return Response(
                json.dumps({"success": False, "message": "Barcode is required"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # cari data barcode di model inventory.receipt.product.detail
        detail = request.env['inventory.receipt.product.detail'].sudo().search(
            [('barcode', '=', barcode)], limit=1
        )

        if not detail:
            return Response(
                json.dumps({"success": False, "message": f"Barcode '{barcode}' not found"}),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        # ambil data produk dari product_id
        product = detail.product_id

        data = {
            "success": True,
            "message": "Barcode found",
            "data": {
                "receipt": detail.receipt_id.name,
                "code_product": detail.code_product,
                "product_name": product.name,
                "warehouse": detail.warehouse_id.name,
                "barcode": detail.barcode,
                "purchase_price": product.standard_price,
                "vendor": detail.vendor_id.name,
                "vendor_code": detail.vendor_code,
                "status": detail.status_product,
            }
        }

        return Response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')]
        )
    

    @http.route('/api/barcode/update_status', type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_barcode_status(self, **kwargs):
        """
        API PATCH untuk update status product detail dan validate picking.
        Request JSON body:
        {
            "receipt": "WH/IN/00009",
            "barcodes": ["123456789", "987654321"]
        }
        """

        # --- Parsing body JSON ---
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return Response(
                json.dumps({"success": False, "message": "Invalid JSON format"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        receipt = data.get('receipt')
        barcodes = data.get('barcodes')

        # --- Validasi input ---
        if not receipt:
            return Response(
                json.dumps({"success": False, "message": "receipt is required"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        if not barcodes or not isinstance(barcodes, list):
            return Response(
                json.dumps({"success": False, "message": "List of barcodes is required"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Cari picking berdasarkan name ---
        picking = request.env['stock.picking'].sudo().search([('name', '=', receipt)], limit=1)
        if not picking:
            return Response(
                json.dumps({"success": False, "message": f"Picking '{receipt}' not found"}),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        # --- Cari detail berdasarkan barcode ---
        details = request.env['inventory.receipt.product.detail'].sudo().search([
            ('barcode', 'in', barcodes)
        ])

        if not details:
            return Response(
                json.dumps({"success": False, "message": "No matching barcodes found"}),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        # --- Update status produk menjadi 'available' ---
        details.write({'status_product': 'available'})

        # --- Jalankan tombol Validate (button_validate) pada picking ---
        try:
            if picking.state not in ('done', 'cancel'):
                picking.button_validate()
        except Exception as e:
            return Response(
                json.dumps({
                    "success": False,
                    "message": f"Failed to validate picking: {str(e)}"
                }),
                headers=[('Content-Type', 'application/json')],
                status=500
            )

        # --- Response sukses ---
        response_data = {
            "success": True,
            "message": f"{len(details)} items updated and picking '{receipt}' validated.",
            "updated_barcodes": details.mapped('barcode'),
            "picking_status": picking.state
        }

        return Response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')],
            status=200
        )