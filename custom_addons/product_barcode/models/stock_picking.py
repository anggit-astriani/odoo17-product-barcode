from odoo import models, fields, _
import uuid
from odoo.exceptions import UserError
import random

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    receipt_product_detail_line_ids = fields.One2many('inventory.receipt.product.detail', 'receipt_id', string='Detail Product Lines')

    transfer_product_detail_line_ids = fields.One2many('inventory.transfer.product.detail', 'transfer_id', string='Detail Product Lines')

    transfer_receive_product_detail_line_ids = fields.One2many('inventory.transfer.receive.product.detail', 'transfer_id', string='Detail Product Lines')

    delivery_product_detail_line_ids = fields.One2many('inventory.delivery.product.detail', 'delivery_id', string='Detail Product Lines')

    # def action_generate_barcodes(self):
    #     for picking in self:
    #         for line in picking.receipt_product_detail_line_ids:
    #             if not line.barcode:
    #                 unique_part = str(uuid.uuid4())[:6].upper()
    #                 line.barcode = f"{line.code_product or 'NOPROD'}{line.vendor_code or 'NOVENDOR'}{unique_part}"

    def action_generate_barcodes(self):
        """
        Generate barcodes berdasarkan quantity di operations (move_line_ids).
        Satu product dengan quantity 3 akan generate 3 barcode berbeda.
        """
        self.ensure_one()
        
        # Validasi: hanya untuk Receipt (incoming)
        if self.picking_type_code != 'incoming':
            raise UserError(_('Generate barcode hanya untuk Receipt (Incoming).'))
        
        # Validasi: Receipt harus sudah di-validate
        if self.state not in ('assigned', 'done'):
            raise UserError(_('Receipt harus dalam status Ready atau Done untuk generate barcode.'))
        
        # Ambil data vendor
        vendor = self.partner_id
        if not vendor:
            raise UserError(_('Vendor tidak ditemukan pada Receipt ini.'))
        
        vendor_code = vendor.ref or 'NOVENDOR'
        
        # Counter untuk tracking berapa barcode yang di-generate
        generated_count = 0
        
        # Loop setiap move line (operations)
        for move_line in self.move_line_ids_without_package:
            product = move_line.product_id
            quantity = int(move_line.quantity)  # Quantity yang akan diterima
            
            if quantity <= 0:
                continue
            
            # Ambil product code
            product_code = product.default_code or 'NOPROD'
            
            # Generate barcode sebanyak quantity
            for i in range(quantity):
                # Generate unique code (6 digit random)
                unique_code = str(random.randint(100000, 999999))
                
                # Gabungkan jadi barcode
                barcode = f"{product_code}{vendor_code}{unique_code}"
                
                # Cek apakah barcode sudah ada (untuk memastikan unique)
                existing = self.env['inventory.receipt.product.detail'].search([
                    ('barcode', '=', barcode)
                ], limit=1)
                
                # Jika barcode sudah ada, generate ulang unique_code
                while existing:
                    unique_code = str(random.randint(100000, 999999))
                    barcode = f"{product_code}{vendor_code}{unique_code}"
                    existing = self.env['inventory.receipt.product.detail'].search([
                        ('barcode', '=', barcode)
                    ], limit=1)
                
                # Create receipt product detail
                self.env['inventory.receipt.product.detail'].create({
                    'receipt_id': self.id,
                    'product_id': product.id,
                    'code_product': product_code,
                    'vendor_id': vendor.id,
                    'vendor_code': vendor_code,
                    'unique_code': unique_code,
                    'barcode': barcode,
                    'purchase_id': self.purchase_id.id if self.purchase_id else False,
                    'warehouse_id': self.picking_type_id.warehouse_id.id,
                    'status_product': 'waiting',
                })
                
                generated_count += 1
        
        # Tampilkan notifikasi sukses
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success!'),
                'message': _('%s barcode(s) berhasil di-generate.') % generated_count,
                'type': 'success',
                'sticky': False,
            }
        }