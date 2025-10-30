from odoo import http
from odoo.http import request, Response
import json


class ApiInventoryReturnOptions(http.Controller):

    @http.route('/api/return/options', type='http', auth='public', methods=['GET'], csrf=False)
    def get_return_dropdown_options(self, **kwargs):
        """
        Endpoint: GET /api/return/options
        Mengembalikan semua pilihan dropdown dari model inventory.return.product.line
        agar bisa digunakan di frontend.
        """
        try:
            # Dapatkan model
            line_model = request.env['inventory.return.product.line']

            # Ambil semua selection dari model
            condition_selection = line_model._fields['condition'].selection
            reason_selection = line_model._fields['return_reason'].selection
            destination_selection = line_model._fields['destination_location'].selection
            status_selection = line_model._fields['new_status'].selection

            # Format jadi list of dict
            def to_dict_list(selection):
                return [
                    {"key": key, "label": label}
                    for key, label in selection
                ]

            response_data = {
                "status": "success",
                "data": {
                    "condition": to_dict_list(condition_selection),
                    "return_reason": to_dict_list(reason_selection),
                    "destination_location": to_dict_list(destination_selection),
                    "new_status": to_dict_list(status_selection)
                }
            }

            return Response(
                json.dumps(response_data, ensure_ascii=False, indent=2),
                content_type='application/json',
                status=200
            )

        except Exception as e:
            return Response(
                json.dumps({
                    "status": "error",
                    "message": f"Terjadi kesalahan: {str(e)}"
                }),
                status=500,
                content_type='application/json'
            )
