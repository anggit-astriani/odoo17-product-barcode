from odoo import models, fields, api
from datetime import datetime


class InventoryReceiptProductDetail(models.Model):
    _inherit = 'inventory.receipt.product.detail'

    # Opname History & Status
    last_opname_date = fields.Datetime('Last Opname Date', readonly=True)
    last_opname_id = fields.Many2one('stock.opname', string='Last Opname', readonly=True)
    last_physical_condition = fields.Selection([
        ('good', 'Good'),
        ('damaged', 'Damaged'),
        ('missing_parts', 'Missing Parts'),
        ('defect', 'Defect'),
        ('not_checked', 'Not Checked')
    ], string='Last Physical Condition', default='not_checked', readonly=True)
    last_opname_notes = fields.Text('Last Opname Notes', readonly=True)
    opname_count = fields.Integer('Opname Count', default=0, readonly=True,
                                  help='Number of times this item has been counted')

    # Opname history lines
    opname_history_ids = fields.One2many('inventory.opname.history', 'detail_product_id',
                                         string='Opname History')


class InventoryOpnameHistory(models.Model):
    _name = 'inventory.opname.history'
    _description = 'Inventory Opname History'
    _order = 'opname_date desc'

    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='Product Detail',
                                        required=True, ondelete='cascade')
    opname_id = fields.Many2one('stock.opname', string='Stock Opname', required=True, ondelete='cascade')
    opname_date = fields.Datetime('Opname Date', required=True)

    # Snapshot data
    barcode = fields.Char('Barcode')
    product_id = fields.Many2one('product.product', string='Product')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

    # Physical condition at time of opname
    physical_condition = fields.Selection([
        ('good', 'Good'),
        ('damaged', 'Damaged'),
        ('missing_parts', 'Missing Parts'),
        ('defect', 'Defect'),
        ('missing', 'Missing/Not Found')
    ], string='Physical Condition', required=True)

    notes = fields.Text('Notes')
    scanned_by = fields.Many2one('res.users', string='Scanned By')

    # Status tracking
    was_scanned = fields.Boolean('Was Scanned', default=True)
    match_status = fields.Selection([
        ('matched', 'Matched'),
        ('status_mismatch', 'Status Mismatch'),
        ('unmatched', 'Unmatched'),
        ('missing', 'Missing')
    ], string='Match Status')


