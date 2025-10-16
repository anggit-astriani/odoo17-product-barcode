import logging
import random
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class ProductBorrowing(models.Model):
    _name = 'product.borrowing'
    _description = 'Product Borrowing'
    _rec_name = 'name'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Borrowing Number', required=True, copy=False, readonly=True, default='New')

    # Borrower Info
    borrower_name = fields.Char('Borrower Name', required=True, tracking=True)
    borrower_phone = fields.Char('Phone Number', tracking=True)
    borrower_email = fields.Char('Email', tracking=True)
    borrower_id_number = fields.Char('ID Number', required=True, tracking=True, help='KTP/Passport/Employee ID')
    borrower_department = fields.Char('Department/Company')
    borrower_address = fields.Text('Address')

    # Borrowing Details
    borrow_date = fields.Datetime('Borrow Date', default=fields.Datetime.now, required=True, tracking=True)
    due_date = fields.Datetime('Due Date', required=True, tracking=True)
    actual_return_date = fields.Datetime('Actual Return Date', readonly=True, tracking=True)
    duration_days = fields.Integer('Duration (Days)', compute='_compute_duration', store=True)

    purpose = fields.Text('Purpose/Reason', required=True, tracking=True)
    notes = fields.Text('Notes')

    # Product Lines
    line_ids = fields.One2many('product.borrowing.line', 'borrowing_id', string='Borrowed Products')

    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('borrowed', 'On Loan'),
        ('returned', 'Returned'),
        ('overdue', 'Overdue'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', required=True, tracking=True)

    borrowing_barcode = fields.Char('Borrowing Barcode', readonly=True, copy=False)
    responsible_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user, tracking=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)

    total_items = fields.Integer('Total Items', compute='_compute_totals', store=True)
    total_returned = fields.Integer('Returned Items', compute='_compute_totals', store=True)
    total_pending = fields.Integer('Pending Items', compute='_compute_totals', store=True)
    is_overdue = fields.Boolean('Is Overdue', compute='_compute_is_overdue', store=True)

    # ===== COMPUTE FIELDS =====
    @api.depends('borrow_date', 'due_date')
    def _compute_duration(self):
        for rec in self:
            rec.duration_days = (rec.due_date - rec.borrow_date).days if rec.borrow_date and rec.due_date else 0

    @api.depends('line_ids', 'line_ids.return_status')
    def _compute_totals(self):
        for rec in self:
            rec.total_items = len(rec.line_ids)
            rec.total_returned = len(rec.line_ids.filtered(lambda l: l.return_status == 'returned'))
            rec.total_pending = len(rec.line_ids.filtered(lambda l: l.return_status in ('pending', 'partial')))

    @api.depends('state', 'due_date')
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for rec in self:
            rec.is_overdue = (rec.state == 'borrowed' and rec.due_date and rec.due_date < now)

    # ===== CREATE =====
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('product.borrowing') or 'New'
        record = super().create(vals)
        if not record.borrowing_barcode:
            record._generate_borrowing_barcode()
        return record

    def _generate_borrowing_barcode(self):
        self.ensure_one()
        date_str = (self.borrow_date or fields.Datetime.now()).strftime('%Y%m%d')
        random_str = str(random.randint(100000, 999999))
        self.borrowing_barcode = f"BRW-{date_str}-{random_str}"

    @api.constrains('due_date', 'borrow_date')
    def _check_dates(self):
        for rec in self:
            if rec.due_date and rec.borrow_date and rec.due_date <= rec.borrow_date:
                raise ValidationError('Due date must be after borrow date!')

    # ===== ACTIONS =====
    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_borrow(self):
        """Mark as borrowed, update product status, and reduce stock"""
        StockQuant = self.env['stock.quant']

        for rec in self:
            if not rec.line_ids:
                raise UserError('Please add at least one product to borrow!')

            # 1️⃣ Check all products availability
            unavailable_products = []
            for line in rec.line_ids:
                if not line.detail_product_id:
                    unavailable_products.append(f"{line.code_product} (No linked product detail)")
                elif line.detail_product_id.sudo().status_product != 'available':
                    unavailable_products.append(
                        f"{line.code_product} (Current: {line.detail_product_id.sudo().status_product})"
                    )

            if unavailable_products:
                raise UserError(
                    "Cannot borrow! The following products are not available:\n" + "\n".join(unavailable_products)
                )

            # 2️⃣ Update status_product & reduce stock
            for line in rec.line_ids:
                detail = line.detail_product_id.sudo()
                product = detail.product_id
                warehouse = detail.warehouse_id or rec.warehouse_id
                location = warehouse.lot_stock_id if warehouse else False

                # Update status
                detail.write({'status_product': 'on_borrow'})
                _logger.info(f"Product {product.display_name} marked as on_borrow.")

                # Reduce stock
                if product and location:
                    quant = StockQuant.search([
                        ('product_id', '=', product.id),
                        ('location_id', '=', location.id)
                    ], limit=1)
                    if quant:
                        if quant.quantity <= 0:
                            raise UserError(f"Cannot borrow {product.display_name}, stock is 0.")
                        new_qty = quant.quantity - 1
                        quant.sudo().write({'quantity': new_qty})
                        _logger.info(f"Stock reduced: {product.display_name} -> {new_qty} units left in {warehouse.name}")
                    else:
                        _logger.warning(f"No stock quant found for {product.display_name} in {warehouse.name}")

            # 3️⃣ Set state borrowed
            rec.write({'state': 'borrowed'})
            rec.message_post(
                body=f"{len(rec.line_ids)} items borrowed and stock updated.",
                message_type='notification'
            )

    def action_return(self):
        """Open return wizard (modal) and auto-fill pending items."""
        self.ensure_one()

        # pastikan masih ada yang belum dikembalikan
        if not self.line_ids.filtered(lambda l: l.return_status in ('pending', 'partial')):
            raise UserError('All products have been returned!')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Return Borrowed Products',
            'res_model': 'product.borrowing.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_borrowing_id': self.id,  # penting agar default_get bekerja
            }
        }

    def action_cancel(self):
        for rec in self:
            for line in rec.line_ids.filtered(lambda l: l.return_status == 'pending'):
                if line.detail_product_id and line.detail_product_id.sudo().status_product == 'on_borrow':
                    line.detail_product_id.sudo().write({'status_product': 'available'})
            rec.write({'state': 'cancel'})

    def action_print_borrowing_document(self):
        return self.env.ref('product_barcode.action_report_product_borrowing').report_action(self)

    @api.model
    def _cron_check_overdue(self):
        now = fields.Datetime.now()
        overdue_borrowings = self.search([('state', '=', 'borrowed'), ('due_date', '<', now)])
        overdue_borrowings.write({'state': 'overdue'})


