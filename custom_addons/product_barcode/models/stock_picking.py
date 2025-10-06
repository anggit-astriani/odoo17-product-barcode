from odoo import models, fields, _
import uuid

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    receipt_product_detail_line_ids = fields.One2many('inventory.receipt.product.detail', 'receipt_id', string='Detail Product Lines')

    # def action_generate_barcodes(self):
    #     for picking in self:
    #         for line in picking.receipt_product_detail_line_ids:
    #             if not line.barcode:
    #                 unique_part = str(uuid.uuid4())[:6].upper()
    #                 line.barcode = f"{line.code_product or 'NOPROD'}{line.vendor_code or 'NOVENDOR'}{unique_part}"