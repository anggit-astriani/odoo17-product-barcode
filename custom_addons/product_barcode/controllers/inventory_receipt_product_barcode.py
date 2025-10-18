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
    

    @http.route('/api/receipt/product_detail', type='http', auth='public', methods=['GET'], csrf=False)
    def get_receipt_product_detail(self, **params):
        """
        API GET untuk ambil semua data Inventory Receipt Product Detail berdasarkan receipt_id
        Contoh pemanggilan:
        GET /api/inventory/receipt_product?receipt_id=1
        """
        receipt_id = params.get('receipt_id')

        if not receipt_id:
            return Response(
                json.dumps({'error': 'Parameter receipt_id wajib diisi'}),
                status=400,
                headers=[('Content-Type', 'application/json')]
            )

        # try:
        #     receipt_id = int(receipt_id)
        # except ValueError:
        #     return Response(
        #         json.dumps({'error': 'receipt_id harus berupa angka'}),
        #         status=400,
        #         headers=[('Content-Type', 'application/json')]
        #     )

        # Ambil data dari model
        records = request.env['inventory.receipt.product.detail'].sudo().search([('receipt_id', '=', receipt_id)])

        result = []
        for rec in records:
            result.append({
                'id': rec.id,
                'receipt_id': rec.receipt_id.name if rec.receipt_id else '',
                'code_product': rec.code_product,
                'product_id': rec.product_id.id if rec.product_id else '',
                'product_name': rec.product_id.display_name if rec.product_id else '',
                'purchase_id': rec.purchase_id.name if rec.purchase_id else '',
                'warehouse_id': rec.warehouse_id.name if rec.warehouse_id else '',
                'warehouse_name': rec.warehouse_id.name if rec.warehouse_id else '',
                'delivery_id': rec.delivery_id.name if rec.delivery_id else '',
                'vendor_id': rec.vendor_id.id if rec.vendor_id else '',
                'vendor_name': rec.vendor_id.name if rec.vendor_id else '',
                'vendor_code': rec.vendor_code,
                'unique_code': rec.unique_code,
                'barcode': rec.barcode,
                'status_product': rec.status_product
            })

        return Response(
            json.dumps({
                'status': 'success',
                'message': 'Data fetched successfully.',
                'count': len(result),
                'data': result
            }),
            status=200,
            headers=[('Content-Type', 'application/json')]
        )
    
    @http.route('/api/barcode/scan', type='http', auth='public', methods=['GET'], csrf=False)
    def scan_barcode_get(self, **params):
        """
        API GET untuk scan barcode dan ambil data produk dari receipt.
        Query parameter: ?barcode=12912001917624
        """
        barcode = params.get('barcode')
        if not barcode:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Barcode is required",
                    "code": "400"
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # cari data barcode di model inventory.receipt.product.detail
        detail = request.env['inventory.receipt.product.detail'].sudo().search(
            [('barcode', '=', barcode)], limit=1
        )

        if not detail:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Barcode '{barcode}' not found",
                    "code": "404"
                }),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        # ambil data produk dari product_id
        product = detail.product_id

        data = {
            "status": "Success",
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
                "condition": detail.condition,
            }
        }

        return Response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')]
        )
    

    @http.route('/api/barcode/update_status', type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_product_status(self, **params):
        """
        API PATCH untuk update status product detail dan validate picking.
        Request JSON body:
        {
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

        barcodes = data.get('barcodes')

        # --- Validasi input ---
        if not barcodes or not isinstance(barcodes, list):
            return Response(
                json.dumps({"success": False, "message": "List of barcodes is required"}),
                headers=[('Content-Type', 'application/json')],
                status=400
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

        # --- Response sukses ---
        response_data = {
            "status": "Success",
            "message": f"{len(details)} items updated.",
            "updated_barcodes": details.mapped('barcode'),
        }

        return Response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')],
            status=200
        )
    
    @http.route('/api/barcode/update_stock', type='http', auth='public', methods=['PATCH'], csrf=False)
    def update_receipt_status(self, **params):
        """
        API PATCH untuk update status product detail dan validate picking.
        Request JSON body:
        {
            "receipt": "WH/IN/00009",
        }
        """

        # --- Parsing body JSON ---
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Invalid JSON format",
                    "code": "400"
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        receipt = data.get('receipt')

        # --- Validasi input ---
        if not receipt:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "receipt is required",
                    "code": "400"
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Cari picking berdasarkan name ---
        picking = request.env['stock.picking'].sudo().search([('name', '=', receipt)], limit=1)
        if not picking:
            return Response(
                json.dumps({
                    "status": "Success",
                    "message": f"Picking '{receipt}' not found"}),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        # --- Jalankan tombol Validate (button_validate) pada picking ---
        try:
            if picking.state not in ('done', 'cancel'):
                picking.button_validate()
        except Exception as e:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"error to validate picking: {str(e)}",
                    "code": "500"
                }),
                headers=[('Content-Type', 'application/json')],
                status=500
            )

        # --- Response sukses ---
        response_data = {
            "status": "Success",
            "message": f"Receipt '{receipt}' validated.",
            "receipt_status": picking.state
        }

        return Response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')],
            status=200
        )
    
    
    @http.route('/api/stock-product-available', type='http', auth='public', methods=['GET'], csrf=False)
    def get_stock_product_available(self, **params):
        """
        API GET untuk menampilkan semua data Inventory Receipt Product Detail
        dengan status 'available' berdasarkan warehouse code.
        Contoh:
        GET /api/stock-product-available?warehouse=WH
        """
        warehouse_code = params.get('warehouse')
        if not warehouse_code:
            return Response(
                json.dumps({'error': 'Parameter warehouse wajib diisi'}),
                status=400,
                headers=[('Content-Type', 'application/json')]
            )

        # Cari warehouse berdasarkan kode
        warehouse = request.env['stock.warehouse'].sudo().search([('code', '=', warehouse_code)], limit=1)
        if not warehouse:
            return Response(
                json.dumps({'error': f'Warehouse dengan code {warehouse_code} tidak ditemukan'}),
                status=404,
                headers=[('Content-Type', 'application/json')]
            )

        # Ambil data product receipt dengan status 'available'
        records = request.env['inventory.receipt.product.detail'].sudo().search([
            ('status_product', '=', 'available'),
            ('warehouse_id', '=', warehouse.id)
        ])

        result = []
        for rec in records:
            result.append({
                'id': rec.id,
                'receipt_id': rec.receipt_id.name if rec.receipt_id else '',
                'code_product': rec.code_product,
                'product_id': rec.product_id.id if rec.product_id else '',
                'product_name': rec.product_id.display_name if rec.product_id else '',
                'warehouse_id': rec.warehouse_id.id if rec.warehouse_id else '',
                'warehouse_code': warehouse.code,
                'warehouse_name': warehouse.name,
                'barcode': rec.barcode,
                'unique_code': rec.unique_code,
                'vendor_id': rec.vendor_id.id if rec.vendor_id else '',
                'vendor_name': rec.vendor_id.name if rec.vendor_id else '',
                'vendor_code': rec.vendor_code,
                'status_product': rec.status_product,
                'condition': rec.condition,
                'information': rec.information
            })

        return Response(
            json.dumps({
                'status': 'success',
                'message': f'Data product available di warehouse {warehouse_code} berhasil diambil.',
                'count': len(result),
                'data': result
            }),
            status=200,
            headers=[('Content-Type', 'application/json')]
        )