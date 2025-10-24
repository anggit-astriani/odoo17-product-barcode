from odoo import http
from odoo.http import request, Response
import json
from datetime import datetime


def response_json(status=True, message="", data=None, errors=None, http_status=200):
    """Helper untuk response JSON standar"""
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


class ApiProductBorrowing(http.Controller):

    @http.route('/api/borrowing/create', type='http', auth='public', methods=['POST'], csrf=False)
    def create_borrowing(self, **kwargs):
        """
        Create new product borrowing
        POST body:
        {
            "borrower_name": "John Doe",
            "borrower_id_number": "3201234567890123",
            "borrower_phone": "08123456789",
            "borrower_email": "john@example.com",
            "borrower_department": "IT Department",
            "borrower_address": "Jl. Example No. 123",
            "warehouse_code": "WH",
            "due_date": "2025-10-20 17:00:00",
            "purpose": "For testing equipment",
            "barcodes": [
                {
                    "barcode": "12345678",
                    "borrow_condition": "good",
                    "borrow_notes": "Item in good condition"
                }
            ]
        }
        """
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return response_json(False, "Invalid JSON format", http_status=400)

        # Validate required fields
        required = ['borrower_name', 'borrower_id_number', 'warehouse_code', 'due_date', 'purpose', 'barcodes']
        for field in required:
            if not data.get(field):
                return response_json(False, f"{field} is required",
                                     errors={"field": field, "reason": "Required"}, http_status=400)

        # Find warehouse
        warehouse = request.env['stock.warehouse'].sudo().search([('code', '=', data['warehouse_code'])], limit=1)
        if not warehouse:
            return response_json(False, f"Warehouse '{data['warehouse_code']}' not found",
                                 errors={"field": "warehouse_code"}, http_status=404)

        # Parse due_date
        try:
            due_date = datetime.strptime(data['due_date'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return response_json(False, "Invalid due_date format. Use: YYYY-MM-DD HH:MM:SS",
                                 errors={"field": "due_date"}, http_status=400)

        # Create borrowing
        borrowing_vals = {
            'borrower_name': data['borrower_name'],
            'borrower_id_number': data['borrower_id_number'],
            'borrower_phone': data.get('borrower_phone', ''),
            'borrower_email': data.get('borrower_email', ''),
            'borrower_department': data.get('borrower_department', ''),
            'borrower_address': data.get('borrower_address', ''),
            'warehouse_id': warehouse.id,
            'due_date': due_date,
            'purpose': data['purpose'],
            'notes': data.get('notes', ''),
        }

        borrowing = request.env['product.borrowing'].sudo().create(borrowing_vals)

        # Add lines
        created_lines = []
        for item in data['barcodes']:
            barcode = item.get('barcode')
            if not barcode:
                continue

            # Find product detail
            detail = request.env['inventory.receipt.product.detail'].sudo().search([
                ('barcode', '=', barcode),
                ('status_product', '=', 'available')
            ], limit=1)

            if not detail:
                continue

            line_vals = {
                'borrowing_id': borrowing.id,
                'barcode': barcode,
                'detail_product_id': detail.id,
                'product_id': detail.product_id.id,
                'code_product': detail.code_product,
                'warehouse_id': detail.warehouse_id.id,
                'receipt_id': detail.receipt_id.id if detail.receipt_id else False,
                'vendor_id': detail.vendor_id.id if detail.vendor_id else False,
                'borrow_condition': item.get('borrow_condition', 'good'),
                'borrow_notes': item.get('borrow_notes', ''),
            }

            line = request.env['product.borrowing.line'].sudo().create(line_vals)
            created_lines.append({
                'barcode': line.barcode,
                'product_name': line.product_id.name,
                'condition': line.borrow_condition,
            })

        result = {
            "borrowing_id": borrowing.id,
            "borrowing_number": borrowing.name,
            "borrowing_barcode": borrowing.borrowing_barcode,
            "borrower": borrowing.borrower_name,
            "due_date": borrowing.due_date.strftime('%Y-%m-%d %H:%M:%S'),
            "total_items": len(created_lines),
            "status": borrowing.state,
            "items": created_lines
        }

        return response_json(True, "Borrowing created successfully", data=result, http_status=201)

    @http.route('/api/borrowing/confirm', type='http', auth='public', methods=['POST'], csrf=False)
    def confirm_borrowing(self, **kwargs):
        """
        Confirm borrowing (change status to borrowed and update product status)
        POST body: {"borrowing_id": 1}
        """
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return response_json(False, "Invalid JSON format", http_status=400)

        borrowing_id = data.get('borrowing_id')
        if not borrowing_id:
            return response_json(False, "borrowing_id is required", http_status=400)

        borrowing = request.env['product.borrowing'].sudo().browse(borrowing_id)
        if not borrowing.exists():
            return response_json(False, f"Borrowing ID {borrowing_id} not found", http_status=404)

        try:
            # Confirm first
            if borrowing.state == 'draft':
                borrowing.action_confirm()

            # Then mark as borrowed (this updates product status)
            if borrowing.state == 'confirmed':
                borrowing.action_borrow()

            result = {
                "borrowing_number": borrowing.name,
                "status": borrowing.state,
                "total_items": borrowing.total_items,
                "message": "Products status updated to 'on_borrow'"
            }
            return response_json(True, "Borrowing confirmed successfully", data=result)
        except Exception as e:
            return response_json(False, f"Failed to confirm: {str(e)}", http_status=500)

    @http.route('/api/borrowing/return', type='http', auth='public', methods=['POST'], csrf=False)
    def return_borrowing(self, **kwargs):
        """
        Return borrowed products with stock restoration

        POST body example:
        {
            "borrowing_id": 1,
            "return_date": "2025-10-18 14:00:00",
            "items": [
                {
                    "barcode": "12345678",
                    "return_condition": "good",
                    "return_notes": "Returned in good condition"
                }
            ],
            "notes": "All items returned on time"
        }
        """
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return response_json(False, "Invalid JSON format", http_status=400)

        borrowing_id = data.get("borrowing_id")
        if not borrowing_id:
            return response_json(False, "borrowing_id is required", http_status=400)

        borrowing = request.env["product.borrowing"].sudo().browse(borrowing_id)
        if not borrowing.exists():
            return response_json(False, f"Borrowing ID {borrowing_id} not found", http_status=404)

        return_date_str = data.get("return_date")
        try:
            return_date = (
                datetime.strptime(return_date_str, "%Y-%m-%d %H:%M:%S")
                if return_date_str else datetime.now()
            )
        except ValueError:
            return_date = datetime.now()

        items = data.get("items", [])
        if not items:
            return response_json(False, "items list is required", http_status=400)

        StockQuant = request.env["stock.quant"].sudo()

        returned_count = 0
        restored_items = []

        for item in items:
            barcode = item.get("barcode")
            if not barcode:
                continue

            line = borrowing.line_ids.filtered(
                lambda l: l.barcode == barcode and l.return_status == "pending"
            )
            if not line:
                continue
            line = line[0]

            return_condition = item.get("return_condition", "good")
            return_notes = item.get("return_notes", data.get("notes", ""))

            line.sudo().write({
                "return_status": "returned",
                "return_date": return_date,
                "return_condition": return_condition,
                "return_notes": return_notes,
            })

            detail = line.detail_product_id.sudo()
            if not detail:
                continue

            product = detail.product_id
            warehouse = detail.warehouse_id
            location = warehouse.lot_stock_id if warehouse else False

            if product and location and return_condition != "lost":
                quant = StockQuant.search([
                    ("product_id", "=", product.id),
                    ("location_id", "=", location.id)
                ], limit=1)

                if quant:
                    quant.write({"quantity": quant.quantity + 1})
                    restored_items.append({
                        "product": product.name,
                        "quantity": quant.quantity,
                        "warehouse": warehouse.name,
                    })
                else:
                    StockQuant.create({
                        "product_id": product.id,
                        "location_id": location.id,
                        "quantity": 1,
                    })
                    restored_items.append({
                        "product": product.name,
                        "quantity": 1,
                        "warehouse": warehouse.name,
                    })

            if return_condition == "lost":
                detail.write({
                    "status_product": "sold",
                    "last_opname_notes": f"Lost during borrowing {borrowing.name}",
                })
            elif return_condition in ("damaged", "minor_damage"):
                detail.write({
                    "status_product": "available",
                    "last_physical_condition": "damaged",
                    "last_opname_notes": f"Returned {return_condition} from {borrowing.name}",
                })
            else:
                detail.write({"status_product": "available"})

            returned_count += 1

        pending = borrowing.line_ids.filtered(lambda l: l.return_status == "pending")
        if not pending:
            borrowing.sudo().write({
                "state": "returned",
                "actual_return_date": return_date
            })

        result = {
            "borrowing_number": borrowing.name,
            "returned_count": returned_count,
            "pending_count": len(pending),
            "status": borrowing.state,
            "restored_stock": restored_items,
        }

        return response_json(True, f"{returned_count} items returned successfully", data=result)

    @http.route('/api/borrowing/detail', type='http', auth='public', methods=['GET'], csrf=False)
    def get_borrowing_detail(self, **params):
        """Get borrowing detail - Query: ?borrowing_id=1"""
        borrowing_id = params.get('borrowing_id')
        if not borrowing_id:
            return response_json(False, "borrowing_id is required", http_status=400)

        try:
            borrowing_id = int(borrowing_id)
        except ValueError:
            return response_json(False, "borrowing_id must be numeric", http_status=400)

        borrowing = request.env['product.borrowing'].sudo().browse(borrowing_id)
        if not borrowing.exists():
            return response_json(False, f"Borrowing ID {borrowing_id} not found", http_status=404)

        lines = [{
            'barcode': line.barcode,
            'product_code': line.code_product,
            'product_name': line.product_id.name if line.product_id else None,
            'warehouse': line.warehouse_id.name if line.warehouse_id else None,
            'borrow_condition': line.borrow_condition,
            'borrow_notes': line.borrow_notes,
            'return_status': line.return_status,
            'return_date': line.return_date.strftime('%Y-%m-%d %H:%M:%S') if line.return_date else None,
            'return_condition': line.return_condition,
            'return_notes': line.return_notes,
        } for line in borrowing.line_ids]

        data = {
            "borrowing_number": borrowing.name,
            "borrowing_barcode": borrowing.borrowing_barcode,
            "borrower_name": borrowing.borrower_name,
            "borrower_id_number": borrowing.borrower_id_number,
            "borrower_phone": borrowing.borrower_phone,
            "borrower_email": borrowing.borrower_email,
            "borrower_department": borrowing.borrower_department,
            "borrower_address": borrowing.borrower_address,
            "warehouse": borrowing.warehouse_id.name,
            "borrow_date": borrowing.borrow_date.strftime('%Y-%m-%d %H:%M:%S'),
            "due_date": borrowing.due_date.strftime('%Y-%m-%d %H:%M:%S'),
            "duration_days": borrowing.duration_days,
            "actual_return_date": borrowing.actual_return_date.strftime(
                '%Y-%m-%d %H:%M:%S') if borrowing.actual_return_date else None,
            "purpose": borrowing.purpose,
            "notes": borrowing.notes,
            "status": borrowing.state,
            "is_overdue": borrowing.is_overdue,
            "total_items": borrowing.total_items,
            "total_returned": borrowing.total_returned,
            "total_pending": borrowing.total_pending,
            "responsible": borrowing.responsible_id.name,
            "items": lines
        }

        return response_json(True, "Borrowing detail retrieved successfully", data=data)

    @http.route('/api/borrowing/list', type='http', auth='public', methods=['GET'], csrf=False)
    def get_borrowing_list(self, **params):
        """
        Get borrowing list - Query: ?warehouse_code=WH&state=borrowed&borrower_name=John
        """
        domain = []

        warehouse_code = params.get('warehouse_code')
        if warehouse_code:
            warehouse = request.env['stock.warehouse'].sudo().search([('code', '=', warehouse_code)], limit=1)
            if warehouse:
                domain.append(('warehouse_id', '=', warehouse.id))

        state = params.get('state')
        if state:
            domain.append(('state', '=', state))

        borrower_name = params.get('borrower_name')
        if borrower_name:
            domain.append(('borrower_name', 'ilike', borrower_name))

        borrowings = request.env['product.borrowing'].sudo().search(domain, order='create_date desc')

        data = [{
            'id': b.id,
            'borrowing_number': b.name,
            'borrowing_barcode': b.borrowing_barcode,
            'borrower_name': b.borrower_name,
            'borrower_phone': b.borrower_phone,
            'warehouse': b.warehouse_id.name,
            'borrow_date': b.borrow_date.strftime('%Y-%m-%d %H:%M:%S'),
            'due_date': b.due_date.strftime('%Y-%m-%d %H:%M:%S'),
            'status': b.state,
            'is_overdue': b.is_overdue,
            'total_items': b.total_items,
            'total_returned': b.total_returned,
            'total_pending': b.total_pending,
        } for b in borrowings]

        return response_json(True, "Borrowing list retrieved successfully",
                             data={"count": len(data), "items": data})