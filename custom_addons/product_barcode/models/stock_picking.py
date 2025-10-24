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

    def action_generate_barcodes(self):
        """
        Generate barcodes berdasarkan quantity di operations (move_ids).
        Satu product dengan quantity 3 akan generate 3 barcode berbeda.
        Hanya generate barcode untuk sisa quantity yang belum digenerate.
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
        total_needed = 0
        already_complete = True
        
        # Loop setiap move (operations) - BUKAN move_line
        for move in self.move_ids_without_package:
            product = move.product_id
            
            # Gunakan field quantity dari stock.move
            quantity = int(move.quantity or 0)
            
            if quantity <= 0:
                continue
            
            total_needed += quantity
            
            # Hitung berapa barcode yang sudah di-generate untuk product ini di receipt ini
            existing_barcodes_count = self.env['inventory.receipt.product.detail'].search_count([
                ('receipt_id', '=', self.id),
                ('product_id', '=', product.id)
            ])
            
            # Hitung sisa yang perlu di-generate
            remaining_qty = quantity - existing_barcodes_count
            
            if remaining_qty > 0:
                already_complete = False
                
                # Ambil product code
                product_code = product.default_code or 'NOPROD'
                
                # Generate barcode hanya untuk sisa quantity
                for i in range(remaining_qty):
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
                        'print_status': 'not_printed'
                    })
                    
                    generated_count += 1
        
        # Jika semua barcode sudah complete, tampilkan notifikasi info
        if already_complete and total_needed > 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'info',
                    'title': _('Info'),
                    'message': _('Jumlah barcode sudah sesuai dengan quantity. Tidak ada barcode baru yang di-generate.'),
                    'sticky': False,
                }
            }
        
        # Jika tidak ada quantity sama sekali
        if total_needed == 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'warning',
                    'title': _('Warning'),
                    'message': _('Tidak ada product dengan quantity untuk di-generate barcode.'),
                    'sticky': False,
                }
            }
        
        # Tampilkan notifikasi sukses
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Success!'),
                'message': _('%s barcode(s) berhasil di-generate!') % generated_count,
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'stock.picking',
                    'res_id': self.id,
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'target': 'current',
                }
            }
        }

    def action_print_all_barcodes(self):
        """
        Print semua barcode dengan status_product = 'waiting' dan print_status = 'not_printed'
        pada receipt ini, kemudian update print_status menjadi 'printed'
        """
        self.ensure_one()
        
        # Validasi: hanya untuk Receipt (incoming)
        if self.picking_type_code != 'incoming':
            raise UserError(_('Print All Barcode hanya untuk Receipt (Incoming).'))
        
        # Cari semua barcode yang belum di-print dengan status waiting
        barcodes_to_print = self.env['inventory.receipt.product.detail'].search([
            ('receipt_id', '=', self.id),
            ('status_product', '=', 'waiting'),
            # ('print_status', '=', 'not_printed')
        ])
        
        # Validasi: pastikan ada barcode yang bisa di-print
        if not barcodes_to_print:
            raise UserError(_(
                'Tidak ada barcode yang bisa di-print.\n\n'
                'Pastikan:\n'
                '1. Sudah generate barcode terlebih dahulu\n'
                '2. Pastika print statusnya adalah "Not Printed"\n'
                '3. Pastika status product barcode adalah "Waiting"\n'
            ))
        
        # Update print_status menjadi 'printed' untuk semua barcode yang akan di-print
        barcodes_to_print.write({'print_status': 'printed'})
        
        # Generate report PDF untuk semua barcode sekaligus
        return self.env.ref('product_barcode.action_report_inventory_barcode').report_action(barcodes_to_print)