import logging
import random
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class ProductBorrowing(models.Model):
    """
    Model untuk Product Borrowing (Peminjaman Produk)
    
    Tujuan: Mengelola peminjaman produk kepada user/karyawan/pihak eksternal
    Fitur: Tracking peminjam, due date, kondisi produk, return management
    """
    _name = 'product.borrowing'
    _description = 'Product Borrowing'
    _rec_name = 'name'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char('Borrowing Number', required=True, copy=False, readonly=True, default='New')

    borrower_name = fields.Char('Borrower Name', required=True, tracking=True)
    borrower_phone = fields.Char('Phone Number', tracking=True)
    borrower_email = fields.Char('Email', tracking=True)
    borrower_id_number = fields.Char('ID Number', required=True, tracking=True, help='KTP/Passport/Employee ID')
    borrower_department = fields.Char('Department/Company')
    borrower_address = fields.Text('Address')

    borrow_date = fields.Datetime('Borrow Date', default=fields.Datetime.now, required=True, tracking=True)
    due_date = fields.Datetime('Due Date', required=True, tracking=True)
    actual_return_date = fields.Datetime('Actual Return Date', readonly=True, tracking=True)
    duration_days = fields.Integer('Duration (Days)', compute='_compute_duration', store=True)
    purpose = fields.Text('Purpose/Reason', required=True, tracking=True)
    notes = fields.Text('Notes')

    # Relasi ke detail produk yang dipinjam
    line_ids = fields.One2many('product.borrowing.line', 'borrowing_id', string='Borrowed Products')

    state = fields.Selection([
        ('draft', 'Draft'),              # Draft - belum dikonfirmasi
        ('confirmed', 'Confirmed'),      # Confirmed - sudah dikonfirmasi tapi belum diambil
        ('borrowed', 'On Loan'),         # Borrowed - sedang dipinjam
        ('returned', 'Returned'),        # Returned - sudah dikembalikan semua
        ('overdue', 'Overdue'),          # Overdue - melewati due date
        ('cancel', 'Cancelled')          # Cancel - dibatalkan
    ], string='Status', default='draft', required=True, tracking=True)

    borrowing_barcode = fields.Char('Borrowing Barcode', readonly=True, copy=False)
    responsible_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user, tracking=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)

    total_items = fields.Integer('Total Items', compute='_compute_totals', store=True)
    total_returned = fields.Integer('Returned Items', compute='_compute_totals', store=True)
    total_pending = fields.Integer('Pending Items', compute='_compute_totals', store=True)
    is_overdue = fields.Boolean('Is Overdue', compute='_compute_is_overdue', store=True)
    
    @api.depends('borrow_date', 'due_date')
    def _compute_duration(self):
        """
        Compute durasi peminjaman dalam hari
        Trigger: Ketika borrow_date atau due_date berubah
        """
        for rec in self:
            # Hitung selisih hari antara due_date dan borrow_date
            rec.duration_days = (rec.due_date - rec.borrow_date).days if rec.borrow_date and rec.due_date else 0

    @api.depends('line_ids', 'line_ids.return_status')
    def _compute_totals(self):
        """
        Compute total statistik items
        Trigger: Ketika line_ids berubah atau return_status dari line berubah
        """
        for rec in self:
            rec.total_items = len(rec.line_ids)
            rec.total_returned = len(rec.line_ids.filtered(lambda l: l.return_status == 'returned'))
            rec.total_pending = len(rec.line_ids.filtered(lambda l: l.return_status in ('pending', 'partial')))

    @api.depends('state', 'due_date')
    def _compute_is_overdue(self):
        """
        Compute apakah peminjaman sudah overdue
        Trigger: Ketika state atau due_date berubah
        
        Logika: Overdue jika state='borrowed' dan due_date sudah lewat
        """
        now = fields.Datetime.now()  
        for rec in self:
            rec.is_overdue = (rec.state == 'borrowed' and rec.due_date and rec.due_date < now)
    
    @api.model
    def create(self, vals):
        """
        Override method create untuk auto-generate nomor borrowing dan barcode
        
        Flow:
        1. Generate nomor borrowing dari sequence jika masih 'New'
        2. Create record
        3. Generate borrowing barcode
        """
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('product.borrowing') or 'New'
        
        record = super().create(vals)
        
        if not record.borrowing_barcode:
            record._generate_borrowing_barcode()
        
        return record

    def _generate_borrowing_barcode(self):
        """
        Generate borrowing barcode unik
        
        Format: BRW-YYYYMMDD-XXXXXX
        - BRW: Prefix untuk Borrowing
        - YYYYMMDD: Tanggal peminjaman
        - XXXXXX: Random 6 digit angka
        """
        self.ensure_one()  
        # Format tanggal menjadi YYYYMMDD
        date_str = (self.borrow_date or fields.Datetime.now()).strftime('%Y%m%d')
        # Generate random 6 digit
        random_str = str(random.randint(100000, 999999))
        # Combine menjadi barcode
        self.borrowing_barcode = f"BRW-{date_str}-{random_str}"

    @api.constrains('due_date', 'borrow_date')
    def _check_dates(self):
        """
        Validasi constraint: due_date harus setelah borrow_date
        
        Trigger: Saat create atau write pada field due_date atau borrow_date
        Raise: ValidationError jika due_date <= borrow_date
        """
        for rec in self:
            # Cek apakah due_date <= borrow_date
            if rec.due_date and rec.borrow_date and rec.due_date <= rec.borrow_date:
                raise ValidationError('Due date must be after borrow date!')
    
    def action_confirm(self):
        """
        Action: Confirm borrowing (draft -> confirmed)
        
        Tujuan: Mengkonfirmasi bahwa peminjaman telah disetujui
        """
        # Update state menjadi confirmed
        self.write({'state': 'confirmed'})

    def action_borrow(self):
        """
        Action: Mark as borrowed dan update status produk
        
        Flow:
        1. Validasi minimal ada 1 produk
        2. Cek semua produk available
        3. Update status_product menjadi 'on_borrow'
        4. Kurangi stock di warehouse
        5. Update state menjadi 'borrowed'
        
        Tujuan: Proses pengambilan barang oleh peminjam
        """
        # Get StockQuant model untuk update stock
        StockQuant = self.env['stock.quant']

        for rec in self:
            # Validasi: harus ada minimal 1 produk
            if not rec.line_ids:
                raise UserError('Please add at least one product to borrow!')

            # Step 1: Check availability semua produk
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

            # Step 2: Update status_product & reduce stock
            for line in rec.line_ids:
                detail = line.detail_product_id.sudo()  
                product = detail.product_id             
                warehouse = detail.warehouse_id or rec.warehouse_id
                location = warehouse.lot_stock_id if warehouse else False

                # Update status menjadi on_borrow
                detail.write({'status_product': 'on_borrow'})
                _logger.info(f"Product {product.display_name} marked as on_borrow.")

                # Reduce stock quantity
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

            # Step 3: Set state menjadi borrowed
            rec.write({'state': 'borrowed'})
            
            rec.message_post(
                body=f"{len(rec.line_ids)} items borrowed and stock updated.",
                message_type='notification'
            )

    def action_return(self):
        """
        Action: Open wizard untuk proses return
        
        Tujuan: Membuka wizard untuk input kondisi return setiap item
        Return: Action untuk open wizard
        """
        self.ensure_one()  
        if not self.line_ids.filtered(lambda l: l.return_status in ('pending', 'partial')):
            raise UserError('All products have been returned!')

        return {
            'type': 'ir.actions.act_window',           
            'name': 'Return Borrowed Products',         
            'res_model': 'product.borrowing.return.wizard',
            'view_mode': 'form',                        
            'target': 'new',                            
            'context': {
                'default_borrowing_id': self.id,        
            }
        }

    def action_cancel(self):
        """
        Action: Cancel borrowing
        
        Flow:
        1. Loop semua lines yang masih pending
        2. Kembalikan status produk menjadi 'available' jika masih 'on_borrow'
        3. Update state menjadi 'cancel'
        
        Tujuan: Membatalkan peminjaman (misal: peminjam tidak jadi ambil barang)
        """
        for rec in self:
            for line in rec.line_ids.filtered(lambda l: l.return_status == 'pending'):
                # Cek apakah detail produk ada dan statusnya on_borrow
                if line.detail_product_id and line.detail_product_id.sudo().status_product == 'on_borrow':
                    # Kembalikan status menjadi available
                    line.detail_product_id.sudo().write({'status_product': 'available'})
            
            # Update state menjadi cancel
            rec.write({'state': 'cancel'})

    def action_print_borrowing_document(self):
        """
        Action: Print borrowing document (report PDF)
        
        Return: Report action untuk generate PDF
        """
        return self.env.ref('product_barcode.action_report_product_borrowing').report_action(self)

    @api.model
    def _cron_check_overdue(self):
        """
        Cron Job: Check dan update status overdue
        
        Schedule: Dijalankan setiap hari (lihat data XML)
        Flow:
        1. Cari semua borrowing dengan state='borrowed' dan due_date < now
        2. Update state menjadi 'overdue'
        
        Tujuan: Auto-update status menjadi overdue untuk peminjaman yang terlambat
        """
        now = fields.Datetime.now() 
        # Search borrowing yang overdue
        overdue_borrowings = self.search([('state', '=', 'borrowed'), ('due_date', '<', now)])
        # Update state menjadi overdue
        overdue_borrowings.write({'state': 'overdue'})

