from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# ============================================================
# MODEL: InventoryTransferReceiveProductDetail
# ============================================================
# Model ini digunakan untuk mencatat histori penerimaan barang dari proses
# "Internal Transfer" antar warehouse (penerimaan setelah barang dikirim dari warehouse lain).
# Barcode yang dipindai di sini adalah barcode produk yang sebelumnya sudah dipindahkan
# (berasal dari model `inventory.transfer.product.detail`).
# ============================================================
class InventoryTransferReceiveProductDetail(models.Model):
    _name = 'inventory.transfer.receive.product.detail'     # Nama model (akan jadi nama tabel di database)
    _description = 'Internal Product Transfer Receive History'  # Deskripsi model untuk Odoo UI
    # _order = 'transfer_date desc'   # (opsional) bisa digunakan untuk mengurutkan data
    # _rec_name = 'display_name'      # (opsional) jika ingin mengganti field utama yang tampil di UI

    # ============================================================
    # FIELD GROUP: Transfer Document
    # ============================================================
    transfer_id = fields.Many2one(
        'stock.picking',                     # Relasi ke stock picking
        string='Internal Transfer Document',
        domain="[('picking_type_id.code','=','internal')]",  # Filter hanya dokumen dengan tipe internal
        ondelete='set null'                  # Jika dokumen transfer dihapus, nilai field ini akan dikosongkan
    )

    # ============================================================
    # FIELD GROUP: Product Reference
    # ============================================================
    product_transfer_id = fields.Many2one(
        'inventory.transfer.product.detail',  # Relasi ke histori transfer produk (barang keluar)
        string='Product Barcode', 
        required=True,
        ondelete='restrict',                  # Tidak boleh dihapus jika masih dipakai di sini
        domain="[('transfer_id', '=', transfer_id)]"  # Hanya tampilkan produk dari dokumen transfer yang sama
    )

    # product_detail_id = fields.Many2one(
    #     'product_transfer_id.product_detail_id', 
    #     string='Product Barcode', 
    #     required=True,
    #     ondelete='restrict',
    #     domain=[('status_product', '=', 'moving')]
    # )

    # ============================================================
    # FIELD GROUP: Related Fields (ambil data otomatis dari relasi)
    # ============================================================
    barcode = fields.Char(
        related='product_transfer_id.barcode',  # Ambil nilai barcode dari record transfer produk
        string='Barcode',
        store=True,
        readonly=True
    )

    product_id = fields.Many2one(
        related='product_transfer_id.product_id',  # Produk yang diterima dari relasi product_tranasfer_id
        string='Product',
        store=True,
        readonly=True
    )

    code_product = fields.Char(
        related='product_transfer_id.code_product',  # Kode produk dari transfer dari relasi product_tranasfer_id
        string='Product Code',
        store=True,
        readonly=True
    )

    unique_code = fields.Char(
        related='product_transfer_id.unique_code',   # Kode unik / serial number dari relasi product_tranasfer_id
        string='Product Code',
        store=True,
        readonly=True
    )

    # ============================================================
    # FIELD GROUP: Transfer Details
    # ============================================================
    from_warehouse_id = fields.Many2one(
        'stock.warehouse',              # Gudang asal (pengirim barang)
        string='From Warehouse',
        required=True,
        ondelete='restrict'
    )

    to_warehouse_id = fields.Many2one(
        'stock.warehouse',              # Gudang tujuan (penerima barang)
        string='To Warehouse',
        required=True,
        ondelete='restrict'
    )

    received_date = fields.Datetime(
        string='Received Date',         # Tanggal penerimaan barang dari transfer internal
        default=fields.Datetime.now     # Otomatis terisi waktu saat record dibuat
    )

    # ============================================================
    # METHOD: _onchange_transfer_id
    # ============================================================
    # Ketika user memilih dokumen transfer (transfer_id),
    # maka sistem otomatis akan mengisi field from_warehouse_id dan to_warehouse_id
    # berdasarkan lokasi asal & tujuan dari dokumen transfer tersebut.
    # ============================================================
    @api.onchange('transfer_id')
    def _onchange_transfer_id(self):
        """Update from_warehouse and to_warehouse based on picking locations."""
        for rec in self:
            if rec.transfer_id:
                # Ambil lokasi source (asal) dan destination (tujuan) dari dokumen transfer
                source_location = rec.transfer_id.location_id
                dest_location = rec.transfer_id.location_dest_id

                # Cari warehouse yang lokasi stock utamanya (lot_stock_id) cocok dengan lokasi transfer
                from_wh = self.env['stock.warehouse'].search([('lot_stock_id', '=', source_location.id)], limit=1)
                to_wh = self.env['stock.warehouse'].search([('lot_stock_id', '=', dest_location.id)], limit=1)

                # Isi field gudang berdasarkan hasil pencarian
                rec.from_warehouse_id = from_wh.id if from_wh else False
                rec.to_warehouse_id = to_wh.id if to_wh else False
            else:
                # Jika transfer_id dikosongkan, maka field gudang juga dikosongkan
                rec.from_warehouse_id = False
                rec.to_warehouse_id = False
