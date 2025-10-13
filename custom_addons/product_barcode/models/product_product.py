from odoo import models, fields

class ProductProduct(models.Model):
    _inherit = 'product.product'

    def action_open_available_products(self):
        """Action ketika tombol Product diklik"""
        self.ensure_one()

        warehouse_id = self.env.context.get('warehouse', False)
        domain = [
            ('product_id', '=', self.id),
            ('status_product', '=', 'available'),
            ('receipt_id.state', '=', 'done'),
        ]
        if warehouse_id:
            domain.append(('warehouse_id', '=', warehouse_id))

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