class ProductBorrowingLine(models.Model):
    """
    Model untuk Product Borrowing Line (Detail Produk yang Dipinjam)
    
    Tujuan: Detail item per item yang dipinjam dalam satu borrowing
    """
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
        ('pending', 'Pending Return'),     # Belum dikembalikan
        ('partial', 'Partial Return'),     # Sebagian dikembalikan (tidak digunakan di sini)
        ('returned', 'Returned'),          # Sudah dikembalikan
        ('lost', 'Lost'),                  # Hilang
        ('damaged_return', 'Returned Damaged')  # Dikembalikan dalam kondisi rusak
    ], string='Return Status', default='pending', required=True)

    # Tanggal pengembalian (readonly, diisi saat return)
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
        """
        Onchange: Auto-fill detail produk berdasarkan barcode
        
        Trigger: Ketika user input barcode di form
        Flow:
        1. Cari product detail berdasarkan barcode dengan status available
        2. Auto-fill semua field terkait (product, warehouse, receipt, vendor)
        3. Tampilkan warning jika tidak ditemukan
        """
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
        """
        Override create: Auto-fill detail produk jika belum ada
        
        Flow:
        1. Jika detail_product_id kosong tapi ada barcode
        2. Cari detail produk berdasarkan barcode
        3. Auto-fill semua field terkait
        4. Create record
        """
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