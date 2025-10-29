from odoo import http, _
from odoo.http import request, Response
import json

class ApiInventoryReturnProduct(http.Controller):

    @http.route('/api/return-products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_return_products(self, **kwargs):
        """
        API GET untuk menampilkan list Product Returns
        seperti tampilan di Odoo (kolom utama)
        """
        try:
            # Ambil semua record Return Product (bisa dibatasi atau difilter jika perlu)
            returns = request.env['inventory.return.product'].sudo().search([], order='return_date desc', limit=50)

            result = []
            for rec in returns:
                result.append({
                    "return_number": rec.name,
                    "delivery_order": rec.delivery_id.name if rec.delivery_id else None,
                    "customer": rec.partner_id.name if rec.partner_id else None,
                    "return_date": rec.return_date.strftime('%Y-%m-%d %H:%M:%S') if rec.return_date else None,
                    "return_to_warehouse": rec.warehouse_id.name if rec.warehouse_id else None,
                    "total_items": rec.total_lines,
                    "returned_count": rec.returned_count,
                    "responsible": rec.user_id.name if rec.user_id else None,
                    "status": rec.state.title() if rec.state else None,
                })

            # Kembalikan response JSON
            data = {
                "status": "success",
                "count": len(result),
                "data": result
            }

            return Response(json.dumps(data), content_type='application/json', status=200)

        except Exception as e:
            return Response(json.dumps({
                "status": "error",
                "message": str(e)
            }), content_type='application/json', status=500)