class StockOpname(models.Model):
    _name = 'stock.opname'
    _description = 'Stock Opname'
    _rec_name = 'name'
    _order = 'create_date desc'

    name = fields.Char('Opname Number', required=True, copy=False, readonly=True, default='New')
    opname_date = fields.Datetime('Opname Date', default=fields.Datetime.now, required=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)
    responsible_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', required=True)
    notes = fields.Text('Notes')

    # Expected Lines (System Data)
    expected_line_ids = fields.One2many('stock.opname.expected.line', 'opname_id', string='Expected Items (System)')

    # Scanned Lines (Physical Data)
    line_ids = fields.One2many('stock.opname.line', 'opname_id', string='Scanned Items (Physical)')

    # Statistics
    total_scanned = fields.Integer('Total Scanned', compute='_compute_totals', store=True)
    total_matched = fields.Integer('Total Matched', compute='_compute_totals', store=True)
    total_unmatched = fields.Integer('Total Unmatched', compute='_compute_totals', store=True)
    total_status_mismatch = fields.Integer('Status Mismatch', compute='_compute_totals', store=True)
    total_expected = fields.Integer('Total Expected', compute='_compute_expected_total', store=True)

    @api.depends('line_ids', 'line_ids.match_status')
    def _compute_totals(self):
        for rec in self:
            rec.total_scanned = len(rec.line_ids)
            rec.total_matched = len(rec.line_ids.filtered(lambda l: l.match_status == 'matched'))
            rec.total_unmatched = len(rec.line_ids.filtered(lambda l: l.match_status == 'unmatched'))
            rec.total_status_mismatch = len(rec.line_ids.filtered(lambda l: l.match_status == 'status_mismatch'))

    @api.depends('expected_line_ids')
    def _compute_expected_total(self):
        for rec in self:
            rec.total_expected = len(rec.expected_line_ids)

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.opname') or 'New'

        record = super().create(vals)

        # Auto-generate expected lines if warehouse is set
        if record.warehouse_id:
            record._generate_expected_lines()

        return record

    def write(self, vals):
        res = super().write(vals)

        # Regenerate expected lines if warehouse changed
        if 'warehouse_id' in vals and vals['warehouse_id']:
            for rec in self:
                if rec.state == 'draft':
                    rec._generate_expected_lines()

        return res

    def _generate_expected_lines(self):
        """Generate expected lines from system data"""
        self.ensure_one()

        # Clear existing expected lines
        self.expected_line_ids.unlink()

        # Get all available products in warehouse
        expected_products = self.env['inventory.receipt.product.detail'].search([
            ('warehouse_id', '=', self.warehouse_id.id),
            ('status_product', '=', 'available')
        ])

        expected_lines = []
        for detail in expected_products:
            # Use last opname data if available, otherwise use defaults
            if detail.last_opname_date:
                condition = detail.last_physical_condition if detail.last_physical_condition != 'not_checked' else 'N/A'
                information = detail.last_opname_notes or 'N/A'
                remarks = f"Last checked: {detail.last_opname_date.strftime('%Y-%m-%d')} - {detail.last_opname_notes or 'No issues'}"
                last_updated = detail.last_opname_date
            else:
                condition = 'N/A'
                information = 'N/A'
                remarks = 'Never checked before'
                last_updated = detail.write_date or detail.create_date

            expected_lines.append({
                'opname_id': self.id,
                'barcode': detail.barcode,
                'code_product': detail.code_product,
                'product_id': detail.product_id.id,
                'warehouse_id': detail.warehouse_id.id,
                'receipt_id': detail.receipt_id.id if detail.receipt_id else False,
                'vendor_id': detail.vendor_id.id if detail.vendor_id else False,
                'vendor_code': detail.vendor_code,
                'system_status': detail.status_product,
                'product_condition': condition,
                'information': information,
                'match_remarks': remarks,
                'last_updated': last_updated,
                'detail_product_id': detail.id,
            })

        self.env['stock.opname.expected.line'].create(expected_lines)

    def action_start_opname(self):
        """Start opname process"""
        self.write({'state': 'in_progress'})

    def action_done(self):
        """Mark opname as done and update stock quantities"""
        self.write({'state': 'done'})

        # Update stock and product details based on opname result
        self._update_stock_from_opname()

        # Update expected lines with scanned information
        self._update_expected_with_scanned_data()

    def _update_stock_from_opname(self):
        """Update inventory.receipt.product.detail based on opname results"""
        history_records = []

        for line in self.line_ids:
            if line.match_status == 'matched' and line.detail_product_id:
                # Update detail product dengan informasi dari physical count
                line.detail_product_id.write({
                    'last_opname_date': self.opname_date,
                    'last_opname_id': self.id,
                    'last_physical_condition': line.product_condition,
                    'last_opname_notes': line.information or 'Scanned and verified',
                    'opname_count': line.detail_product_id.opname_count + 1,
                })

                # Create history record
                history_records.append({
                    'detail_product_id': line.detail_product_id.id,
                    'opname_id': self.id,
                    'opname_date': self.opname_date,
                    'barcode': line.barcode,
                    'product_id': line.product_id.id,
                    'warehouse_id': line.warehouse_id.id,
                    'physical_condition': line.product_condition,
                    'notes': line.information,
                    'scanned_by': self.responsible_id.id,
                    'was_scanned': True,
                    'match_status': line.match_status,
                })

        # Handle missing items (expected but not scanned)
        for expected_line in self.expected_line_ids.filtered(lambda e: not e.is_scanned):
            if expected_line.detail_product_id:
                # Update as not found
                expected_line.detail_product_id.write({
                    'last_opname_date': self.opname_date,
                    'last_opname_id': self.id,
                    'last_physical_condition': 'not_checked',
                    'last_opname_notes': 'Item not found during physical count',
                    'opname_count': expected_line.detail_product_id.opname_count + 1,
                })

                # Create history record for missing item
                history_records.append({
                    'detail_product_id': expected_line.detail_product_id.id,
                    'opname_id': self.id,
                    'opname_date': self.opname_date,
                    'barcode': expected_line.barcode,
                    'product_id': expected_line.product_id.id,
                    'warehouse_id': expected_line.warehouse_id.id,
                    'physical_condition': 'missing',
                    'notes': 'Item expected but not found during physical count',
                    'scanned_by': self.responsible_id.id,
                    'was_scanned': False,
                    'match_status': 'missing',
                })

        # Bulk create history records
        if history_records:
            self.env['inventory.opname.history'].create(history_records)

    def _update_expected_with_scanned_data(self):
        """Update expected lines dengan actual scanned data untuk next opname reference"""
        for expected_line in self.expected_line_ids:
            if expected_line.is_scanned:
                # Cari scanned line yang match
                scanned_line = self.line_ids.filtered(lambda l: l.barcode == expected_line.barcode)
                if scanned_line:
                    scanned_line = scanned_line[0]  # Take first if multiple

                    # Update expected line dengan scanned data
                    expected_line.write({
                        'product_condition': scanned_line.product_condition,
                        'information': scanned_line.information or 'Scanned OK',
                        'match_remarks': scanned_line.match_remarks,
                        'last_updated': scanned_line.scanned_date,
                    })

    def action_cancel(self):
        """Cancel opname"""
        self.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        """Reset to draft"""
        self.write({'state': 'draft'})

    def action_open_export_wizard(self):
        """Open export wizard"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Export Stock Opname',
            'res_model': 'stock.opname.export.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_opname_id': self.id,
            }
        }


class StockOpnameExpectedLine(models.Model):
    _name = 'stock.opname.expected.line'
    _description = 'Stock Opname Expected Line (System Data)'
    _rec_name = 'barcode'
    _order = 'code_product'

    opname_id = fields.Many2one('stock.opname', string='Stock Opname', required=True, ondelete='cascade')
    barcode = fields.Char('Barcode', required=True)
    code_product = fields.Char('Product Code')
    product_id = fields.Many2one('product.product', string='Product')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    receipt_id = fields.Many2one('stock.picking', string='Receipt')
    vendor_id = fields.Many2one('res.partner', string='Vendor')
    vendor_code = fields.Char('Vendor Code')

    system_status = fields.Selection([
        ('waiting', 'Waiting'),
        ('available', 'Available'),
        ('sold', 'Sold')
    ], string='System Status')

    # Fields that can be updated from last opname
    product_condition = fields.Char('Condition', default='N/A')
    information = fields.Text('Information', default='N/A')
    match_remarks = fields.Text('Remarks', default='Expected from system')
    last_updated = fields.Datetime('Last Updated', readonly=True)

    # Link to system record
    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='Detail Product')

    # Scan status
    is_scanned = fields.Boolean('Scanned', compute='_compute_is_scanned', store=True)

    @api.depends('opname_id.line_ids', 'opname_id.line_ids.barcode', 'barcode')
    def _compute_is_scanned(self):
        for rec in self:
            rec.is_scanned = bool(rec.opname_id.line_ids.filtered(lambda l: l.barcode == rec.barcode))


class StockOpnameLine(models.Model):
    _name = 'stock.opname.line'
    _description = 'Stock Opname Line'
    _rec_name = 'barcode'

    opname_id = fields.Many2one('stock.opname', string='Stock Opname', required=True, ondelete='cascade')
    barcode = fields.Char('Barcode', required=True)
    code_product = fields.Char('Product Code')
    product_id = fields.Many2one('product.product', string='Product')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

    product_condition = fields.Selection([
        ('good', 'Good'),
        ('damaged', 'Damaged'),
        ('missing_parts', 'Missing Parts'),
        ('defect', 'Defect')
    ], string='Product Condition', default='good', required=True)

    information = fields.Text('Information')
    scanned_date = fields.Datetime('Scanned Date', default=fields.Datetime.now)

    match_status = fields.Selection([
        ('matched', 'Matched'),
        ('unmatched', 'Unmatched'),
        ('status_mismatch', 'Status Mismatch')
    ], string='Match Status', readonly=True)

    match_remarks = fields.Text('Match Remarks', readonly=True)

    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='Detail Product', readonly=True)
    detail_product_status = fields.Selection([
        ('waiting', 'Waiting'),
        ('available', 'Available'),
        ('sold', 'Sold')
    ], string='System Status', readonly=True)

    receipt_id = fields.Many2one('stock.picking', string='Receipt', related='detail_product_id.receipt_id', store=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', related='detail_product_id.vendor_id', store=True)

    @api.model
    def create(self, vals):
        """Auto-match barcode with inventory.receipt.product.detail and validate status"""
        if vals.get('barcode'):
            detail = self.env['inventory.receipt.product.detail'].sudo().search([
                ('barcode', '=', vals['barcode'])
            ], limit=1)

            if detail:
                vals['detail_product_id'] = detail.id
                vals['code_product'] = detail.code_product
                vals['product_id'] = detail.product_id.id
                vals['warehouse_id'] = detail.warehouse_id.id
                vals['detail_product_status'] = detail.status_product

                # Validasi status product
                if detail.status_product == 'available':
                    vals['match_status'] = 'matched'
                    vals['match_remarks'] = 'Product found and status is available'
                elif detail.status_product == 'waiting':
                    vals['match_status'] = 'status_mismatch'
                    vals['match_remarks'] = 'Product found but status is WAITING (not yet available in system)'
                elif detail.status_product == 'sold':
                    vals['match_status'] = 'status_mismatch'
                    vals[
                        'match_remarks'] = 'Product found but status is SOLD (already sold, should not be in warehouse)'
                else:
                    vals['match_status'] = 'status_mismatch'
                    vals['match_remarks'] = f'Product found but status is {detail.status_product}'
            else:
                vals['match_status'] = 'unmatched'
                vals['match_remarks'] = 'Barcode not found in system'

        return super().create(vals)