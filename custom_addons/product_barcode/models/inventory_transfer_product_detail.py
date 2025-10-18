from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class InventoryTransferProductDetail(models.Model):
    _name = 'inventory.transfer.product.detail'
    _description = 'Internal Product Transfer History'
    _rec_name = 'barcode'

    # Transfer Document
    transfer_id = fields.Many2one(
        'stock.picking', 
        string='Internal Transfer Document',
        domain="[('picking_type_id.code','=','internal')]",
        ondelete='set null'
    )

    # Reference ke product detail
    product_detail_id = fields.Many2one(
        'inventory.receipt.product.detail', 
        string='Product Barcode', 
        required=True,
        ondelete='restrict',
        domain="[('status_product','=','available'), ('warehouse_id','=',from_warehouse_id)]"
    )
    barcode = fields.Char(
        related='product_detail_id.barcode', 
        string='Barcode',
        store=True,
        readonly=True
    )
    product_id = fields.Many2one(
        related='product_detail_id.product_id',
        string='Product',
        store=True,
        readonly=True
    )
    code_product = fields.Char(
        related='product_detail_id.code_product',
        string='Product Code',
        store=True,
        readonly=True
    )
    unique_code = fields.Char(
        related='product_detail_id.unique_code',
        string='Product Code',
        store=True,
        readonly=True
    )
    
    # Transfer Details
    from_warehouse_id = fields.Many2one(
        'stock.warehouse', 
        string='From Warehouse', 
        required=True,
        ondelete='restrict'
    )
    to_warehouse_id = fields.Many2one(
        'stock.warehouse', 
        string='To Warehouse', 
        required=True,
        ondelete='restrict'
    )

    status_product = fields.Selection(
        related='product_detail_id.status_product',
        string='Status Product',
        readonly=True,
        store=True
    )

    # transfer_status = fields.Selection([
    #     ('preparing_shipment', ''),
    #     ('shipped', ''),
    #     ('receiving_in_progress', ''),
    #     ('received', '')
    # ], string='Status Product', readonly=True, store=True)

    @api.onchange('transfer_id')
    def _onchange_transfer_id(self):
        """Update from_warehouse and to_warehouse based on picking locations."""
        for rec in self:
            if rec.transfer_id:
                # Ambil lokasi dari picking
                source_location = rec.transfer_id.location_id
                dest_location = rec.transfer_id.location_dest_id

                # Mapping lokasi ke warehouse
                from_wh = self.env['stock.warehouse'].search([('lot_stock_id', '=', source_location.id)], limit=1)
                to_wh = self.env['stock.warehouse'].search([('lot_stock_id', '=', dest_location.id)], limit=1)

                rec.from_warehouse_id = from_wh.id if from_wh else False
                rec.to_warehouse_id = to_wh.id if to_wh else False
            else:
                rec.from_warehouse_id = False
                rec.to_warehouse_id = False