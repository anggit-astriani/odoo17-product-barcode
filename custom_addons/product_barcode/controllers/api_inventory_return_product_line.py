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
