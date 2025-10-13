from odoo import models, fields, api


class StockOpnameComparison(models.Model):
    _name = 'stock.opname.comparison'
    _description = 'Stock Opname Comparison View'
    _rec_name = 'barcode'
    _order = 'comparison_status, code_product'

    opname_id = fields.Many2one('stock.opname', string='Stock Opname', required=True, ondelete='cascade')

    # Common Data (sama antara system dan scanned)
    barcode = fields.Char('Barcode', required=True)
    code_product = fields.Char('Product Code')
    product_id = fields.Many2one('product.product', string='Product')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    receipt_id = fields.Many2one('stock.picking', string='Receipt')
    vendor_id = fields.Many2one('res.partner', string='Vendor')

    # System Data (Expected)
    system_status = fields.Selection([
        ('waiting', 'Waiting'),
        ('available', 'Available'),
        ('sold', 'Sold')
    ], string='System Status')
    system_date = fields.Datetime('System Date')

    # Scanned Data (Physical)
    is_scanned = fields.Boolean('Is Scanned', default=False)
    scanned_condition = fields.Selection([
        ('good', 'Good'),
        ('damaged', 'Damaged'),
        ('missing_parts', 'Missing Parts'),
        ('defect', 'Defect')
    ], string='Physical Condition')
    scanned_information = fields.Text('Physical Information')
    scanned_match_status = fields.Selection([
        ('matched', 'Matched'),
        ('status_mismatch', 'Status Mismatch'),
        ('unmatched', 'Unmatched')
    ], string='Scan Match Status')
    scanned_match_remarks = fields.Text('Scan Remarks')
    scanned_date = fields.Datetime('Scan Date')

    # Comparison Result
    comparison_status = fields.Selection([
        ('perfect_match', 'Perfect Match'),
        ('found_with_issue', 'Found (with issue)'),
        ('missing', 'Missing'),
        ('surplus', 'Surplus/Unknown')
    ], string='Comparison Status', compute='_compute_comparison_status', store=True)

    discrepancy_notes = fields.Text('Discrepancy Notes', compute='_compute_discrepancy_notes', store=True)

    opname_line_id = fields.Many2one('stock.opname.line', string='Opname Line')
    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='System Product Detail')

    @api.depends('is_scanned', 'system_status', 'scanned_match_status', 'scanned_condition')
    def _compute_comparison_status(self):
        for rec in self:
            if not rec.is_scanned:
                # Ada di sistem tapi tidak di-scan
                rec.comparison_status = 'missing'
            elif not rec.system_status:
                # Di-scan tapi tidak ada di sistem
                rec.comparison_status = 'surplus'
            elif rec.scanned_match_status == 'matched' and rec.scanned_condition == 'good':
                # Perfect: di-scan, matched, dan kondisi baik
                rec.comparison_status = 'perfect_match'
            else:
                # Di-scan tapi ada issue (status mismatch atau kondisi tidak baik)
                rec.comparison_status = 'found_with_issue'

    @api.depends('comparison_status', 'scanned_match_remarks', 'scanned_condition', 'scanned_information')
    def _compute_discrepancy_notes(self):
        for rec in self:
            notes = []

            if rec.comparison_status == 'missing':
                notes.append('❌ Item not found during physical count')
                if rec.system_status == 'sold':
                    notes.append('⚠️ System shows as SOLD but still in expected list')

            elif rec.comparison_status == 'surplus':
                notes.append('⚠️ Item found but not registered in system')
                notes.append(f'Scan remarks: {rec.scanned_match_remarks or "N/A"}')

            elif rec.comparison_status == 'found_with_issue':
                if rec.scanned_match_status == 'status_mismatch':
                    notes.append(f'⚠️ Status issue: {rec.scanned_match_remarks or "Status mismatch detected"}')
                if rec.scanned_condition != 'good':
                    notes.append(f'⚠️ Physical condition: {rec.scanned_condition.upper()}')
                if rec.scanned_information:
                    notes.append(f'📝 Info: {rec.scanned_information}')

            elif rec.comparison_status == 'perfect_match':
                notes.append('✅ Item verified successfully')

            rec.discrepancy_notes = '\n'.join(notes) if notes else 'No issues'


