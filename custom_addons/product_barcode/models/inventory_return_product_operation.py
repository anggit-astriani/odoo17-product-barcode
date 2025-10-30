from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

# ============================================================
# MODEL: InventoryReturnProductOperation
# ============================================================
# Model ini digunakan untuk mencatat operasi atau ringkasan produk 
# yang direturn berdasarkan hasil pemindaian barcode.
# Setiap produk dalam return akan memiliki satu record di sini,
# berisi jumlah permintaan return (demand) dan jumlah aktual (quantity).
# ============================================================
class InventoryReturnProductOperation(models.Model):
    _name = 'inventory.return.product.operation'  # Nama model Odoo
    _description = 'Product Return Operation'     # Deskripsi model
    _rec_name = 'product_id'                      # Field yang ditampilkan di tree view

    # ============================================================
    # RELASI KE HEADER RETURN
    # ============================================================
    return_id = fields.Many2one(
        'inventory.return.product',   # Relasi ke model induk return
        string='Return',
        ondelete='cascade',
        required=True
    )
    
    # ============================================================
    # PRODUK YANG DIRETURN
    # ============================================================
    product_id = fields.Many2one(
        'product.product',             # Relasi ke master produk
        string='Product',
        required=True
    )
    
    # ============================================================
    # JUMLAH YANG DIHARAPKAN (EXPECTED RETURN)
    # ============================================================
    demand = fields.Integer(
        'Demand',
        required=True,
        default=0,
        help='Jumlah yang diharapkan untuk di-return (dapat diinput manual)'  
        # → Field ini biasanya diisi manual oleh user saat membuat return.
        #   Menunjukkan berapa jumlah produk yang diharapkan akan diretur.
    )
    
    # ============================================================
    # JUMLAH SEBENARNYA (ACTUAL RETURN)
    # ============================================================
    quantity = fields.Integer(
        'Quantity',                    # Label field
        readonly=True,                 # Tidak bisa diubah manual
        default=0,                     # Default = 0
        help='Jumlah aktual produk yang di-return (dari scan barcode). Ini yang akan mempengaruhi stock.'
        # → Field ini diupdate otomatis berdasarkan hasil pemindaian barcode
        #   dari model `inventory.return.product.line`
        #   sehingga user tidak bisa ubah langsung.
    )
    
    # ============================================================
    # STATUS RETURN (BERDASARKAN HEADER)
    # ============================================================
    state = fields.Selection(
        related='return_id.state',     # Ambil dari field `state` di header return
        string='Status',               # Label field
        store=True                     # Disimpan di database agar bisa digunakan untuk filter/sort
    )
    
    # ============================================================
    # VALIDASI NILAI DEMAND
    # ============================================================
    @api.constrains('demand')
    def _check_demand(self):
        """Validasi: demand tidak boleh bernilai negatif"""
        for rec in self:
            if rec.demand < 0:
                # Jika user memasukkan angka negatif, tampilkan error
                raise ValidationError(_('Demand tidak boleh negatif!'))
