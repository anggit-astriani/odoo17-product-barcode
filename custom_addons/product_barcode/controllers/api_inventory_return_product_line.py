from odoo import http
from odoo.http import request, Response
import json

class ApiReturnProductLine(http.Controller):

    @http.route('/api/return/items', type='http', auth='public', methods=['GET'], csrf=False)
    def get_return_items(self, **kwargs):
        """
        Endpoint: GET /api/return/items?return=RTN/00014
        Deskripsi: Menampilkan list item dari return berdasarkan nomor return (name)
        """
        return_number = kwargs.get('return')

        if not return_number:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Parameter 'return' wajib diisi, contoh: /api/return/items?return=RTN/00014"
                }),
                status=400,
                content_type='application/json'
            )

        # Cari record return berdasarkan nomor (name)
        return_record = request.env['inventory.return.product'].sudo().search([
            ('name', '=', return_number)
        ], limit=1)

        if not return_record:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Return dengan nomor {return_number} tidak ditemukan."
                }),
                status=404,
                content_type='application/json'
            )

        # Ambil semua line di return tersebut
        lines = return_record.line_ids.sudo()

        data = []
        for line in lines:
            data.append({
                "id": line.id,
                "barcode_scanned": line.barcode_scanned,
                "product_name": line.product_id.display_name if line.product_id else None,
                "product_code": line.code_product,
                "warehouse": line.warehouse_id.name if line.warehouse_id else None,
                "condition": dict(line._fields['condition'].selection).get(line.condition),
                "return_reason": dict(line._fields['return_reason'].selection).get(line.return_reason),
                "destination_location": dict(line._fields['destination_location'].selection).get(line.destination_location) if line.destination_location else None,
                "new_status": dict(line._fields['new_status'].selection).get(line.new_status) if line.new_status else None,
                "is_processed": line.is_processed,
                "processed_date": line.processed_date.strftime('%Y-%m-%d %H:%M:%S') if line.processed_date else None,
                "notes": line.notes,
            })

        response_data = {
            "status": "success",
            "return_number": return_record.name,
            "delivery_order": return_record.delivery_id.name if return_record.delivery_id else None,
            "total_items": len(data),
            "items": data
        }

        return Response(
            json.dumps(response_data, ensure_ascii=False, indent=2),
            content_type='application/json',
            status=200
        )
    

    @http.route('/api/return/scan', type='http', auth='public', methods=['GET'], csrf=False)
    def scan_barcode(self, **kwargs):
        """
        Endpoint: GET /api/return/scan?return=RTN/00001&barcode=123456789
        Fungsi: Scan barcode untuk menambahkan item ke return tertentu berdasarkan nomor return.
        """
        return_number = kwargs.get('return')
        barcode = kwargs.get('barcode')

        if not return_number or not barcode:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": "Parameter 'return' dan 'barcode' wajib diisi. Contoh: /api/return/scan?return=RTN/00001&barcode=123456789"
                }),
                status=400,
                content_type='application/json'
            )

        return_record = request.env['inventory.return.product'].sudo().search([
            ('name', '=', return_number)
        ], limit=1)

        if not return_record:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Return dengan nomor {return_number} tidak ditemukan."
                }),
                status=404,
                content_type='application/json'
            )

        if return_record.state not in ['draft', 'in_progress']:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Return {return_number} tidak dalam status aktif. (Status saat ini: {return_record.state})"
                }),
                status=400,
                content_type='application/json'
            )

        product_detail = request.env['inventory.receipt.product.detail'].sudo().search([
            ('barcode', '=', barcode),
            ('status_product', '=', 'sold')
        ], limit=1)

        if not product_detail:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Produk dengan barcode {barcode} tidak ditemukan atau tidak berstatus 'Sold'."
                }),
                status=404,
                content_type='application/json'
            )

        duplicate = request.env['inventory.return.product.line'].sudo().search([
            ('return_id', '=', return_record.id),
            ('barcode_scanned', '=', barcode)
        ], limit=1)

        if duplicate:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Barcode {barcode} sudah ada di return {return_number}."
                }),
                status=400,
                content_type='application/json'
            )

        if return_record.delivery_id and product_detail.delivery_id != return_record.delivery_id:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Barcode {barcode} bukan dari Delivery Order {return_record.delivery_id.name}. Produk ini dari {product_detail.delivery_id.name if product_detail.delivery_id else 'Delivery lain'}."
                }),
                status=400,
                content_type='application/json'
            )

        new_line = request.env['inventory.return.product.line'].sudo().create({
            'return_id': return_record.id,
            'barcode_scanned': barcode,
            'product_detail_id': product_detail.id,
            'condition': 'good',         # Default
            'return_reason': 'other',    # Default
        })

        response_data = {
            "status": "success",
            "message": f"Produk {product_detail.product_id.display_name} berhasil ditambahkan ke return {return_record.name}.",
            "return_number": return_record.name,
            "return_state": return_record.state,
            "data": {
                "id": new_line.id,
                "barcode": new_line.barcode_scanned,
                "product_name": product_detail.product_id.display_name,
                "product_code": product_detail.code_product,
                "warehouse": product_detail.warehouse_id.name,
                "condition": dict(new_line._fields['condition'].selection).get(new_line.condition),
                "return_reason": dict(new_line._fields['return_reason'].selection).get(new_line.return_reason),
                "destination_location": dict(new_line._fields['destination_location'].selection).get(new_line.destination_location),
                "new_status": dict(new_line._fields['new_status'].selection).get(new_line.new_status),
                "is_processed": new_line.is_processed,
            }
        }

        return Response(
            json.dumps(response_data, ensure_ascii=False, indent=2),
            content_type='application/json',
            status=200
        )

