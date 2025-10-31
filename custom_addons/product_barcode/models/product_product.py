from odoo import models, fields

# ============================================================
# MODEL: InventoryDeliveryProductDetail
# ============================================================
# class ini inherit dari product.product
# digunakan untuk menambahkan action pada tombol product pada inventory -> reporting -> stock
# ============================================================
class ProductProduct(models.Model):
    _inherit = 'product.product'

    # function ketika tombol product diklik
    def action_open_available_products(self):
        """Action ketika tombol Product diklik"""
        # memastikan hanya 1 record yang diproses
        self.ensure_one()

        # Ambil warehouse_id dari context
        warehouse_id = self.env.context.get('warehouse', False)
        # domain digunakan untuk memfilter data yang akan ditampilkan
        domain = [
            ('product_id', '=', self.id),
            ('status_product', 'in', ['available','moving','scanned','on_borrow']),
            ('receipt_id.state', '=', 'done'),
        ]
        if warehouse_id:
            domain.append(('warehouse_id', '=', warehouse_id))

        # buat window (tree view) baru untuk product 
        return {
            'name': 'Product',
            'type': 'ir.actions.act_window',
            'res_model': 'inventory.receipt.product.detail',
            'view_mode': 'tree',
            'views': [(self.env.ref('product_barcode.view_inventory_receipt_product_detail_tree_available').id, 'tree')],
            'domain': domain,
            'context': {
                'default_product_id': self.id,
                'default_warehouse_id': warehouse_id,
            },
            'target': 'current',
        }