class ProductBorrowingLine(models.Model):
    _name = 'product.borrowing.line'
    _description = 'Product Borrowing Line'
    _rec_name = 'product_id'

    borrowing_id = fields.Many2one('product.borrowing', string='Borrowing', required=True, ondelete='cascade')

    barcode = fields.Char('Barcode', required=True)
    product_id = fields.Many2one('product.product', string='Product')
    code_product = fields.Char('Product Code')
    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='Detail Product')

    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    receipt_id = fields.Many2one('stock.picking', string='Receipt')
    vendor_id = fields.Many2one('res.partner', string='Vendor')

    borrow_condition = fields.Selection([
        ('good', 'Good'),
        ('minor_damage', 'Minor Damage'),
        ('damaged', 'Damaged')
    ], string='Condition When Borrowed', default='good', required=True)
    borrow_notes = fields.Text('Borrow Notes')

    return_status = fields.Selection([
        ('pending', 'Pending Return'),
        ('partial', 'Partial Return'),
        ('returned', 'Returned'),
        ('lost', 'Lost'),
        ('damaged_return', 'Returned Damaged')
    ], string='Return Status', default='pending', required=True)

    return_date = fields.Datetime('Return Date', readonly=True)
    return_condition = fields.Selection([
        ('good', 'Good'),
        ('minor_damage', 'Minor Damage'),
        ('damaged', 'Damaged'),
        ('lost', 'Lost')
    ], string='Condition When Returned')
    return_notes = fields.Text('Return Notes')

    @api.onchange('barcode')
    def _onchange_barcode(self):
        if self.barcode:
            detail = self.env['inventory.receipt.product.detail'].search([
                ('barcode', '=', self.barcode),
                ('status_product', '=', 'available')
            ], limit=1)
            if detail:
                self.detail_product_id = detail.id
                self.product_id = detail.product_id.id
                self.code_product = detail.code_product
                self.warehouse_id = detail.warehouse_id.id
                self.receipt_id = detail.receipt_id.id if detail.receipt_id else False
                self.vendor_id = detail.vendor_id.id if detail.vendor_id else False
            else:
                return {
                    'warning': {
                        'title': 'Product Not Found',
                        'message': f'Barcode {self.barcode} not found or not available for borrowing.'
                    }
                }

    @api.model
    def create(self, vals):
        if not vals.get('detail_product_id') and vals.get('barcode'):
            detail = self.env['inventory.receipt.product.detail'].search([('barcode', '=', vals['barcode'])], limit=1)
            if detail:
                vals['detail_product_id'] = detail.id
                vals.setdefault('product_id', detail.product_id.id)
                vals.setdefault('code_product', detail.code_product)
                vals.setdefault('warehouse_id', detail.warehouse_id.id)
                if detail.receipt_id:
                    vals.setdefault('receipt_id', detail.receipt_id.id)
                vals.setdefault('vendor_id', detail.vendor_id.id if detail.vendor_id else False)
        return super().create(vals)
