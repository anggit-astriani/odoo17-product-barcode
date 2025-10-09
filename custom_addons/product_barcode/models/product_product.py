from odoo import models, fields

class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_open_available_products(self):
        """Action ketika tombol Product diklik"""
        self.ensure_one()
        return {
            'name': 'Product',
            'type': 'ir.actions.act_window',
            'res_model': 'inventory.receipt.product.detail',
            'view_mode': 'tree,form',
            'views': [(self.env.ref('product_barcode.view_inventory_receipt_product_detail_tree_available').id, 'tree'),
                      (False, 'form')],
            'domain': [
                ('product_id', '=', self.id),
                ('status_product', '=', 'available')
            ],
            'context': {
                'default_product_id': self.id,
            },
            'target': 'current',
        }