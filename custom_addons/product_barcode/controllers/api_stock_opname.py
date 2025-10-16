from odoo import http
from odoo.http import request, Response
import json
from datetime import datetime


def response_json(status=True, message="", data=None, errors=None, http_status=200):
    """
    Helper untuk response JSON standar:
    - Jika success=True → tampilkan data (tanpa errors)
    - Jika success=False → tampilkan errors (tanpa data)
    """
    body = {
        "success": status,
        "message": message,
    }

    if status and data is not None:
        body["data"] = data
    elif not status and errors is not None:
        body["errors"] = errors

    return Response(
        json.dumps(body, ensure_ascii=False, default=str),
        headers=[('Content-Type', 'application/json')],
        status=http_status
    )


class ApiStockOpname(http.Controller):

    @http.route('/api/opname/expected_products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_expected_products(self, **params):
        """
        API GET untuk mendapatkan list expected products (product yang ada di sistem)
        Query parameter:
        - warehouse_code (required): Kode warehouse (e.g., "WH")
        - status (optional): Filter by status product, default "available"
        - limit (optional): Limit jumlah hasil, default 100
        - offset (optional): Offset untuk pagination, default 0

        Example: /api/opname/expected_products?warehouse_code=WH&status=available&limit=50
        """
        warehouse_code = params.get('warehouse_code')
        if not warehouse_code:
            return response_json(False, "warehouse_code is required",
                                 errors={"field": "warehouse_code", "reason": "This field is required"},
                                 http_status=400)

        warehouse = request.env['stock.warehouse'].sudo().search([('code', '=', warehouse_code)], limit=1)
        if not warehouse:
            return response_json(False, f"Warehouse '{warehouse_code}' not found",
                                 errors={"field": "warehouse_code", "reason": "Not found"},
                                 http_status=404)

        # Build domain
        domain = [('warehouse_id', '=', warehouse.id)]

        # Filter by status (default: available)
        status = params.get('status', 'available')
        if status and status != 'all':
            domain.append(('status_product', '=', status))

        # Pagination
        try:
            limit = int(params.get('limit', 100))
            offset = int(params.get('offset', 0))
        except ValueError:
            return response_json(False, "limit and offset must be numbers",
                                 errors={"field": "limit/offset", "reason": "Must be numeric"},
                                 http_status=400)

        # Get total count
        total_count = request.env['inventory.receipt.product.detail'].sudo().search_count(domain)

        # Get products with pagination
        products = request.env['inventory.receipt.product.detail'].sudo().search(
            domain,
            limit=limit,
            offset=offset,
            order='code_product, barcode'
        )

        items = []
        for p in products:
            item = {
                'id': p.id,
                'barcode': p.barcode,
                'product_code': p.code_product,
                'product_name': p.product_id.name if p.product_id else None,
                'product_id': p.product_id.id if p.product_id else None,
                'warehouse': p.warehouse_id.name if p.warehouse_id else None,
                'warehouse_id': p.warehouse_id.id if p.warehouse_id else None,
                'receipt': p.receipt_id.name if p.receipt_id else None,
                'receipt_id': p.receipt_id.id if p.receipt_id else None,
                'vendor': p.vendor_id.name if p.vendor_id else None,
                'vendor_id': p.vendor_id.id if p.vendor_id else None,
                'vendor_code': p.vendor_code,
                'status': p.status_product,
                'unique_code': p.unique_code,
            }

            # Add opname history if available
            if p.last_opname_date:
                item['last_opname'] = {
                    'date': p.last_opname_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'opname_id': p.last_opname_id.id if p.last_opname_id else None,
                    'opname_number': p.last_opname_id.name if p.last_opname_id else None,
                    'condition': p.last_physical_condition,
                    'notes': p.last_opname_notes,
                    'count': p.opname_count
                }
            else:
                item['last_opname'] = None

            items.append(item)

        result = {
            "warehouse": warehouse.name,
            "warehouse_code": warehouse.code,
            "status_filter": status,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "returned_count": len(items),
            "has_more": (offset + len(items)) < total_count,
            "items": items
        }

        return response_json(True, f"Found {total_count} expected products", data=result)

    @http.route('/api/opname/expected_products/summary', type='http', auth='public', methods=['GET'], csrf=False)
    def get_expected_products_summary(self, **params):
        """
        API GET untuk mendapatkan summary expected products per status
        Query parameter:
        - warehouse_code (required): Kode warehouse

        Example: /api/opname/expected_products/summary?warehouse_code=WH
        """
        warehouse_code = params.get('warehouse_code')
        if not warehouse_code:
            return response_json(False, "warehouse_code is required",
                                 errors={"field": "warehouse_code", "reason": "This field is required"},
                                 http_status=400)

        warehouse = request.env['stock.warehouse'].sudo().search([('code', '=', warehouse_code)], limit=1)
        if not warehouse:
            return response_json(False, f"Warehouse '{warehouse_code}' not found",
                                 errors={"field": "warehouse_code", "reason": "Not found"},
                                 http_status=404)

        base_domain = [('warehouse_id', '=', warehouse.id)]

        # Count by status
        status_counts = {}
        statuses = ['waiting', 'available', 'sold', 'on_borrow']

        for status in statuses:
            domain = base_domain + [('status_product', '=', status)]
            count = request.env['inventory.receipt.product.detail'].sudo().search_count(domain)
            status_counts[status] = count

        # Total count
        total = request.env['inventory.receipt.product.detail'].sudo().search_count(base_domain)

        # Count products that have been checked in opname
        checked_domain = base_domain + [('last_opname_date', '!=', False)]
        checked_count = request.env['inventory.receipt.product.detail'].sudo().search_count(checked_domain)

        # Count products never checked
        never_checked_domain = base_domain + [('last_opname_date', '=', False)]
        never_checked_count = request.env['inventory.receipt.product.detail'].sudo().search_count(never_checked_domain)

        result = {
            "warehouse": warehouse.name,
            "warehouse_code": warehouse.code,
            "total_products": total,
            "by_status": status_counts,
            "opname_status": {
                "checked": checked_count,
                "never_checked": never_checked_count,
                "checked_percentage": round((checked_count / total * 100), 2) if total > 0 else 0
            }
        }

        return response_json(True, "Summary retrieved successfully", data=result)

    @http.route('/api/opname/expected_products/by_opname', type='http', auth='public', methods=['GET'], csrf=False)
    def get_expected_products_by_opname(self, **params):
        """
        API GET untuk mendapatkan expected products berdasarkan opname tertentu
        Query parameter:
        - opname_id (required): ID stock opname

        Example: /api/opname/expected_products/by_opname?opname_id=1
        """
        opname_id = params.get('opname_id')
        if not opname_id:
            return response_json(False, "opname_id is required",
                                 errors={"field": "opname_id", "reason": "This field is required"},
                                 http_status=400)

        try:
            opname_id = int(opname_id)
        except ValueError:
            return response_json(False, "opname_id must be a number",
                                 errors={"field": "opname_id", "reason": "Must be numeric"},
                                 http_status=400)

        opname = request.env['stock.opname'].sudo().browse(opname_id)
        if not opname.exists():
            return response_json(False, f"Stock opname with ID {opname_id} not found",
                                 errors={"field": "opname_id", "reason": "Not found"},
                                 http_status=404)

        # Get expected lines from opname
        expected_lines = []
        for line in opname.expected_line_ids:
            expected_lines.append({
                'id': line.id,
                'barcode': line.barcode,
                'product_code': line.code_product,
                'product_name': line.product_id.name if line.product_id else None,
                'warehouse': line.warehouse_id.name if line.warehouse_id else None,
                'receipt': line.receipt_id.name if line.receipt_id else None,
                'vendor': line.vendor_id.name if line.vendor_id else None,
                'vendor_code': line.vendor_code,
                'system_status': line.system_status,
                'product_condition': line.product_condition,
                'information': line.information,
                'match_remarks': line.match_remarks,
                'last_updated': line.last_updated.strftime('%Y-%m-%d %H:%M:%S') if line.last_updated else None,
                'is_scanned': line.is_scanned,
            })

        # Separate scanned and not scanned
        scanned = [item for item in expected_lines if item['is_scanned']]
        not_scanned = [item for item in expected_lines if not item['is_scanned']]

        result = {
            "opname_number": opname.name,
            "warehouse": opname.warehouse_id.name,
            "opname_date": opname.opname_date.strftime('%Y-%m-%d %H:%M:%S'),
            "status": opname.state,
            "total_expected": len(expected_lines),
            "total_scanned": len(scanned),
            "total_not_scanned": len(not_scanned),
            "scanned_percentage": round((len(scanned) / len(expected_lines) * 100), 2) if expected_lines else 0,
            "items": {
                "all": expected_lines,
                "scanned": scanned,
                "not_scanned": not_scanned
            }
        }

        return response_json(True, "Expected products retrieved successfully", data=result)

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
            return response_json(False, "Invalid JSON format", http_status=400)

        warehouse_code = data.get('warehouse_code')
        if not warehouse_code:
            return response_json(False, "warehouse_code is required",
                                 errors={"field": "warehouse_code", "reason": "This field is required"},
                                 http_status=400)

        warehouse = request.env['stock.warehouse'].sudo().search([('code', '=', warehouse_code)], limit=1)
        if not warehouse:
            return response_json(False, f"Warehouse '{warehouse_code}' not found",
                                 errors={"field": "warehouse_code", "reason": "Not found"},
                                 http_status=404)

        opname = request.env['stock.opname'].sudo().create({
            'warehouse_id': warehouse.id,
            'notes': data.get('notes', ''),
            'state': 'in_progress'
        })

        opname_data = {
            "opname_id": opname.id,
            "opname_number": opname.name,
            "warehouse": warehouse.name,
            "opname_date": opname.opname_date.strftime('%Y-%m-%d %H:%M:%S'),
            "status": opname.state,
            "total_expected": opname.total_expected
        }

        return response_json(True, "Stock opname created successfully", data=opname_data, http_status=201)

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
            return response_json(False, "Invalid JSON format", http_status=400)

        opname_id = data.get('opname_id')
        barcodes = data.get('barcodes', [])

        if not opname_id:
            return response_json(False, "opname_id is required",
                                 errors={"field": "opname_id", "reason": "This field is required"},
                                 http_status=400)
        if not barcodes or not isinstance(barcodes, list):
            return response_json(False, "barcodes must be a non-empty list",
                                 errors={"field": "barcodes", "reason": "Must be a non-empty list"},
                                 http_status=400)

        opname = request.env['stock.opname'].sudo().browse(opname_id)
        if not opname.exists():
            return response_json(False, f"Stock opname with ID {opname_id} not found",
                                 errors={"field": "opname_id", "reason": "Not found"},
                                 http_status=404)
        if opname.state not in ['draft', 'in_progress']:
            return response_json(False, "Stock opname is not in progress",
                                 errors={"field": "state", "reason": "Must be in progress"},
                                 http_status=400)

        created_lines = []
        matched_count = 0
        unmatched_count = 0

        for item in barcodes:
            barcode = item.get('barcode')
            if not barcode:
                continue

            existing = request.env['stock.opname.line'].sudo().search([
                ('opname_id', '=', opname_id),
                ('barcode', '=', barcode)
            ], limit=1)
            if existing:
                continue

            line = request.env['stock.opname.line'].sudo().create({
                'opname_id': opname_id,
                'barcode': barcode,
                'product_condition': item.get('product_condition', 'good'),
                'information': item.get('information', ''),
            })

            if line.match_status == 'matched':
                matched_count += 1
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

        result = {
            "opname_number": opname.name,
            "scanned_count": len(created_lines),
            "matched_count": matched_count,
            "unmatched_count": unmatched_count,
            "items": created_lines
        }

        return response_json(True, f"Successfully scanned {len(created_lines)} barcodes", data=result)

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
            return response_json(False, "Invalid JSON format", http_status=400)

        opname_id = data.get('opname_id')
        if not opname_id:
            return response_json(False, "opname_id is required",
                                 errors={"field": "opname_id", "reason": "This field is required"},
                                 http_status=400)

        opname = request.env['stock.opname'].sudo().browse(opname_id)
        if not opname.exists():
            return response_json(False, f"Stock opname with ID {opname_id} not found",
                                 errors={"field": "opname_id", "reason": "Not found"},
                                 http_status=404)
        if opname.state == 'done':
            return response_json(False, "Stock opname already completed",
                                 errors={"field": "state", "reason": "Already done"},
                                 http_status=400)

        try:
            opname.action_done()
        except Exception as e:
            return response_json(False, f"Failed to submit opname: {str(e)}",
                                 errors={"exception": str(e)},
                                 http_status=500)

        summary = {
            'matched': [],
            'unmatched': []
        }

        for line in opname.line_ids:
            item = {
                'barcode': line.barcode,
                'product_code': line.code_product,
                'product_name': line.product_id.name if line.product_id else None,
                'product_condition': line.product_condition,
                'information': line.information,
                'system_status': line.detail_product_status,
                'remarks': line.match_remarks
            }
            summary[line.match_status if line.match_status in summary else 'unmatched'].append(item)

        result = {
            "opname_number": opname.name,
            "status": opname.state,
            "total_scanned": opname.total_scanned,
            "total_matched": opname.total_matched,
            "total_unmatched": opname.total_unmatched,
            "summary": summary
        }

        return response_json(True, "Stock opname submitted successfully", data=result)

    @http.route('/api/opname/detail', type='http', auth='public', methods=['GET'], csrf=False)
    def get_opname_detail(self, **params):
        """
        API GET untuk melihat detail stock opname
        Query parameter: ?opname_id=1
        """
        opname_id = params.get('opname_id')
        if not opname_id:
            return response_json(False, "opname_id is required",
                                 errors={"field": "opname_id", "reason": "Missing"},
                                 http_status=400)

        try:
            opname_id = int(opname_id)
        except ValueError:
            return response_json(False, "opname_id must be a number",
                                 errors={"field": "opname_id", "reason": "Must be numeric"},
                                 http_status=400)

        opname = request.env['stock.opname'].sudo().browse(opname_id)
        if not opname.exists():
            return response_json(False, f"Stock opname with ID {opname_id} not found",
                                 errors={"field": "opname_id", "reason": "Not found"},
                                 http_status=404)

        lines = [{
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
        } for line in opname.line_ids]

        data = {
            "opname_number": opname.name,
            "warehouse": opname.warehouse_id.name,
            "opname_date": opname.opname_date.strftime('%Y-%m-%d %H:%M:%S'),
            "responsible": opname.responsible_id.name,
            "status": opname.state,
            "notes": opname.notes,
            "total_expected": opname.total_expected,
            "total_scanned": opname.total_scanned,
            "total_matched": opname.total_matched,
            "total_unmatched": opname.total_unmatched,
            "lines": lines
        }

        return response_json(True, "Stock opname detail retrieved successfully", data=data)

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
            warehouse = request.env['stock.warehouse'].sudo().search([('code', '=', warehouse_code)], limit=1)
            if warehouse:
                domain.append(('warehouse_id', '=', warehouse.id))
        if state:
            domain.append(('state', '=', state))

        opnames = request.env['stock.opname'].sudo().search(domain, order='create_date desc')
        data = [{
            'id': opname.id,
            'opname_number': opname.name,
            'warehouse': opname.warehouse_id.name,
            'notes': opname.notes,
            'opname_date': opname.opname_date.strftime('%Y-%m-%d %H:%M:%S'),
            'responsible': opname.responsible_id.name,
            'status': opname.state,
            'total_expected': opname.total_expected,
            'total_scanned': opname.total_scanned,
            'total_matched': opname.total_matched,
            'total_unmatched': opname.total_unmatched
        } for opname in opnames]

        return response_json(True, "Stock opname list retrieved successfully", data={"count": len(data), "items": data})