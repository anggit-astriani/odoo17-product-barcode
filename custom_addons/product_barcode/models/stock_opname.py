from odoo import models, fields, api
from datetime import datetime


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

    line_ids = fields.One2many('stock.opname.line', 'opname_id', string='Opname Lines')
    total_scanned = fields.Integer('Total Scanned', compute='_compute_totals', store=True)
    total_matched = fields.Integer('Total Matched', compute='_compute_totals', store=True)
    total_unmatched = fields.Integer('Total Unmatched', compute='_compute_totals', store=True)
    total_status_mismatch = fields.Integer('Status Mismatch', compute='_compute_totals', store=True)

    @api.depends('line_ids', 'line_ids.match_status')
    def _compute_totals(self):
        for rec in self:
            rec.total_scanned = len(rec.line_ids)
            rec.total_matched = len(rec.line_ids.filtered(lambda l: l.match_status == 'matched'))
            rec.total_unmatched = len(rec.line_ids.filtered(lambda l: l.match_status == 'unmatched'))
            rec.total_status_mismatch = len(rec.line_ids.filtered(lambda l: l.match_status == 'status_mismatch'))

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.opname') or 'New'
        return super().create(vals)

    def action_start_opname(self):
        """Start opname process"""
        self.write({'state': 'in_progress'})

    def action_done(self):
        """Mark opname as done and update stock quantities"""
        self.write({'state': 'done'})

        # Update stock quantity based on opname result
        self._update_stock_from_opname()

    def _update_stock_from_opname(self):
        """Update stock quantity in inventory.receipt.product.detail based on opname"""
        for line in self.line_ids:
            if line.match_status == 'matched' and line.detail_product_id:
                # Jika product condition bukan 'good', bisa update field atau log informasi
                # Untuk saat ini, kita hanya track di stock opname line saja
                # Tidak perlu update detail_product_id karena sudah ada record di opname
                pass

    def action_cancel(self):
        """Cancel opname"""
        self.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        """Reset to draft"""
        self.write({'state': 'draft'})


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