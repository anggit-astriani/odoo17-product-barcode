from odoo import models, fields, api
import uuid
import random

class InventoryReceiptProductDetail(models.Model):
    _name = 'inventory.receipt.product.detail'
    _rec_name = 'barcode'

    receipt_id = fields.Many2one('stock.picking', string='Receipt', domain="[('picking_type_id.code','=','incoming')]")
    code_product = fields.Char('Code Product', required=True)
    product_id = fields.Many2one('product.product', string='Product', required=True)
    purchase_id = fields.Many2one('purchase.order', string='Purchase Order')
    warehouse_id = fields.Many2one('stock.warehouse', string='Werehouse')
    delivery_id = fields.Many2one('stock.picking', string='Delivery', domain="[('picking_type_id.code','=','outgoing')]")

    vendor_id = fields.Many2one('res.partner', string='Vendor')
    vendor_code = fields.Char(string='Vendor Code', compute='_compute_vendor_code', store=True)
    unique_code = fields.Char(string='Unique Code', readonly=True, copy=False)
    barcode = fields.Char(string='Barcode', readonly=True, copy=False)
    status_product = fields.Selection([
        ('waiting', 'Waiting'),
        ('available', 'Available'),
        ('sold', 'Sold'),
        ('scanned', 'Scanned'),
        ('moving', 'Moving'),
        ('on_borrow', 'Borrowed')
    ], string='Status', default='waiting', required=True)

    print_status = fields.Selection([
        ('not_printed', 'Not Printed'),
        ('printed', 'Printed')
    ], string='Print Status', default='not_printed', required=True, 
       help='Status untuk tracking apakah barcode sudah dicetak atau belum')

    scan_process = fields.Selection([
        ('receipt', 'Receipt'),
        ('transfer', 'Internal Transfer'),
        ('transfer_receive', 'Transfer Receive'),
        ('delivery', 'Delivery Order'),
    ], string='Last Scan Process')

    condition = fields.Char(string='Condition')
    last_stock_opname_date = fields.Datetime(string='Last Stock Opname Date')
    information = fields.Text(string='Information')

    status_product = fields.Selection([
        ('waiting', 'Waiting'),
        ('available', 'Available'),
        ('sold', 'Sold'),
        ('on_borrow', 'Borrowed')
    ], string='Status', default='waiting', required=True)

    # Opname fields
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
    opname_count = fields.Integer('Opname Count', default=0, readonly=True)
    opname_history_ids = fields.One2many('inventory.opname.history', 'detail_product_id', string='Opname History')

    # Borrowing tracking fields
    borrowing_line_ids = fields.One2many('product.borrowing.line', 'detail_product_id', string='Borrowing History')
    # store=True sehingga perubahan status_product akan otomatis merecompute is_borrowed
    current_borrowing_id = fields.Many2one(
        'product.borrowing',
        string='Current Borrowing',
        compute='_compute_current_borrowing',
        store=True,
    )
    is_borrowed = fields.Boolean(
        'Is Borrowed',
        compute='_compute_is_borrowed',
        store=True,
    )


    @api.depends('borrowing_line_ids', 'borrowing_line_ids.return_status', 'borrowing_line_ids.borrowing_id.state')
    def _compute_current_borrowing(self):
        """
        Cari borrowing terakhir (pending) yang berkaitan dengan detail product ini.
        disimpan (store=True) sehingga view akan menampilkan tanpa perlu reload manual.
        """
        for rec in self:
            current = rec.borrowing_line_ids.filtered(
                lambda l: l.return_status == 'pending' and l.borrowing_id.state in ('borrowed', 'overdue', 'confirmed')
            )
            # sort descending by borrow_date (most recent)
            if current:
                current_sorted = current.sorted(key=lambda l: l.borrowing_id.borrow_date or fields.Datetime.now(), reverse=True)
                rec.current_borrowing_id = current_sorted[0].borrowing_id.id
            else:
                rec.current_borrowing_id = False

    @api.onchange('receipt_id')
    def _onchange_receipt_id(self):
        """Isi otomatis purchase, warehouse, vendor, dan domain produk dari receipt"""
        if self.receipt_id:
            # ambil purchase dan warehouse
            self.purchase_id = self.receipt_id.purchase_id
            self.warehouse_id = self.receipt_id.picking_type_id.warehouse_id

            # ambil vendor dari receipt atau purchase order
            if self.receipt_id.partner_id:
                self.vendor_id = self.receipt_id.partner_id
            elif self.receipt_id.purchase_id and self.receipt_id.purchase_id.partner_id:
                self.vendor_id = self.receipt_id.purchase_id.partner_id

            # isi vendor_code otomatis juga
            if self.vendor_id and not self.vendor_code:
                self.vendor_code = self.vendor_id.ref

            # batasi pilihan product agar sesuai dengan receipt
            products = self.receipt_id.move_ids_without_package.product_id
            return {'domain': {'product_id': [('id', 'in', products.ids)]}}


    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Isi otomatis code_product dari default_code produk"""
        if self.product_id and not self.code_product:
            self.code_product = self.product_id.default_code

    @api.onchange('vendor_id')
    def _onchange_vendor_id(self):
        """Isi otomatis vendor_code dari ref partner"""
        if self.vendor_id and not self.vendor_code:
            self.vendor_code = self.vendor_id.ref

    @api.depends('vendor_id.ref')
    def _compute_vendor_code(self):
        """Compute vendor_code dari ref partner jika kosong"""
        for rec in self:
            if rec.vendor_id and not rec.vendor_code:
                rec.vendor_code = rec.vendor_id.ref

    def _inverse_vendor_code(self):
        """Biar field tetap bisa diisi manual, tidak overwrite saat edit"""
        pass

    # ---------- create ----------
    @api.model
    def create(self, vals):
        """Isi otomatis receipt_id, purchase_id, warehouse_id saat create"""
        parent_id = vals.get('receipt_id') or self._context.get('default_receipt_id')
        if parent_id:
            picking = self.env['stock.picking'].browse(parent_id)
            if picking:
                vals.setdefault('receipt_id', picking.id)
                if not vals.get('purchase_id') and picking.purchase_id:
                    vals['purchase_id'] = picking.purchase_id.id
                if not vals.get('warehouse_id') and picking.picking_type_id.warehouse_id:
                    vals['warehouse_id'] = picking.picking_type_id.warehouse_id.id

        # otomatis isi code_product dari default_code kalau masih kosong
        if vals.get('product_id') and not vals.get('code_product'):
            product = self.env['product.product'].browse(vals['product_id'])
            vals['code_product'] = product.default_code

        # otomatis isi vendor_code dari ref kalau masih kosong
        if vals.get('vendor_id') and not vals.get('vendor_code'):
            partner = self.env['res.partner'].browse(vals['vendor_id'])
            vals['vendor_code'] = partner.ref
        
        # generate unique_code (6 karakter)
        # unique_code = str(uuid.uuid4())[:6].upper()
        unique_code = str(random.randint(100000, 999999))
        vals['unique_code'] = unique_code

        # gabungkan jadi barcode
        code_product = vals.get('code_product', 'NOPROD')
        vendor_code = vals.get('vendor_code', 'NOVENDOR')
        vals['barcode'] = f"{code_product}{vendor_code}{unique_code}"

        return super().create(vals)

    def action_print_barcode(self):
        self.ensure_one()
        # Update print status menjadi 'printed'
        self.write({'print_status': 'printed'})
        return self.env.ref('product_barcode.action_report_inventory_barcode').report_action(self)