class StockOpname(models.Model):
    _inherit = 'stock.opname'

    comparison_ids = fields.One2many('stock.opname.comparison', 'opname_id', string='Comparison Lines')

    # Statistics
    comparison_perfect_match = fields.Integer('Perfect Match', compute='_compute_comparison_stats', store=True)
    comparison_found_with_issue = fields.Integer('Found (with issue)', compute='_compute_comparison_stats', store=True)
    comparison_missing = fields.Integer('Missing', compute='_compute_comparison_stats', store=True)
    comparison_surplus = fields.Integer('Surplus', compute='_compute_comparison_stats', store=True)

    @api.depends('comparison_ids', 'comparison_ids.comparison_status')
    def _compute_comparison_stats(self):
        for rec in self:
            rec.comparison_perfect_match = len(
                rec.comparison_ids.filtered(lambda c: c.comparison_status == 'perfect_match'))
            rec.comparison_found_with_issue = len(
                rec.comparison_ids.filtered(lambda c: c.comparison_status == 'found_with_issue'))
            rec.comparison_missing = len(rec.comparison_ids.filtered(lambda c: c.comparison_status == 'missing'))
            rec.comparison_surplus = len(rec.comparison_ids.filtered(lambda c: c.comparison_status == 'surplus'))

    def action_generate_comparison(self):
        """Generate comparison data between system and scanned items"""
        self.ensure_one()

        # Clear existing comparison
        self.comparison_ids.unlink()

        comparison_data = []
        processed_barcodes = set()

        # 1. Get all expected products from system (inventory.receipt.product.detail)
        expected_products = self.env['inventory.receipt.product.detail'].search([
            ('warehouse_id', '=', self.warehouse_id.id),
            ('status_product', '=', 'available')
        ])

        # Process expected products
        for detail in expected_products:
            barcode = detail.barcode
            processed_barcodes.add(barcode)

            # Check if this product was scanned
            scanned_line = self.line_ids.filtered(lambda l: l.barcode == barcode)

            comparison_vals = {
                'opname_id': self.id,
                'barcode': barcode,
                'code_product': detail.code_product,
                'product_id': detail.product_id.id,
                'warehouse_id': detail.warehouse_id.id,
                'receipt_id': detail.receipt_id.id if detail.receipt_id else False,
                'vendor_id': detail.vendor_id.id if detail.vendor_id else False,
                'system_status': detail.status_product,
                'system_date': detail.create_date,
                'detail_product_id': detail.id,
            }

            if scanned_line:
                # Product was scanned
                comparison_vals.update({
                    'is_scanned': True,
                    'scanned_condition': scanned_line.product_condition,
                    'scanned_information': scanned_line.information,
                    'scanned_match_status': scanned_line.match_status,
                    'scanned_match_remarks': scanned_line.match_remarks,
                    'scanned_date': scanned_line.scanned_date,
                    'opname_line_id': scanned_line.id,
                })
            else:
                # Product not scanned (missing)
                comparison_vals.update({
                    'is_scanned': False,
                })

            comparison_data.append(comparison_vals)

        # 2. Add scanned items that are not in system (surplus/unmatched)
        for line in self.line_ids:
            if line.barcode not in processed_barcodes:
                comparison_vals = {
                    'opname_id': self.id,
                    'barcode': line.barcode,
                    'code_product': line.code_product,
                    'product_id': line.product_id.id if line.product_id else False,
                    'warehouse_id': line.warehouse_id.id if line.warehouse_id else False,
                    'receipt_id': line.receipt_id.id if line.receipt_id else False,
                    'vendor_id': line.vendor_id.id if line.vendor_id else False,
                    'system_status': False,
                    'system_date': False,
                    'is_scanned': True,
                    'scanned_condition': line.product_condition,
                    'scanned_information': line.information,
                    'scanned_match_status': line.match_status,
                    'scanned_match_remarks': line.match_remarks,
                    'scanned_date': line.scanned_date,
                    'opname_line_id': line.id,
                    'detail_product_id': line.detail_product_id.id if line.detail_product_id else False,
                }
                comparison_data.append(comparison_vals)

        # Create comparison records
        self.env['stock.opname.comparison'].create(comparison_data)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Comparison Generated',
                'message': f'''
                    Total Items: {len(comparison_data)}
                    Perfect Match: {self.comparison_perfect_match}
                    Found (with issue): {self.comparison_found_with_issue}
                    Missing: {self.comparison_missing}
                    Surplus: {self.comparison_surplus}
                ''',
                'type': 'success',
                'sticky': False,
            }
        }