from odoo import models, fields, api
from odoo.exceptions import ValidationError

# ============================================================
# MODEL: InventoryDeliveryProductDetail
# ============================================================
# Model ini digunakan untuk mencatat **riwayat produk** yang keluar
# (delivery) berdasarkan barcode produk yang sebelumnya tercatat
# di penerimaan barang (inventory.receipt.product.detail).
# Barcode yang bisa digunakan hanya yang statusnya 'available'.
# ============================================================

class InventoryDeliveryProductDetail(models.Model):
    _name = 'inventory.delivery.product.detail'

    # ------------------------------------------------------------
    # FIELD DEFINITIONS
    # ------------------------------------------------------------

    # Mengambil referensi receipt (penerimaan barang)
    # dari relasi Many2one ke model stock.picking, diambil melalui
    # field related 'receipt_code_product.receipt_id'.
    receipt_id = fields.Many2one(
        'stock.picking',
        string='Receipt',
        related='receipt_code_product.receipt_id',
        store=True
    )

    # Referensi ke delivery order (stock.picking) dengan filter hanya
    # picking type 'outgoing' (keluar). Hanya bisa dibaca (readonly).
    delivery_id = fields.Many2one(
        'stock.picking',
        string='Delivery',
        domain="[('picking_type_id.code','=','outgoing')]",
        readonly=True
    )

    # Produk barcode yang diambil dari tabel inventory.receipt.product.detail.
    # Domain: hanya produk yang belum punya delivery_id, sesuai warehouse, 
    # dan status 'available'.
    receipt_code_product = fields.Many2one(
        'inventory.receipt.product.detail',
        string='Product Barcode',
        domain="[('delivery_id','=',False), ('warehouse_id','=',warehouse_id), ('status_product', '=', 'available')]",
        required=True
    )

    # Barcode produk (related dari receipt_code_product)
    barcode = fields.Char(
        related='receipt_code_product.barcode',
        string='Barcode',
        store=True,
        readonly=True
    )

    # Kode produk (related)
    code_product = fields.Char(
        'Code Product',
        related='receipt_code_product.code_product',
        store=True,
        readonly=True
    )

    # Produk (Many2one related ke product_id pada receipt detail)
    product_id = fields.Many2one(
        related='receipt_code_product.product_id',
        string='Product',
        store=True,
        readonly=True
    )

    # Sales order terkait dengan pengiriman (optional)
    sale_id = fields.Many2one('sale.order', string='Sales Order')

    # Warehouse tempat barang dikirim
    warehouse_id = fields.Many2one('stock.warehouse', string='Werehouse')

    # Status produk, diambil dari receipt_code_product
    status_product = fields.Selection(
        related='receipt_code_product.status_product',
        string='Status Product',
        readonly=True,
        store=True
    )

    # ------------------------------------------------------------
    # ONCHANGE METHODS
    # ------------------------------------------------------------

    @api.onchange('delivery_id')
    def _onchange_delivery_id(self):
        """
        Ketika delivery_id berubah, maka otomatis akan mengisi
        warehouse_id sesuai warehouse dari delivery yang dipilih.
        """
        for rec in self:
            if rec.delivery_id:
                # rec.sale_id = rec.delivery_id.sale_id  # bisa digunakan jika ingin isi sale_id otomatis
                rec.warehouse_id = rec.delivery_id.picking_type_id.warehouse_id

    # ------------------------------------------------------------
    # COMPUTE METHODS
    # ------------------------------------------------------------

    @api.depends('delivery_id')
    def _compute_return_id(self):
        """
        Menghitung apakah delivery ini memiliki return (barang dikembalikan).
        Jika ada picking dengan return_id = delivery_id, maka set is_returned = True.
        """
        for rec in self:
            if rec.delivery_id:
                return_pickings = self.env['stock.picking'].search([
                    ('return_id', '=', rec.delivery_id.id),
                    ('picking_type_id.code', '=', 'incoming')
                ], limit=1)
                rec.return_id = return_pickings.id if return_pickings else False
                rec.is_returned = bool(return_pickings)

    # ------------------------------------------------------------
    # CREATE OVERRIDE
    # ------------------------------------------------------------

    @api.model
    def create(self, vals):
        """
        Override method create untuk mengisi otomatis:
        - delivery_id (jika diambil dari context)
        - warehouse_id (dari delivery yang dipilih)
        Serta mengupdate field delivery_id di inventory.receipt.product.detail
        agar produk tersebut terhubung dengan delivery ini.
        """
        parent_id = vals.get('delivery_id') or self._context.get('default_delivery_id')
        if parent_id:
            picking = self.env['stock.picking'].browse(parent_id)
            if picking:
                # Isi delivery_id jika belum diisi
                if not vals.get('delivery_id'):
                    vals['delivery_id'] = picking.id
                # Isi warehouse_id otomatis jika belum diisi
                if not vals.get('warehouse_id') and picking.picking_type_id.warehouse_id:
                    vals['warehouse_id'] = picking.picking_type_id.warehouse_id.id

        # Panggil create asli dari Odoo
        record = super().create(vals)

        # Update delivery_id di InventoryReceiptProductDetail agar produk ini
        # dianggap sudah terpakai (terkirim).
        if record.delivery_id and record.receipt_code_product:
            record.receipt_code_product.delivery_id = record.delivery_id
        return record
    
    # ------------------------------------------------------------
    # WRITE OVERRIDE
    # ------------------------------------------------------------

    def write(self, vals):
        """
        Override method write agar setiap kali delivery_id berubah,
        maka delivery_id di record receipt_code_product ikut diperbarui.
        """
        res = super().write(vals)
        for rec in self:
            delivery = vals.get('delivery_id') or rec.delivery_id
            receipt = vals.get('receipt_code_product') or rec.receipt_code_product
            if delivery and receipt:
                receipt.delivery_id = delivery
        return res
    
    # ------------------------------------------------------------
    # UNLINK OVERRIDE
    # ------------------------------------------------------------

    def unlink(self):
        """
        Sebelum record ini dihapus, reset kembali delivery_id pada
        receipt_code_product agar produk bisa digunakan ulang (tidak terkunci).
        """
        for rec in self:
            if rec.receipt_code_product:
                rec.receipt_code_product.delivery_id = False
        return super().unlink()
    
    # ------------------------------------------------------------
    # ONCHANGE DOMAIN FILTER
    # ------------------------------------------------------------

    @api.onchange('product_id', 'warehouse_id')
    def _onchange_product_id(self):
        """
        Mengubah domain (filter pilihan) pada field receipt_code_product
        agar hanya menampilkan barcode produk yang:
        - belum dikirim (delivery_id = False)
        - sesuai product_id dan warehouse_id yang dipilih
        """
        domain = [('delivery_id', '=', False)]
        if self.product_id:
            domain.append(('product_id', '=', self.product_id.id))
        if self.warehouse_id:
            domain.append(('warehouse_id', '=', self.warehouse_id.id))
        return {'domain': {'receipt_code_product': domain}}
