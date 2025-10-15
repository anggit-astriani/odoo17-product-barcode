from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import random


class ProductBorrowing(models.Model):
    _name = 'product.borrowing'
    _description = 'Product Borrowing'
    _rec_name = 'name'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Borrowing Number', required=True, copy=False, readonly=True, default='New')

    # Borrower Information
    borrower_name = fields.Char('Borrower Name', required=True, tracking=True)
    borrower_phone = fields.Char('Phone Number', tracking=True)
    borrower_email = fields.Char('Email', tracking=True)
    borrower_id_number = fields.Char('ID Number', required=True, tracking=True,
                                     help='KTP/Passport/Employee ID')
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

    # Barcode for borrowing document
    borrowing_barcode = fields.Char('Borrowing Barcode', readonly=True, copy=False)

    # Responsible
    responsible_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user,
                                     tracking=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)

    # Statistics
    total_items = fields.Integer('Total Items', compute='_compute_totals', store=True)
    total_returned = fields.Integer('Returned Items', compute='_compute_totals', store=True)
    total_pending = fields.Integer('Pending Items', compute='_compute_totals', store=True)
    is_overdue = fields.Boolean('Is Overdue', compute='_compute_is_overdue', store=True)

    @api.depends('borrow_date', 'due_date')
    def _compute_duration(self):
        for rec in self:
            if rec.borrow_date and rec.due_date:
                delta = rec.due_date - rec.borrow_date
                rec.duration_days = delta.days
            else:
                rec.duration_days = 0

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

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('product.borrowing') or 'New'

        record = super().create(vals)

        # Generate borrowing barcode
        if not record.borrowing_barcode:
            record._generate_borrowing_barcode()

        return record

    def _generate_borrowing_barcode(self):
        """Generate unique barcode for borrowing document"""
        self.ensure_one()

        # Format: BRW-[YYYYMMDD]-[RANDOM6]
        date_str = self.borrow_date.strftime('%Y%m%d')
        random_str = str(random.randint(100000, 999999))

        self.borrowing_barcode = f"BRW-{date_str}-{random_str}"

    @api.constrains('due_date', 'borrow_date')
    def _check_dates(self):
        for rec in self:
            if rec.due_date and rec.borrow_date and rec.due_date <= rec.borrow_date:
                raise ValidationError('Due date must be after borrow date!')

    def action_confirm(self):
        """Confirm borrowing"""
        self.write({'state': 'confirmed'})

    def action_borrow(self):
        """Mark as borrowed and update product status"""
        for rec in self:
            if not rec.line_ids:
                raise UserError('Please add at least one product to borrow!')

            # Validate all products are available
            unavailable_products = []
            for line in rec.line_ids:
                if line.detail_product_id and line.detail_product_id.status_product != 'available':
                    unavailable_products.append(
                        f"{line.code_product} (Status: {line.detail_product_id.status_product})"
                    )
            if unavailable_products:
                raise UserError(
                    "Cannot borrow! Following products are not available:\n" + "\n".join(unavailable_products)
                )

            # Update status produk jadi "on_borrow"
            for line in rec.line_ids:
                if line.detail_product_id:
                    line.detail_product_id.sudo().write({'status_product': 'on_borrow'})

            rec.write({'state': 'borrowed'})

    def action_return(self):
        """Process return"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Return Products',
            'res_model': 'product.borrowing.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_borrowing_id': self.id,
            }
        }

    def action_cancel(self):
        """Cancel borrowing"""
        for rec in self:
            # Revert product status back to available (only if still on_borrow)
            for line in rec.line_ids.filtered(lambda l: l.return_status == 'pending'):
                if line.detail_product_id and line.detail_product_id.status_product == 'on_borrow':
                    line.detail_product_id.sudo().write({'status_product': 'available'})

            rec.write({'state': 'cancel'})

    def action_print_borrowing_document(self):
        """Print borrowing document with barcode"""
        return self.env.ref('product_barcode.action_report_product_borrowing').report_action(self)

    @api.model
    def _cron_check_overdue(self):
        """Cron job to check and mark overdue borrowings"""
        now = fields.Datetime.now()
        overdue_borrowings = self.search([
            ('state', '=', 'borrowed'),
            ('due_date', '<', now)
        ])
        overdue_borrowings.write({'state': 'overdue'})


class ProductBorrowingLine(models.Model):
    _name = 'product.borrowing.line'
    _description = 'Product Borrowing Line'
    _rec_name = 'product_id'

    borrowing_id = fields.Many2one('product.borrowing', string='Borrowing', required=True, ondelete='cascade')

    # Product Info
    barcode = fields.Char('Barcode', required=True)
    product_id = fields.Many2one('product.product', string='Product')
    code_product = fields.Char('Product Code')
    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='Detail Product')

    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    receipt_id = fields.Many2one('stock.picking', string='Receipt')
    vendor_id = fields.Many2one('res.partner', string='Vendor')

    # Borrowing Status
    borrow_condition = fields.Selection([
        ('good', 'Good'),
        ('minor_damage', 'Minor Damage'),
        ('damaged', 'Damaged')
    ], string='Condition When Borrowed', default='good', required=True)

    borrow_notes = fields.Text('Borrow Notes')

    # Return Status
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

    # Auto-fill on barcode scan
    @api.onchange('barcode')
    def _onchange_barcode(self):
        if self.barcode:
            # Search in inventory.receipt.product.detail
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


class InventoryReceiptProductDetail(models.Model):
    _inherit = 'inventory.receipt.product.detail'

    # Update selection to include on_borrow if not already there
    status_product = fields.Selection(
        selection_add=[('on_borrow', 'On Borrow')],
        ondelete={'on_borrow': 'set default'}
    )

    # Borrowing history
    borrowing_line_ids = fields.One2many('product.borrowing.line', 'detail_product_id',
                                         string='Borrowing History')
    current_borrowing_id = fields.Many2one('product.borrowing', string='Current Borrowing',
                                           compute='_compute_current_borrowing', store=False)
    is_borrowed = fields.Boolean('Is Borrowed', compute='_compute_is_borrowed', store=False)

    @api.depends('status_product')
    def _compute_is_borrowed(self):
        for rec in self:
            rec.is_borrowed = (rec.status_product == 'on_borrow')

    @api.depends('borrowing_line_ids', 'borrowing_line_ids.return_status', 'borrowing_line_ids.borrowing_id.state',
                 'status_product')
    def _compute_current_borrowing(self):
        for rec in self:
            # Find current active borrowing
            current = rec.borrowing_line_ids.filtered(
                lambda l: l.return_status == 'pending' and l.borrowing_id.state in ('borrowed', 'overdue', 'confirmed')
            ).sorted(lambda l: l.borrowing_id.borrow_date, reverse=True)
            rec.current_borrowing_id = current[0].borrowing_id.id if current else False