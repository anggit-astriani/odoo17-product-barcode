from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class InventoryTransferReceiveProductDetail(models.Model):
    _name = 'inventory.transfer.receive.product.detail'
    _description = 'Internal Product Transfer Receive History'
    # _order = 'transfer_date desc'
    # _rec_name = 'display_name'

    # Transfer Document
    transfer_id = fields.Many2one(
        'stock.picking', 
        string='Internal Transfer Document',
        domain="[('picking_type_id.code','=','internal')]",
        ondelete='set null'
    )

    # Reference ke transfer product detail
    product_transfer_id = fields.Many2one(
        'inventory.transfer.product.detail', 
        string='Product Barcode', 
        required=True,
        ondelete='restrict',
        domain="[('transfer_id', '=', transfer_id)]"
    )
    # product_detail_id = fields.Many2one(
    #     'product_transfer_id.product_detail_id', 
    #     string='Product Barcode', 
    #     required=True,
    #     ondelete='restrict',
    #     domain=[('status_product', '=', 'moving')]
    # )
    barcode = fields.Char(
        related='product_transfer_id.barcode', 
        string='Barcode',
        store=True,
        readonly=True
    )
    product_id = fields.Many2one(
        related='product_transfer_id.product_id',
        string='Product',
        store=True,
        readonly=True
    )
    code_product = fields.Char(
        related='product_transfer_id.code_product',
        string='Product Code',
        store=True,
        readonly=True
    )
    unique_code = fields.Char(
        related='product_transfer_id.unique_code',
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
    received_date = fields.Datetime(string='Received Date', default=fields.Datetime.now)

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