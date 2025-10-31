from odoo import http, _
from odoo.http import request, Response
import json

class ApiInventoryReturnProduct(http.Controller):

    @http.route('/api/return-products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_return_products(self, **kwargs):
        """
        API GET untuk menampilkan list Product Returns
        seperti tampilan di Odoo (kolom utama)
        Contoh pemanggilan:
        GET /api/return-products
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
        
    @http.route('/api/return/confirm', type='http', auth='public', methods=['POST'], csrf=False)
    def confirm_return(self, **kwargs):
        """
        Endpoint: POST /api/return/confirm
        Body/Param:
            return=RTN/00001
        Fungsi:
            - Menjalankan tombol 'Confirm' di model inventory.return.product
        """
        return_number = kwargs.get('return')

        if not return_number:
            return Response(
                json.dumps({"status": "error", "message": "Parameter 'return' wajib diisi."}),
                status=400, content_type='application/json'
            )

        # Cari record berdasarkan name
        return_record = request.env['inventory.return.product'].sudo().search([('name', '=', return_number)], limit=1)
        if not return_record:
            return Response(
                json.dumps({"status": "error", "message": f"Return {return_number} tidak ditemukan."}),
                status=404, content_type='application/json'
            )

        # Validasi status
        if return_record.state != 'draft':
            return Response(
                json.dumps({"status": "error", "message": f"Return {return_number} tidak bisa dikonfirmasi karena statusnya bukan 'Draft'."}),
                status=400, content_type='application/json'
            )

        try:
            return_record.action_confirm()
            return Response(
                json.dumps({
                    "status": "success",
                    "message": f"Return {return_record.name} berhasil dikonfirmasi.",
                    "state": return_record.state
                }),
                status=200, content_type='application/json'
            )
        except Exception as e:
            return Response(json.dumps({
                "status": "error",
                "message": f"Gagal mengonfirmasi return: {str(e)}"
            }), status=500, content_type='application/json')


    @http.route('/api/return/process', type='http', auth='public', methods=['POST'], csrf=False)
    def process_return(self, **kwargs):
        """
        Endpoint: POST /api/return/process
        Body/Param:
            return=RTN/00001
        Fungsi:
            - Menjalankan tombol 'Process All Returns'
            - Memanggil method action_process_return() untuk membuat stock move dan update status
        """
        return_number = kwargs.get('return')

        if not return_number:
            return Response(
                json.dumps({"status": "error", "message": "Parameter 'return' wajib diisi."}),
                status=400, content_type='application/json'
            )

        # Cari record berdasarkan name
        return_record = request.env['inventory.return.product'].sudo().search([('name', '=', return_number)], limit=1)
        if not return_record:
            return Response(
                json.dumps({"status": "error", "message": f"Return {return_number} tidak ditemukan."}),
                status=404, content_type='application/json'
            )

        # Validasi state
        if return_record.state not in ['confirmed', 'in_progress']:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Return {return_number} tidak dapat diproses. (Status saat ini: {return_record.state})"
                }),
                status=400, content_type='application/json'
            )

        try:
            # Jalankan proses
            return_record.action_process_return()

            return Response(
                json.dumps({
                    "status": "success",
                    "message": f"Return {return_record.name} berhasil diproses.",
                    "state": return_record.state,
                    "total_lines": return_record.total_lines,
                    "returned_count": return_record.returned_count
                }, ensure_ascii=False, indent=2),
                status=200, content_type='application/json'
            )
        except Exception as e:
            return Response(json.dumps({
                "status": "error",
                "message": f"Gagal memproses return: {str(e)}"
            }), status=500, content_type='application/json')