from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

# ============================================================
# MODEL: InventoryReturnProductLine
# ============================================================
# Model ini menyimpan detail tiap produk yang dikembalikan
# dari customer (per barcode). Satu record mewakili satu produk
# hasil scan barcode dalam dokumen return.
# ============================================================
class InventoryReturnProductLine(models.Model):
    _name = 'inventory.return.product.line'
    _description = 'Product Return Line'
    _rec_name = 'barcode_scanned'  # Field utama untuk menampilkan nama record di UI

    # ------------------------------------------------------------
    # RELASI & FIELD DASAR
    # ------------------------------------------------------------

    # Relasi ke "inventory.return.product"
    return_id = fields.Many2one(
        'inventory.return.product', string='Return', 
        ondelete='cascade', required=True
    )
    
    # Barcode yang di-scan dari produk
    barcode_scanned = fields.Char('Scanned Barcode', required=True)

    # Referensi ke detail produk (record di inventory.receipt.product.detail)
    product_detail_id = fields.Many2one(
        'inventory.receipt.product.detail',
        string='Product Detail',
        readonly=True
    )
    
    # Produk utama (relasi ke product.product) → otomatis dari product_detail_id
    product_id = fields.Many2one(
        'product.product', string='Product',
        related='product_detail_id.product_id', store=True, readonly=True
    )
    
    # Kode produk
    code_product = fields.Char(
        'Product Code', related='product_detail_id.code_product', 
        store=True, readonly=True
    )
    
    # Warehouse asal produk
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Current Warehouse',
        related='product_detail_id.warehouse_id', 
        store=True, readonly=True
    )
    
    # ------------------------------------------------------------
    # FIELD RETURN CONDITION & REASON
    # ------------------------------------------------------------

    # Kondisi barang yang dikembalikan oleh customer
    condition = fields.Selection([
        ('good', 'Good Condition'),   # Barang baik, bisa dijual ulang
        ('damaged', 'Rusak'),         # Barang rusak, perlu karantina
        ('defect', 'Cacat Produk'),   # Barang cacat, tidak layak jual
        ('wrong_item', 'Salah Kirim') # Barang salah kirim
    ], string='Kondisi Barang', required=True)
    
    # Alasan customer melakukan return
    return_reason = fields.Selection([
        ('wrong_delivery', 'Salah Pengiriman'),
        ('damaged', 'Rusak'),
        ('not_suitable', 'Tidak Sesuai'),
        ('defect', 'Cacat Produk'),
        ('change_mind', 'Berubah Pikiran'),
        ('other', 'Lainnya')
    ], string='Alasan Return', required=True)
    
    # Catatan tambahan atau keterangan lain
    notes = fields.Text('Catatan')

    # Foto kondisi barang saat return (opsional)
    image = fields.Binary('Foto Kondisi', attachment=True)
    
    # ------------------------------------------------------------
    # FIELD COMPUTED (Lokasi Tujuan & Status Baru)
    # ------------------------------------------------------------

    # Lokasi tujuan barang setelah dikembalikan (otomatis dari kondisi)
    destination_location = fields.Selection([
        ('stock', 'Kembali ke Stock'),
        ('quarantine', 'Karantina'),
        ('scrap', 'Scrap/Buang')
    ], string='Lokasi Tujuan', compute='_compute_destination', store=True)
    
    # Status produk baru setelah diproses return
    new_status = fields.Selection([
        ('available', 'Available'),
        ('waiting', 'Waiting')
    ], string='Status Baru', compute='_compute_new_status', store=True)
    
    # ------------------------------------------------------------
    # FIELD STATUS LINE
    # ------------------------------------------------------------

    # Menandai apakah produk ini sudah diproses
    is_processed = fields.Boolean('Sudah Diproses', default=False, readonly=True)
    
    # Tanggal kapan produk ini diproses return-nya
    processed_date = fields.Datetime('Tanggal Diproses', readonly=True)
    
    # State dokumen return (relasi dari parent)
    state = fields.Selection(
        related='return_id.state', string='Return Status', store=True
    )

    # ============================================================
    # ONCHANGE: SCAN BARCODE
    # ============================================================

    @api.onchange('barcode_scanned')
    def _onchange_barcode_scanned(self):
        """Dijalankan otomatis ketika user mengisi/meng-scan barcode."""
        if self.barcode_scanned:
            # 1️⃣ Cek apakah barcode sudah ada di line lain dalam return yang sama
            if self.return_id and self.return_id.id:
                existing_line = self.return_id.line_ids.filtered(
                    lambda l: l.barcode_scanned == self.barcode_scanned and l.id != self.id and l.id
                )
                if existing_line:
                    # Jika barcode sudah ada → reset dan beri warning
                    self.barcode_scanned = False
                    self.product_detail_id = False
                    return {
                        'warning': {
                            'title': 'Barcode Sudah Ada',
                            'message': f'Barcode {self.barcode_scanned} sudah ditambahkan di return ini.'
                        }
                    }
            
            # 2️⃣ Cari product detail berdasarkan barcode (hanya yang status "sold")
            detail = self.env['inventory.receipt.product.detail'].search([
                ('barcode', '=', self.barcode_scanned),
                ('status_product', '=', 'sold')
            ], limit=1)
            
            if detail:
                # 3️⃣ Validasi: pastikan produk berasal dari delivery order yang sama
                if self.return_id.delivery_id and detail.delivery_id != self.return_id.delivery_id:
                    self.barcode_scanned = False
                    self.product_detail_id = False
                    return {
                        'warning': {
                            'title': 'Barcode Tidak Sesuai',
                            'message': f'Barcode {self.barcode_scanned} bukan dari Delivery Order {self.return_id.delivery_id.name}. Produk ini dari {detail.delivery_id.name if detail.delivery_id else "delivery order lain"}.'
                        }
                    }
                
                # 4️⃣ Jika valid → set product_detail_id
                self.product_detail_id = detail.id
            else:
                # Jika tidak ditemukan → beri warning
                self.product_detail_id = False
                return {
                    'warning': {
                        'title': 'Barcode Tidak Ditemukan',
                        'message': f'Barcode {self.barcode_scanned} tidak ditemukan atau status produk bukan "Sold".'
                    }
                }

    # ============================================================
    # COMPUTE: Lokasi Tujuan Berdasarkan Kondisi Barang
    # ============================================================

    @api.depends('condition')
    def _compute_destination(self):
        """Menentukan lokasi tujuan penyimpanan barang berdasarkan kondisi."""
        for line in self:
            if line.condition == 'good':
                line.destination_location = 'stock'        # Barang baik → kembali ke stock normal
            elif line.condition in ['damaged']:
                line.destination_location = 'quarantine'    # Barang rusak → karantina
            elif line.condition in ['defect']:
                line.destination_location = 'scrap'         # Barang cacat → scrap
            else:
                line.destination_location = 'stock'         # Default
    
    # ============================================================
    # COMPUTE: Status Baru Produk Berdasarkan Kondisi
    # ============================================================

    @api.depends('condition')
    def _compute_new_status(self):
        """Menentukan status produk baru setelah diproses."""
        for line in self:
            if line.condition in ['good', 'wrong_item']:
                line.new_status = 'available'   # Barang baik / salah kirim → bisa dijual lagi
            else:
                line.new_status = 'waiting'     # Rusak / cacat → menunggu tindakan

    # ============================================================
    # ACTION: Proses Return Line (update status produk)
    # ============================================================

    def action_process_return(self):
        """Memproses return untuk 1 produk (ubah status dari SOLD ke AVAILABLE/WAITING)."""
        for line in self:
            # Validasi: tidak boleh diproses dua kali
            if line.is_processed:
                raise UserError(_('Item ini sudah diproses sebelumnya.'))
            
            # Validasi: harus ada detail produk
            if not line.product_detail_id:
                raise UserError(_('Product detail tidak ditemukan. Pastikan barcode valid.'))
            
            # Validasi: produk harus berstatus 'sold' sebelum return
            if line.product_detail_id.status_product != 'sold':
                raise UserError(_('Produk %s tidak dalam status "Sold". Status saat ini: %s') % (
                    line.barcode_scanned, 
                    dict(line.product_detail_id._fields['status_product'].selection).get(line.product_detail_id.status_product)
                ))
            
            # Mapping kondisi ke status baru produk
            status_mapping = {
                'good': 'available',
                'damaged': 'waiting',
                'defect': 'waiting',
                'wrong_item': 'available'
            }
            new_status = status_mapping.get(line.condition, 'waiting')
            
            # Ambil label teks dari field selection (untuk disimpan di catatan produk)
            condition_label = dict(line._fields['condition'].selection).get(line.condition)
            reason_label = dict(line._fields['return_reason'].selection).get(line.return_reason)
            
            # Update record di inventory.receipt.product.detail
            line.product_detail_id.write({
                'status_product': new_status,       # Ubah status produk
                'delivery_id': False,               # Hapus referensi delivery karena sudah kembali
                'condition': f"Returned: {condition_label}",  # Update kondisi di product detail
                'information': f"=== PRODUCT RETURN ===\n"
                              f"Return Number: {line.return_id.name}\n"
                              f"Return Date: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                              f"From Delivery: {line.return_id.delivery_id.name}\n"
                              f"Customer: {line.return_id.partner_id.name}\n"
                              f"Condition: {condition_label}\n"
                              f"Reason: {reason_label}\n"
                              f"New Status: {new_status.upper()}\n"
                              f"Notes: {line.notes or '-'}\n"
                              f"Processed by: {self.env.user.name}",
                'scan_process': False,  # Reset flag scan
            })
            
            # Tandai line sebagai sudah diproses
            line.write({
                'is_processed': True,
                'processed_date': fields.Datetime.now()
            })
            
        # Tampilkan notifikasi sukses di UI Odoo
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Berhasil!'),
                'message': _('Return berhasil diproses. Status produk diubah dari SOLD ke %s.') % new_status.upper(),
                'type': 'success',
                'sticky': False,
            }
        }

    # ============================================================
    # CONSTRAINT: Cegah Barcode Duplikat
    # ============================================================

    @api.constrains('barcode_scanned', 'return_id')
    def _check_duplicate_barcode(self):
        """Pastikan barcode tidak duplikat dalam satu return."""
        for line in self:
            if line.barcode_scanned and line.return_id:
                duplicate = self.search([
                    ('return_id', '=', line.return_id.id),
                    ('barcode_scanned', '=', line.barcode_scanned),
                    ('id', '!=', line.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_('Barcode %s sudah ada di return ini.') % line.barcode_scanned)
