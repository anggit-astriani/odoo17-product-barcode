from odoo import http, _
from odoo.http import request, Response
from odoo.exceptions import ValidationError, UserError
import json

class ApiInventorunternalTransferReceive(http.Controller):

    @http.route('/api/internal-transfer-receive/create', type='http', auth='public', methods=['POST'], csrf=False)
    def create_internal_transfer_receive(self, **params):
        """
        Endpoint HTTP untuk create data internal transfer receive berdasarkan barcode
        Param:
            POST /api/internal-transfer-receive/create?barcode=1234567890&transfer_id=WH/INT/00013
        """
        product_barcode = params.get('barcode')
        transfer_name = params.get('transfer_id')  # <-- Tambahan parameter baru

        if not product_barcode:
            return request.make_response(
                json.dumps({
                    "status": "error",
                    "message": "Missing required parameter: barcode",
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Cari data transfer product detail berdasarkan barcode ---
        domain = [('barcode', '=', product_barcode)]
        if transfer_name:
            # filter berdasarkan picking jika transfer_id diberikan
            picking = request.env['stock.picking'].sudo().search([('name', '=', transfer_name)], limit=1)
            if not picking:
                return Response(
                    json.dumps({
                        "status": "error",
                        "message": f"Internal transfer '{transfer_name}' not found.",
                    }),
                    headers=[('Content-Type', 'application/json')],
                    status=404
                )
            domain.append(('transfer_id', '=', picking.id))

        transfer_product = request.env['inventory.transfer.product.detail'].sudo().search(domain, limit=1)

        if not transfer_product:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Transfer product with barcode '{product_barcode}' not found.",
                }),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        # --- Ambil product receipt terkait ---
        product_receipt = transfer_product.product_detail_id
        if not product_receipt or product_receipt.status_product != 'moving':
            return request.make_response(
                json.dumps({
                    "status": "error",
                    "message": f"Product '{product_barcode}' must be in 'moving' status to be received.",
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Ambil picking internal transfer ---
        picking = transfer_product.transfer_id
        if not picking:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"No internal transfer document found for product '{product_barcode}'.",
                }),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        # --- Mapping warehouse asal dan tujuan ---
        from_wh = transfer_product.from_warehouse_id
        to_wh = transfer_product.to_warehouse_id
        if not from_wh or not to_wh:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Source or destination warehouse not found.",
                    "data": None
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Cek apakah sudah pernah diterima ---
        existing_receive = request.env['inventory.transfer.receive.product.detail'].sudo().search([
            ('product_transfer_id', '=', transfer_product.id)
        ], limit=1)

        if existing_receive:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Product '{product_barcode}' has already been received.",
                    "data": {
                        "receive_id": existing_receive.id,
                        "transfer_id": picking.name,
                        "barcode": product_barcode
                    }
                }),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # --- Buat record receive ---
        receive_record = request.env['inventory.transfer.receive.product.detail'].sudo().create({
            'transfer_id': picking.id,
            'product_transfer_id': transfer_product.id,
            'from_warehouse_id': from_wh.id,
            'to_warehouse_id': to_wh.id,
        })

        # --- Update status product receipt ---
        product_receipt.sudo().write({
            'status_product': 'scanned',
            'scan_process': 'transfer_receive'
        })

        return request.make_response(
            json.dumps({
                "status": "success",
                "message": f"Product '{product_barcode}' successfully received.",
                "data": {
                    "receive_id": receive_record.id,
                    "transfer_id": picking.name,
                    "barcode": product_barcode,
                    "product_id": transfer_product.product_id.id,
                    "product_name": transfer_product.product_id.display_name,
                    "from_warehouse": from_wh.name,
                    "to_warehouse": to_wh.name,
                    "status_product": product_receipt.status_product,
                    "scan_process": product_receipt.scan_process
                }
            }),
            headers=[('Content-Type', 'application/json')],
            status=200
        )


    # @http.route('/api/internal-transfer-receive/create', type='http', auth='public', methods=['POST'], csrf=False)
    # def create_internal_transfer_receive(self, **params):
    #     """
    #     Endpoint HTTP untuk create data internal transfer receive berdasarkan transfer_id dan barcode.
    #     Payload JSON:
    #     {
    #         "transfer_id": "WH/INT/00013",
    #         "barcodes": "2341673920303"
    #     }
    #     """

    #     # --- Parsing JSON body dari request HTTP ---
    #     try:
    #         data = json.loads(request.httprequest.data.decode('utf-8'))
    #     except Exception:
    #         return Response(
    #             json.dumps({
    #                 "status": "error",
    #                 "message": "Invalid JSON payload."
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=400
    #         )

    #     transfer_name = data.get('transfer_id')
    #     product_barcode = data.get('barcodes')

    #     if not transfer_name or not product_barcode:
    #         return Response(
    #             json.dumps({
    #                 "status": "error",
    #                 "message": "Missing required parameter: transfer_id or barcodes",
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=400
    #         )

    #     # --- Cari picking transfer berdasarkan transfer_id ---
    #     picking = request.env['stock.picking'].sudo().search([('name', '=', transfer_name)], limit=1)
    #     if not picking:
    #         return Response(
    #             json.dumps({
    #                 "status": "error",
    #                 "message": f"Transfer document '{transfer_name}' not found."
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=404
    #         )

    #     # --- Cari data transfer product berdasarkan barcode & transfer_id ---
    #     transfer_product = request.env['inventory.transfer.product.detail'].sudo().search([
    #         ('barcode', '=', product_barcode),
    #         ('transfer_id', '=', picking.id)
    #     ], limit=1)

    #     if not transfer_product:
    #         return Response(
    #             json.dumps({
    #                 "status": "error",
    #                 "message": f"Transfer product with barcode '{product_barcode}' not found in transfer '{transfer_name}'.",
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=404
    #         )

    #     # --- Ambil product receipt ---
    #     product_receipt = transfer_product.product_detail_id
    #     if not product_receipt or product_receipt.status_product != 'moving':
    #         return Response(
    #             json.dumps({
    #                 "status": "error",
    #                 "message": f"Product '{product_barcode}' must be in 'moving' status to be received.",
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=400
    #         )

    #     # --- Ambil warehouse asal dan tujuan ---
    #     from_wh = transfer_product.from_warehouse_id
    #     to_wh = transfer_product.to_warehouse_id
    #     if not from_wh or not to_wh:
    #         return Response(
    #             json.dumps({
    #                 "status": "error",
    #                 "message": "Source or destination warehouse not found."
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=400
    #         )

    #     # --- Cek apakah sudah diterima ---
    #     existing_receive = request.env['inventory.transfer.receive.product.detail'].sudo().search([
    #         ('product_transfer_id', '=', transfer_product.id)
    #     ], limit=1)

    #     if existing_receive:
    #         return Response(
    #             json.dumps({
    #                 "status": "error",
    #                 "message": f"Product '{product_barcode}' has already been received.",
    #                 "data": {
    #                     "receive_id": existing_receive.id,
    #                     "transfer_id": picking.name,
    #                     "barcode": product_barcode
    #                 }
    #             }),
    #             headers=[('Content-Type', 'application/json')],
    #             status=400
    #         )

    #     # --- Buat record receive ---
    #     receive_record = request.env['inventory.transfer.receive.product.detail'].sudo().create({
    #         'transfer_id': picking.id,
    #         'product_transfer_id': transfer_product.id,
    #         'from_warehouse_id': from_wh.id,
    #         'to_warehouse_id': to_wh.id,
    #     })

    #     # --- Update status product receipt ---
    #     product_receipt.sudo().write({
    #         'status_product': 'scanned',
    #         'scan_process': 'transfer_receive'
    #     })

    #     return Response(
    #         json.dumps({
    #             "status": "success",
    #             "message": f"Product '{product_barcode}' successfully received.",
    #             "data": {
    #                 "receive_id": receive_record.id,
    #                 "transfer_id": picking.name,
    #                 "barcode": product_barcode,
    #                 "product_id": transfer_product.product_id.id,
    #                 "product_name": transfer_product.product_id.display_name,
    #                 "from_warehouse": from_wh.name,
    #                 "to_warehouse": to_wh.name,
    #                 "status_product": product_receipt.status_product,
    #                 "scan_process": product_receipt.scan_process
    #             }
    #         }),
    #         headers=[('Content-Type', 'application/json')],
    #         status=200
    #     )
    
    @http.route('/api/internal-transfer/transfer-product-receive', type='http', auth='public', methods=['PATCH'], csrf=False)
    def transfer_product_receive(self):
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
                ('picking_type_id.code', '=', 'internal')
            ], limit=1)

            if not picking:
                raise UserError(_("Transfer ID %s tidak ditemukan.") % transfer_id_str)

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

            # --- Cari transfer detail ---
            transfer_details = request.env['inventory.transfer.receive.product.detail'].sudo().search([
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
                        'warehouse_id': detail.to_warehouse_id.id,
                        'status_product': 'available',
                        'scan_process': False
                    })
                    updated_barcodes.append(detail.barcode)

            return Response(
                json.dumps({
                    "status": "success",
                    "message": "Picking divalidasi dan warehouse berhasil diperbarui.",
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
        

    # @http.route('/api/internal-transfer/validate-transfer-product-receive', type='http', auth='public', methods=['PATCH'], csrf=False)
    # def validate_transfer_product_receive(self):
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

    #         # --- Jalankan tombol Validate jika belum done/cancel ---
    #         try:
    #             if picking.state not in ('done', 'cancel'):
    #                 picking.button_validate()
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
    #             ('transfer_id', '=', picking.id)
    #         ])

    #         if not transfer_details:
    #             raise UserError(_("Tidak ada data transfer product detail yang cocok dengan barcode tersebut."))

    #         return Response(
    #             json.dumps({
    #                 "status": "success",
    #                 "message": "Picking divalidasi dan warehouse berhasil diperbarui.",
    #                 "data": {
    #                     "transfer_id": transfer_id_str,
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