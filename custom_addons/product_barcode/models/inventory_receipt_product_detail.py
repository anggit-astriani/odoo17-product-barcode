from odoo import models, fields, api
import uuid
import random

# ============================================================
# MODEL: InventoryReceiptProductDetail
# ============================================================
# Model ini digunakan untuk mencatat detail produk yang diterima
# dari proses penerimaan barang (Goods Receipt / Incoming Shipment).
# Data ini menjadi dasar manajemen stok per unit (berdasarkan barcode unik).
# ============================================================

class InventoryReceiptProductDetail(models.Model):
    _name = 'inventory.receipt.product.detail'
    _rec_name = 'barcode'  # Nama record yang ditampilkan di Odoo adalah barcode

    # ------------------------------------------------------------
    # FIELD DEFINITIONS
    # ------------------------------------------------------------

    # Relasi ke dokumen penerimaan (stock.picking) dengan tipe incoming
    receipt_id = fields.Many2one(
        'stock.picking',
        string='Receipt',
        domain="[('picking_type_id.code','=','incoming')]"
    )

    # Kode produk dari master product (default_code)
    code_product = fields.Char('Code Product', required=True)

    # Produk yang diterima (harus diisi)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )

    # Relasi ke purchase order (jika penerimaan berasal dari pembelian)
    purchase_id = fields.Many2one('purchase.order', string='Purchase Order')

    # Warehouse tempat produk diterima
    warehouse_id = fields.Many2one('stock.warehouse', string='Werehouse')

    # Relasi ke delivery order (jika produk sudah keluar)
    delivery_id = fields.Many2one(
        'stock.picking',
        string='Delivery',
        domain="[('picking_type_id.code','=','outgoing')]"
    )

    # Vendor yang mengirimkan barang
    vendor_id = fields.Many2one('res.partner', string='Vendor')

    # Kode vendor (biasanya field 'ref' pada partner)
    vendor_code = fields.Char(
        string='Vendor Code',
        compute='_compute_vendor_code',
        store=True
    )

    # Kode unik acak untuk membedakan produk satuan (6 digit)
    unique_code = fields.Char(
        string='Unique Code',
        readonly=True,
        copy=False
    )

    # Barcode hasil kombinasi code_product + vendor_code + unique_code
    barcode = fields.Char(
        string='Barcode',
        readonly=True,
        copy=False
    )

    # Status stok produk berdasarkan siklus hidup barang
    status_product = fields.Selection([
        ('waiting', 'Waiting'),      # Menunggu diproses
        ('available', 'Available'),  # Siap dijual atau dikirim
        ('sold', 'Sold'),            # Sudah terjual
        ('scanned', 'Scanned'),      # Sudah discan (sedang diproses)
        ('moving', 'Moving'),        # Sedang dipindahkan antar lokasi
        ('on_borrow', 'Borrowed')    # Sedang dipinjam
    ], string='Status', default='waiting', required=True)

    # Status cetak barcode (apakah sudah dicetak di label fisik)
    print_status = fields.Selection([
        ('not_printed', 'Not Printed'),
        ('printed', 'Printed')
    ], string='Print Status', default='not_printed', required=True,
       help='Status untuk tracking apakah barcode sudah dicetak atau belum')

    # Menyimpan proses terakhir yang dilakukan pada produk ini (tracking)
    scan_process = fields.Selection([
        ('receipt', 'Receipt'),               # Saat penerimaan
        ('transfer', 'Internal Transfer'),    # Saat transfer antar gudang
        ('transfer_receive', 'Transfer Receive'),  # Saat penerimaan transfer
        ('delivery', 'Delivery Order'),       # Saat pengiriman keluar
    ], string='Last Scan Process')

    # Kondisi fisik barang (opsional, bisa diisi manual)
    condition = fields.Char(string='Condition')

    # Waktu terakhir barang di-opname (stock count)
    last_stock_opname_date = fields.Datetime(string='Last Stock Opname Date')

    # Catatan tambahan terkait produk
    information = fields.Text(string='Information')

    # ------------------------------------------------------------
    # ONCHANGE METHODS
    # ------------------------------------------------------------

    @api.onchange('receipt_id')
    def _onchange_receipt_id(self):
        """
        Ketika receipt (picking) dipilih:
        - otomatis isi purchase_id, warehouse_id, vendor_id, vendor_code
        - batasi domain product_id agar hanya bisa pilih produk dari receipt tsb
        """
        if self.receipt_id:
            # Ambil purchase dan warehouse dari picking type
            self.purchase_id = self.receipt_id.purchase_id
            self.warehouse_id = self.receipt_id.picking_type_id.warehouse_id

            # Tentukan vendor berdasarkan partner dari receipt atau purchase
            if self.receipt_id.partner_id:
                self.vendor_id = self.receipt_id.partner_id
            elif self.receipt_id.purchase_id and self.receipt_id.purchase_id.partner_id:
                self.vendor_id = self.receipt_id.purchase_id.partner_id

            # Isi vendor_code otomatis jika ada vendor
            if self.vendor_id and not self.vendor_code:
                self.vendor_code = self.vendor_id.ref

            # Batasi pilihan produk hanya produk yang ada di dokumen receipt
            products = self.receipt_id.move_ids_without_package.product_id
            return {'domain': {'product_id': [('id', 'in', products.ids)]}}

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """
        Saat product_id diubah, otomatis isi code_product
        berdasarkan default_code produk (internal reference).
        """
        if self.product_id and not self.code_product:
            self.code_product = self.product_id.default_code

    @api.onchange('vendor_id')
    def _onchange_vendor_id(self):
        """
        Saat vendor diganti, otomatis isi vendor_code dari field 'ref'.
        """
        if self.vendor_id and not self.vendor_code:
            self.vendor_code = self.vendor_id.ref

    @api.depends('vendor_id.ref')
    def _compute_vendor_code(self):
        """
        Hitung otomatis vendor_code dari ref partner jika belum terisi.
        (agar bisa disimpan ke database)
        """
        for rec in self:
            if rec.vendor_id and not rec.vendor_code:
                rec.vendor_code = rec.vendor_id.ref

    def _inverse_vendor_code(self):
        """
        Fungsi dummy agar field vendor_code bisa diisi manual (tidak overwrite).
        """
        pass

    # ------------------------------------------------------------
    # CREATE OVERRIDE
    # ------------------------------------------------------------

    @api.model
    def create(self, vals):
        """
        Override method create untuk:
        - otomatis isi receipt_id, purchase_id, warehouse_id
        - otomatis isi code_product dan vendor_code
        - generate unique_code acak (6 digit)
        - generate barcode gabungan dari code_product + vendor_code + unique_code
        """
        # Jika create dari form receipt, ambil context default_receipt_id
        parent_id = vals.get('receipt_id') or self._context.get('default_receipt_id')
        if parent_id:
            picking = self.env['stock.picking'].browse(parent_id)
            if picking:
                # isi field terkait picking
                vals.setdefault('receipt_id', picking.id)
                if not vals.get('purchase_id') and picking.purchase_id:
                    vals['purchase_id'] = picking.purchase_id.id
                if not vals.get('warehouse_id') and picking.picking_type_id.warehouse_id:
                    vals['warehouse_id'] = picking.picking_type_id.warehouse_id.id

        # Isi code_product otomatis dari default_code produk
        if vals.get('product_id') and not vals.get('code_product'):
            product = self.env['product.product'].browse(vals['product_id'])
            vals['code_product'] = product.default_code

        # Isi vendor_code otomatis dari ref partner
        if vals.get('vendor_id') and not vals.get('vendor_code'):
            partner = self.env['res.partner'].browse(vals['vendor_id'])
            vals['vendor_code'] = partner.ref
        
        # Buat unique code 6 digit acak
        unique_code = str(random.randint(100000, 999999))
        vals['unique_code'] = unique_code

        # Gabungkan code_product + vendor_code + unique_code menjadi barcode
        code_product = vals.get('code_product', 'NOPROD')
        vendor_code = vals.get('vendor_code', 'NOVENDOR')
        vals['barcode'] = f"{code_product}{vendor_code}{unique_code}"

        # Lanjutkan ke proses create standar Odoo
        return super().create(vals)

    # ------------------------------------------------------------
    # ACTION METHOD (BUTTON)
    # ------------------------------------------------------------

    def action_print_barcode(self):
        """
        Tombol aksi untuk mencetak barcode produk.
        - Update print_status menjadi 'printed'
        - Memanggil report action (didefinisikan di XML)
        """
        self.ensure_one()  # pastikan hanya satu record
        # Update status cetak
        self.write({'print_status': 'printed'})
        # Panggil report action yang ada di reports/inventory_receipt_barcode_report.xml
        return self.env.ref('product_barcode.action_report_inventory_barcode').report_action(self)
