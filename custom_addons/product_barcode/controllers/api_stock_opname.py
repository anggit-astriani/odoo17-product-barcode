from odoo import http
from odoo.http import request, Response
import json
from datetime import datetime


class ApiStockOpname(http.Controller):

    @http.route('/api/opname/create', type='http', auth='public', methods=['POST'], csrf=False)
    def create_opname(self, **kwargs):
        """
        API POST untuk membuat Stock Opname baru
        Request JSON body:
        {
            "warehouse_code": "WH",
            "notes": "Monthly stock opname"
        }
        """
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return Response(
                json.dumps({"success": False, "message": "Invalid JSON format"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        warehouse_code = data.get('warehouse_code')

        if not warehouse_code:
            return Response(
                json.dumps({"success": False, "message": "warehouse_code is required"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # Cari warehouse
        warehouse = request.env['stock.warehouse'].sudo().search([
            ('code', '=', warehouse_code)
        ], limit=1)

        if not warehouse:
            return Response(
                json.dumps({"success": False, "message": f"Warehouse '{warehouse_code}' not found"}),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        # Buat stock opname
        opname = request.env['stock.opname'].sudo().create({
            'warehouse_id': warehouse.id,
            'notes': data.get('notes', ''),
            'state': 'in_progress'
        })

        response_data = {
            "success": True,
            "message": "Stock opname created successfully",
            "data": {
                "opname_id": opname.id,
                "opname_number": opname.name,
                "warehouse": warehouse.name,
                "opname_date": opname.opname_date.strftime('%Y-%m-%d %H:%M:%S'),
                "status": opname.state
            }
        }

        return Response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')],
            status=201
        )

    @http.route('/api/opname/scan', type='http', auth='public', methods=['POST'], csrf=False)
    def scan_barcode_opname(self, **kwargs):
        """
        API POST untuk scan barcode dan tambahkan ke opname line
        Request JSON body:
        {
            "opname_id": 1,
            "barcodes": [
                {
                    "barcode": "12345678",
                    "product_condition": "good",
                    "information": "Box slightly damaged"
                },
                {
                    "barcode": "87654321",
                    "product_condition": "damaged",
                    "information": "Screen broken"
                }
            ]
        }
        """
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return Response(
                json.dumps({"success": False, "message": "Invalid JSON format"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        opname_id = data.get('opname_id')
        barcodes = data.get('barcodes', [])

        if not opname_id:
            return Response(
                json.dumps({"success": False, "message": "opname_id is required"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        if not barcodes or not isinstance(barcodes, list):
            return Response(
                json.dumps({"success": False, "message": "barcodes must be a non-empty list"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # Cari opname
        opname = request.env['stock.opname'].sudo().browse(opname_id)
        if not opname.exists():
            return Response(
                json.dumps({"success": False, "message": f"Stock opname with ID {opname_id} not found"}),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        if opname.state not in ['draft', 'in_progress']:
            return Response(
                json.dumps({"success": False, "message": "Stock opname is not in progress"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # Proses setiap barcode
        created_lines = []
        matched_count = 0
        unmatched_count = 0
        status_mismatch_count = 0

        for item in barcodes:
            barcode = item.get('barcode')
            if not barcode:
                continue

            # Cek apakah barcode sudah di-scan sebelumnya di opname yang sama
            existing = request.env['stock.opname.line'].sudo().search([
                ('opname_id', '=', opname_id),
                ('barcode', '=', barcode)
            ], limit=1)

            if existing:
                continue  # Skip jika sudah ada

            # Buat opname line
            line_vals = {
                'opname_id': opname_id,
                'barcode': barcode,
                'product_condition': item.get('product_condition', 'good'),
                'information': item.get('information', ''),
            }

            line = request.env['stock.opname.line'].sudo().create(line_vals)

            if line.match_status == 'matched':
                matched_count += 1
            elif line.match_status == 'status_mismatch':
                status_mismatch_count += 1
            else:
                unmatched_count += 1

            created_lines.append({
                'barcode': line.barcode,
                'product_code': line.code_product,
                'product_name': line.product_id.name if line.product_id else None,
                'warehouse': line.warehouse_id.name if line.warehouse_id else None,
                'product_condition': line.product_condition,
                'match_status': line.match_status,
                'match_remarks': line.match_remarks,
                'system_status': line.detail_product_status,
                'receipt': line.receipt_id.name if line.receipt_id else None,
                'vendor': line.vendor_id.name if line.vendor_id else None
            })

        response_data = {
            "success": True,
            "message": f"Successfully scanned {len(created_lines)} barcodes",
            "data": {
                "opname_number": opname.name,
                "scanned_count": len(created_lines),
                "matched_count": matched_count,
                "status_mismatch_count": status_mismatch_count,
                "unmatched_count": unmatched_count,
                "items": created_lines
            }
        }

        return Response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')],
            status=200
        )

    @http.route('/api/opname/submit', type='http', auth='public', methods=['POST'], csrf=False)
    def submit_opname(self, **kwargs):
        """
        API POST untuk submit/finalize stock opname
        Request JSON body:
        {
            "opname_id": 1
        }
        """
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return Response(
                json.dumps({"success": False, "message": "Invalid JSON format"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        opname_id = data.get('opname_id')

        if not opname_id:
            return Response(
                json.dumps({"success": False, "message": "opname_id is required"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # Cari opname
        opname = request.env['stock.opname'].sudo().browse(opname_id)
        if not opname.exists():
            return Response(
                json.dumps({"success": False, "message": f"Stock opname with ID {opname_id} not found"}),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        if opname.state == 'done':
            return Response(
                json.dumps({"success": False, "message": "Stock opname already completed"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        # Set state ke done (akan trigger _update_stock_from_opname)
        try:
            opname.action_done()
        except Exception as e:
            return Response(
                json.dumps({
                    "success": False,
                    "message": f"Failed to submit opname: {str(e)}"
                }),
                headers=[('Content-Type', 'application/json')],
                status=500
            )

        # Hitung summary hasil opname
        summary = {
            'matched': [],
            'status_mismatch': [],
            'unmatched': []
        }

        for line in opname.line_ids:
            item_data = {
                'barcode': line.barcode,
                'product_code': line.code_product,
                'product_name': line.product_id.name if line.product_id else None,
                'product_condition': line.product_condition,
                'information': line.information,
                'system_status': line.detail_product_status,
                'remarks': line.match_remarks
            }

            if line.match_status == 'matched':
                summary['matched'].append(item_data)
            elif line.match_status == 'status_mismatch':
                summary['status_mismatch'].append(item_data)
            else:
                summary['unmatched'].append(item_data)

        response_data = {
            "success": True,
            "message": "Stock opname submitted successfully",
            "data": {
                "opname_number": opname.name,
                "status": opname.state,
                "total_scanned": opname.total_scanned,
                "total_matched": opname.total_matched,
                "total_status_mismatch": opname.total_status_mismatch,
                "total_unmatched": opname.total_unmatched,
                "summary": summary
            }
        }

        return Response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')],
            status=200
        )

    @http.route('/api/opname/detail', type='http', auth='public', methods=['GET'], csrf=False)
    def get_opname_detail(self, **params):
        """
        API GET untuk melihat detail stock opname
        Query parameter: ?opname_id=1
        """
        opname_id = params.get('opname_id')

        if not opname_id:
            return Response(
                json.dumps({"success": False, "message": "opname_id is required"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        try:
            opname_id = int(opname_id)
        except ValueError:
            return Response(
                json.dumps({"success": False, "message": "opname_id must be a number"}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        opname = request.env['stock.opname'].sudo().browse(opname_id)
        if not opname.exists():
            return Response(
                json.dumps({"success": False, "message": f"Stock opname with ID {opname_id} not found"}),
                headers=[('Content-Type', 'application/json')],
                status=404
            )

        lines_data = []
        for line in opname.line_ids:
            lines_data.append({
                'barcode': line.barcode,
                'product_code': line.code_product,
                'product_name': line.product_id.name if line.product_id else None,
                'warehouse': line.warehouse_id.name if line.warehouse_id else None,
                'product_condition': line.product_condition,
                'information': line.information,
                'match_status': line.match_status,
                'match_remarks': line.match_remarks,
                'system_status': line.detail_product_status,
                'receipt': line.receipt_id.name if line.receipt_id else None,
                'vendor': line.vendor_id.name if line.vendor_id else None,
                'scanned_date': line.scanned_date.strftime('%Y-%m-%d %H:%M:%S') if line.scanned_date else None
            })

        response_data = {
            "success": True,
            "data": {
                "opname_number": opname.name,
                "warehouse": opname.warehouse_id.name,
                "opname_date": opname.opname_date.strftime('%Y-%m-%d %H:%M:%S'),
                "responsible": opname.responsible_id.name,
                "status": opname.state,
                "notes": opname.notes,
                "total_scanned": opname.total_scanned,
                "total_matched": opname.total_matched,
                "total_status_mismatch": opname.total_status_mismatch,
                "total_unmatched": opname.total_unmatched,
                "lines": lines_data
            }
        }

        return Response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')],
            status=200
        )

    @http.route('/api/opname/list', type='http', auth='public', methods=['GET'], csrf=False)
    def get_opname_list(self, **params):
        """
        API GET untuk melihat list stock opname
        Query parameter: ?warehouse_code=WH&state=in_progress
        """
        warehouse_code = params.get('warehouse_code')
        state = params.get('state')

        domain = []
        if warehouse_code:
            warehouse = request.env['stock.warehouse'].sudo().search([
                ('code', '=', warehouse_code)
            ], limit=1)
            if warehouse:
                domain.append(('warehouse_id', '=', warehouse.id))

        if state:
            domain.append(('state', '=', state))

        opnames = request.env['stock.opname'].sudo().search(domain, order='create_date desc')

        result = []
        for opname in opnames:
            result.append({
                'id': opname.id,
                'opname_number': opname.name,
                'warehouse': opname.warehouse_id.name,
                'opname_date': opname.opname_date.strftime('%Y-%m-%d %H:%M:%S'),
                'responsible': opname.responsible_id.name,
                'status': opname.state,
                'total_scanned': opname.total_scanned,
                'total_matched': opname.total_matched,
                'total_status_mismatch': opname.total_status_mismatch,
                'total_unmatched': opname.total_unmatched
            })

        return Response(
            json.dumps({'count': len(result), 'data': result}),
            headers=[('Content-Type', 'application/json')],
            status=200
        )