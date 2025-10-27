from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class InventoryReturnProductOperation(models.Model):
    _name = 'inventory.return.product.operation'
    _description = 'Product Return Operation'
    _rec_name = 'product_id'

    return_id = fields.Many2one('inventory.return.product', string='Return',
                                ondelete='cascade', required=True)
    
    product_id = fields.Many2one('product.product', string='Product', required=True)
    
    demand = fields.Integer('Demand', required=True, default=0,
                           help='Jumlah yang diharapkan untuk di-return (dapat diinput manual)')
    
    quantity = fields.Integer('Quantity', readonly=True, default=0,
                             help='Jumlah aktual produk yang di-return (dari scan barcode). Ini yang akan mempengaruhi stock.')
    
    state = fields.Selection(related='return_id.state', string='Status', store=True)
    
    @api.constrains('demand')
    def _check_demand(self):
        """Validasi: demand tidak boleh negatif"""
        for rec in self:
            if rec.demand < 0:
                raise ValidationError(_('Demand tidak boleh negatif!'))