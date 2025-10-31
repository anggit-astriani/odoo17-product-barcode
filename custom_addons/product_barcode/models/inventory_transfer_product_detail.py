from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# ============================================================
# MODEL: InventoryTransferProductDetail
# ============================================================
# Model ini digunakan untuk mencatat histori pemindahan produk antar gudang (internal transfer).
# Barcode produk yang bisa dipindahkan diambil dari model `inventory.receipt.product.detail`
# dengan syarat status produk masih 'available' (artinya produk tersebut masih bisa dipindahkan).
# ============================================================
class InventoryTransferProductDetail(models.Model):
    _name = 'inventory.transfer.product.detail'   # Nama model baru (akan menjadi nama tabel di database)
    _description = 'Internal Product Transfer History'  # Deskripsi model
    _rec_name = 'barcode'  # Field yang ditampilkan sebagai nama record di Odoo UI

    # ============================================================
    # FIELD GROUP: Transfer Document
    # ============================================================
    transfer_id = fields.Many2one(
        'stock.picking',                # Relasi ke dokumen picking Odoo (internal transfer)
        string='Internal Transfer Document',
        domain="[('picking_type_id.code','=','internal')]",  # Hanya tampilkan dokumen dengan tipe internal transfer
        ondelete='set null'             # Jika dokumen transfer dihapus, field ini di-set null (tidak ikut dihapus)
    )

    # ============================================================
    # FIELD GROUP: Product Reference
    # ============================================================
    product_detail_id = fields.Many2one(
        'inventory.receipt.product.detail',  # Relasi ke model detail penerimaan produk
        string='Product Barcode',
        required=True,
        ondelete='restrict',
        domain="[('status_product','=','available'), ('warehouse_id','=',from_warehouse_id)]"  
        # Filter agar hanya barcode produk yang 'available' di gudang asal (from_warehouse) yang bisa dipilih
    )

    barcode = fields.Char(
        related='product_detail_id.barcode',  # Ambil nilai dari field barcode di model relasi (product_detail_id)
        string='Barcode',
        store=True,
        readonly=True
    )

    product_id = fields.Many2one(
        related='product_detail_id.product_id',  # Produk produk berdasarkan pada product_detail_id
        string='Product',
        store=True,
        readonly=True
    )

    code_product = fields.Char(
        related='product_detail_id.code_product',  # Kode produk berdasarkan pada product_detail_id
        string='Product Code',
        store=True,
        readonly=True
    )

    unique_code = fields.Char(
        related='product_detail_id.unique_code',   # Kode unik produk berdasarkan pada product_detail_id
        string='Product Code',
        store=True,
        readonly=True
    )

    # ============================================================
    # FIELD GROUP: Transfer Details
    # ============================================================
    from_warehouse_id = fields.Many2one(
        'stock.warehouse',     # Gudang asal produk
        string='From Warehouse',
        required=True,
        ondelete='restrict'    # Tidak boleh dihapus jika masih digunakan
    )

    to_warehouse_id = fields.Many2one(
        'stock.warehouse',     # Gudang tujuan produk
        string='To Warehouse',
        required=True,
        ondelete='restrict'
    )

    # ============================================================
    # FIELD GROUP: Status Product (relasi dari product detail)
    # ============================================================
    status_product = fields.Selection(
        related='product_detail_id.status_product',  # Status produk dari model referensi
        string='Status Product',
        readonly=True,
        store=True
    )

    # ============================================================
    # Menambahkan status transfer produk
    # ============================================================
    # transfer_status = fields.Selection([
    #     ('preparing_shipment', 'Preparing Shipment'),
    #     ('shipped', 'Shipped'),
    #     ('receiving_in_progress', 'Receiving in Progress'),
    #     ('received', 'Received')
    # ], string='Transfer Status', readonly=True, store=True)

    # ============================================================
    # METHOD: onchange(transfer_id)
    # ============================================================
    # Ketika user memilih dokumen transfer (transfer_id),
    # maka field from_warehouse_id dan to_warehouse_id otomatis terisi
    # berdasarkan lokasi source dan destination pada dokumen transfer tersebut.
    # ============================================================
    @api.onchange('transfer_id')
    def _onchange_transfer_id(self):
        """Update from_warehouse dan to_warehouse berdasarkan pada picking locations."""
        for rec in self:
            if rec.transfer_id:
                # Ambil lokasi asal dan tujuan dari dokumen picking
                source_location = rec.transfer_id.location_id
                dest_location = rec.transfer_id.location_dest_id

                # Cari warehouse yang memiliki lokasi stock (lot_stock_id) sesuai dengan lokasi picking
                from_wh = self.env['stock.warehouse'].search([('lot_stock_id', '=', source_location.id)], limit=1)
                to_wh = self.env['stock.warehouse'].search([('lot_stock_id', '=', dest_location.id)], limit=1)

                # Isi field warehouse berdasarkan hasil pencarian
                rec.from_warehouse_id = from_wh.id if from_wh else False
                rec.to_warehouse_id = to_wh.id if to_wh else False
            else:
                # Jika transfer_id kosong, kosongkan juga field warehouse
                rec.from_warehouse_id = False
                rec.to_warehouse_id = False
