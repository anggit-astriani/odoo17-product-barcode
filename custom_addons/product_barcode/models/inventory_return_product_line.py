from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class InventoryReturnProductLine(models.Model):
    _name = 'inventory.return.product.line'
    _description = 'Product Return Line'
    _rec_name = 'barcode_scanned'

    return_id = fields.Many2one('inventory.return.product', string='Return', 
                                ondelete='cascade', required=True)
    
    # Scan barcode untuk ambil product detail
    barcode_scanned = fields.Char('Scanned Barcode', required=True)
    product_detail_id = fields.Many2one('inventory.receipt.product.detail',
                                        string='Product Detail',
                                        readonly=True)
    
    product_id = fields.Many2one('product.product', string='Product',
                                 related='product_detail_id.product_id', store=True, readonly=True)
    
    code_product = fields.Char('Product Code', related='product_detail_id.code_product', 
                               store=True, readonly=True)
    
    warehouse_id = fields.Many2one('stock.warehouse', string='Current Warehouse',
                                   related='product_detail_id.warehouse_id', 
                                   store=True, readonly=True)
    
    # Field penting untuk return
    condition = fields.Selection([
        ('good', 'Good Condition'),
        ('damaged', 'Rusak'),
        ('defect', 'Cacat Produk'),
        ('wrong_item', 'Salah Kirim')
    ], string='Kondisi Barang', required=True)
    
    return_reason = fields.Selection([
        ('wrong_delivery', 'Salah Pengiriman'),
        ('damaged', 'Rusak'),
        ('not_suitable', 'Tidak Sesuai'),
        ('defect', 'Cacat Produk'),
        ('change_mind', 'Berubah Pikiran'),
        ('other', 'Lainnya')
    ], string='Alasan Return', required=True)
    
    # action_type = fields.Selection([
    #     ('refund', 'Refund'),
    #     ('replacement', 'Penggantian'),
    #     ('repair', 'Perbaikan')
    # ], string='Tindakan')
    
    notes = fields.Text('Catatan')
    image = fields.Binary('Foto Kondisi', attachment=True)
    
    destination_location = fields.Selection([
        ('stock', 'Kembali ke Stock'),
        ('quarantine', 'Karantina'),
        ('scrap', 'Scrap/Buang')
    ], string='Lokasi Tujuan', compute='_compute_destination', store=True)
    
    new_status = fields.Selection([
        ('available', 'Available'),
        ('waiting', 'Waiting')
    ], string='Status Baru', compute='_compute_new_status', store=True)
    
    is_processed = fields.Boolean('Sudah Diproses', default=False, readonly=True)
    processed_date = fields.Datetime('Tanggal Diproses', readonly=True)
    
    state = fields.Selection(related='return_id.state', string='Return Status', store=True)

    @api.onchange('barcode_scanned')
    def _onchange_barcode_scanned(self):
        """Cari product detail berdasarkan barcode yang di-scan"""
        if self.barcode_scanned:
            # Cek apakah barcode sudah ada di line lain dalam return yang sama
            if self.return_id and self.return_id.id:
                existing_line = self.return_id.line_ids.filtered(
                    lambda l: l.barcode_scanned == self.barcode_scanned and l.id != self.id and l.id
                )
                
                if existing_line:
                    self.barcode_scanned = False
                    self.product_detail_id = False
                    return {
                        'warning': {
                            'title': 'Barcode Sudah Ada',
                            'message': f'Barcode {self.barcode_scanned} sudah ditambahkan di return ini.'
                        }
                    }
            
            # Cari product detail dengan barcode yang di-scan
            detail = self.env['inventory.receipt.product.detail'].search([
                ('barcode', '=', self.barcode_scanned),
                ('status_product', '=', 'sold')
            ], limit=1)
            
            if detail:
                # Validasi apakah produk ini dari delivery order yang benar
                if self.return_id.delivery_id and detail.delivery_id != self.return_id.delivery_id:
                    self.barcode_scanned = False
                    self.product_detail_id = False
                    return {
                        'warning': {
                            'title': 'Barcode Tidak Sesuai',
                            'message': f'Barcode {self.barcode_scanned} bukan dari Delivery Order {self.return_id.delivery_id.name}. Produk ini dari {detail.delivery_id.name if detail.delivery_id else "delivery order lain"}.'
                        }
                    }
                
                self.product_detail_id = detail.id
            else:
                self.product_detail_id = False
                return {
                    'warning': {
                        'title': 'Barcode Tidak Ditemukan',
                        'message': f'Barcode {self.barcode_scanned} tidak ditemukan atau status produk bukan "Sold".'
                    }
                }

    @api.depends('condition')
    def _compute_destination(self):
        """Tentukan lokasi tujuan berdasarkan kondisi"""
        for line in self:
            if line.condition == 'good':
                line.destination_location = 'stock'
            elif line.condition in ['damaged']:
                line.destination_location = 'quarantine'
            elif line.condition in ['defect']:
                line.destination_location = 'scrap'
            else:
                line.destination_location = 'stock'

    @api.depends('condition')
    def _compute_new_status(self):
        """Tentukan status baru produk berdasarkan kondisi
        - GOOD -> AVAILABLE (bisa dijual lagi)
        - DAMAGED -> WAITING (perlu perbaikan)
        - DEFECT -> WAITING (perlu evaluasi)
        - WRONG_ITEM -> AVAILABLE (kembali ke stock)
        """
        for line in self:
            if line.condition == 'good':
                line.new_status = 'available'
            elif line.condition == 'wrong_item':
                line.new_status = 'available'
            else:  # damaged atau defect
                line.new_status = 'waiting'

    def action_process_return(self):
        """Process individual return line - Update status dari SOLD ke AVAILABLE/WAITING"""
        for line in self:
            if line.is_processed:
                raise UserError(_('Item ini sudah diproses sebelumnya.'))
            
            if not line.product_detail_id:
                raise UserError(_('Product detail tidak ditemukan. Pastikan barcode valid.'))
            
            # Validasi: produk harus dalam status 'sold'
            if line.product_detail_id.status_product != 'sold':
                raise UserError(_('Produk %s tidak dalam status "Sold". Status saat ini: %s') % (
                    line.barcode_scanned, 
                    dict(line.product_detail_id._fields['status_product'].selection).get(line.product_detail_id.status_product)
                ))
            
            # Mapping kondisi ke status baru di inventory.receipt.product.detail
            # GOOD condition -> kembali ke AVAILABLE (bisa dijual lagi)
            # DAMAGED -> WAITING (perlu pengecekan/repair)
            # DEFECT/WRONG_ITEM -> WAITING (untuk dievaluasi)
            status_mapping = {
                'good': 'available',        # Kondisi baik -> langsung available
                'damaged': 'waiting',        # Rusak -> waiting untuk repair
                'defect': 'waiting',         # Cacat -> waiting untuk evaluasi
                'wrong_item': 'available'    # Salah kirim -> kembali available
            }
            
            new_status = status_mapping.get(line.condition, 'waiting')
            
            # Buat informasi detail untuk field condition dan information
            condition_label = dict(line._fields['condition'].selection).get(line.condition)
            reason_label = dict(line._fields['return_reason'].selection).get(line.return_reason)
            # action_label = dict(line._fields['action_type'].selection).get(line.action_type)
            
            # Update product detail - ubah dari SOLD ke status baru
            line.product_detail_id.write({
                'status_product': new_status,
                'delivery_id': False,  # Clear delivery reference karena sudah di-return
                'condition': f"Returned: {condition_label}",
                'information': f"=== PRODUCT RETURN ===\n"
                              f"Return Number: {line.return_id.name}\n"
                              f"Return Date: {fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                              f"From Delivery: {line.return_id.delivery_id.name}\n"
                              f"Customer: {line.return_id.partner_id.name}\n"
                              f"Condition: {condition_label}\n"
                              f"Reason: {reason_label}\n"
                            #   f"Action: {action_label}\n"
                              f"New Status: {new_status.upper()}\n"
                              f"Notes: {line.notes or '-'}\n"
                              f"Processed by: {self.env.user.name}",
                'scan_process': False,  # Reset scan process
            })
            
            # Mark as processed
            line.write({
                'is_processed': True,
                'processed_date': fields.Datetime.now()
            })
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Berhasil!'),
                'message': _('Return berhasil diproses. Status produk diubah dari SOLD ke %s.') % new_status.upper(),
                'type': 'success',
                'sticky': False,
            }
        }

    @api.constrains('barcode_scanned', 'return_id')
    def _check_duplicate_barcode(self):
        """Validasi: barcode tidak boleh duplikat dalam satu return"""
        for line in self:
            if line.barcode_scanned and line.return_id:
                duplicate = self.search([
                    ('return_id', '=', line.return_id.id),
                    ('barcode_scanned', '=', line.barcode_scanned),
                    ('id', '!=', line.id)
                ], limit=1)
                
                if duplicate:
                    raise ValidationError(_('Barcode %s sudah ada di return ini.') % line.barcode_scanned)