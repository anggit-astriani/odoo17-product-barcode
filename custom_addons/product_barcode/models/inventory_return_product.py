from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

# ============================================================
# MODEL: InventoryReturnProduct
# ============================================================
# Model ini digunakan untuk mencatat proses "return barang"
# dari pelanggan (customer) ke warehouse setelah pengiriman (delivery).
# Model ini memiliki state workflow: draft → confirmed → done → cancel
# serta mengelola lines dan operasi return.
# ============================================================
class InventoryReturnProduct(models.Model):
    _name = 'inventory.return.product'
    _description = 'Product Return from Delivery'
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Untuk mencatat aktivitas dan chatter
    _rec_name = 'name'  # Field utama yang tampil sebagai nama record
    _order = 'return_date desc, id desc'  # Urutan default data

    # Nomor unik untuk setiap return (auto sequence)
    name = fields.Char(
        'Return Number', required=True, copy=False, 
        default='New', readonly=True, tracking=True
    )
    
    # Referensi ke Delivery Order (harus sudah selesai/done)
    delivery_id = fields.Many2one(
        'stock.picking', string='Delivery Order',
        domain="[('picking_type_id.code','=','outgoing'), ('state','=','done')]",
        required=True, tracking=True, readonly=True,
        states={'draft': [('readonly', False)]}  # hanya bisa diedit saat draft
    )
    
    # Customer diambil otomatis dari delivery order
    partner_id = fields.Many2one(
        'res.partner', string='Customer', 
        related='delivery_id.partner_id', store=True, readonly=True
    )
    
    # Tanggal return (default hari ini)
    return_date = fields.Datetime(
        'Return Date', default=fields.Datetime.now,
        required=True, tracking=True, readonly=True,
        states={'draft': [('readonly', False)]}
    )
    
    # Warehouse tempat barang dikembalikan
    warehouse_id = fields.Many2one(
        'stock.warehouse', string='Return To Warehouse',
        required=True, tracking=True, readonly=True,
        states={'draft': [('readonly', False)]}
    )
    
    # Status workflow dokumen
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True, readonly=True)
    
    # Detail produk yang dikembalikan
    line_ids = fields.One2many(
        'inventory.return.product.line', 'return_id', 
        string='Return Lines', readonly=True,
        states={
            'draft': [('readonly', False)], 
            'confirmed': [('readonly', False)]
        }
    )
    
    # Detail operasi per produk (jumlah total return)
    operation_ids = fields.One2many(
        'inventory.return.product.operation', 'return_id',
        string='Operations', readonly=True,
        states={'draft': [('readonly', False)]}
    )
    
    # Catatan tambahan
    notes = fields.Text('Notes')

    # User yang bertanggung jawab atas return ini
    user_id = fields.Many2one(
        'res.users', string='Responsible', 
        default=lambda self: self.env.user, tracking=True
    )
    
    # Jumlah total baris produk
    total_lines = fields.Integer(
        'Total Items', compute='_compute_total_lines', store=True
    )

    # Jumlah produk yang sudah diproses return-nya
    returned_count = fields.Integer(
        'Returned Count', compute='_compute_returned_count', store=True
    )

    # ============================================================
    # COMPUTE METHODS
    # ============================================================

    @api.depends('line_ids')
    def _compute_total_lines(self):
        """Hitung total baris return (jumlah line_ids)."""
        for rec in self:
            rec.total_lines = len(rec.line_ids)

    @api.depends('line_ids.is_processed')
    def _compute_returned_count(self):
        """Hitung berapa produk yang sudah diproses return-nya."""
        for rec in self:
            rec.returned_count = len(rec.line_ids.filtered(lambda l: l.is_processed))

    # ============================================================
    # ONCHANGE METHODS
    # ============================================================

    @api.onchange('delivery_id')
    def _onchange_delivery_id(self):
        """Set warehouse otomatis dari delivery order yang dipilih."""
        if self.delivery_id:
            self.warehouse_id = self.delivery_id.picking_type_id.warehouse_id

    # ============================================================
    # OVERRIDE CREATE
    # ============================================================

    @api.model
    def create(self, vals):
        """Override create untuk generate nomor otomatis."""
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('inventory.return.product') or 'New'
        return super().create(vals)

    # ============================================================
    # ACTION METHODS (Workflow Buttons)
    # ============================================================

    def action_confirm(self):
        """Konfirmasi return order."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Tidak ada produk yang akan di-return. Silakan tambahkan minimal 1 produk.'))
        
        # Buat otomatis operations dari return lines
        self._generate_operations()
        self.write({'state': 'confirmed'})

    def _generate_operations(self):
        """Generate operation berdasarkan produk di return line."""
        self.ensure_one()
        
        # Hapus operasi lama (jika ada)
        self.operation_ids.unlink()
        
        # Grouping produk berdasarkan product_id
        product_quantities = {}
        for line in self.line_ids:
            if line.product_id:
                if line.product_id.id not in product_quantities:
                    product_quantities[line.product_id.id] = {
                        'product': line.product_id,
                        'quantity': 0,
                        'lines': []
                    }
                # Tambahkan quantity 1 per baris
                product_quantities[line.product_id.id]['quantity'] += 1
                product_quantities[line.product_id.id]['lines'].append(line.id)
        
        # Buat record operation baru per produk
        for product_data in product_quantities.values():
            self.env['inventory.return.product.operation'].create({
                'return_id': self.id,
                'product_id': product_data['product'].id,
                'quantity': product_data['quantity'],
                'demand': product_data['quantity'],  # Demand = quantity default
            })

    def action_process_return(self):
        """Proses semua return dan update status produk & stok."""
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError(_('Tidak ada produk untuk diproses.'))
        
        # Filter hanya line yang belum diproses
        unprocessed_lines = self.line_ids.filtered(lambda l: not l.is_processed)
        if not unprocessed_lines:
            raise UserError(_('Semua produk sudah diproses.'))
        
        # Jalankan proses return per line (ubah status product)
        for line in unprocessed_lines:
            line.action_process_return()
        
        # Jalankan pergerakan stok berdasarkan operasi (jumlah produk)
        self._process_stock_movements()
        
        # Jika semua line sudah diproses, ubah status menjadi done
        if all(line.is_processed for line in self.line_ids):
            self.write({'state': 'done'})
            return [
                {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success!'),
                        'message': _('Semua produk return telah diproses dan stock telah diupdate berdasarkan Quantity.'),
                        'type': 'success',
                        'sticky': False,
                    }
                },
                {'type': 'ir.actions.client', 'tag': 'reload'},
            ]

    def _process_stock_movements(self):
        """Membuat stock picking & stock moves untuk menambah stok ke warehouse."""
        self.ensure_one()
        
        # Validasi: harus ada operasi
        if not self.operation_ids:
            raise UserError(_('Tidak ada operations untuk diproses.'))
        
        StockMove = self.env['stock.move']
        StockPicking = self.env['stock.picking']
        
        # Cari picking type 'incoming' (penerimaan barang)
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', self.warehouse_id.id),
            ('code', '=', 'incoming')
        ], limit=1)
        
        if not picking_type:
            raise UserError(_('Picking type incoming tidak ditemukan untuk warehouse %s') % self.warehouse_id.name)
        
        # Lokasi customer (barang berasal dari sini)
        customer_location = self.env.ref('stock.stock_location_customers')
        
        # Buat dokumen picking untuk return barang masuk
        picking = StockPicking.create({
            'picking_type_id': picking_type.id,
            'location_id': customer_location.id,
            'location_dest_id': self.warehouse_id.lot_stock_id.id,
            'origin': self.name,
            'move_type': 'direct',
        })
        
        # Buat stock move untuk setiap produk di operation
        for operation in self.operation_ids:
            if operation.quantity > 0:
                StockMove.create({
                    'name': operation.product_id.name,
                    'product_id': operation.product_id.id,
                    'product_uom_qty': operation.quantity,
                    'product_uom': operation.product_id.uom_id.id,
                    'picking_id': picking.id,
                    'location_id': customer_location.id,
                    'location_dest_id': self.warehouse_id.lot_stock_id.id,
                })
        
        # Validasi picking (konfirmasi & lakukan transfer)
        if picking.move_ids:
            picking.action_confirm()  # Konfirmasi picking
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty  # Set quantity done
            
            picking.button_validate()  # Validasi (selesaikan picking)
            
            # Tambahkan pesan log ke chatter
            self.message_post(
                body=_(
                    'Stock movement created: <a href="#" data-oe-model="stock.picking" data-oe-id="%s">%s</a><br/>'
                    'Total stock added: %s items'
                ) % (picking.id, picking.name, sum(self.operation_ids.mapped('quantity'))),
                subject=_('Stock Updated')
            )

    def action_done(self):
        """Menandai dokumen return sebagai selesai (done)."""
        self.ensure_one()
        
        # Pastikan semua line sudah diproses
        unprocessed = self.line_ids.filtered(lambda l: not l.is_processed)
        if unprocessed:
            raise UserError(_('Masih ada %s produk yang belum diproses. Silakan proses semua produk terlebih dahulu.') % len(unprocessed))
        
        self.write({'state': 'done'})
    
    def action_cancel(self):
        """Batalkan dokumen return (tidak bisa jika sudah done)."""
        self.ensure_one()
        if self.state == 'done':
            raise UserError(_('Return yang sudah Done tidak bisa dibatalkan.'))
        self.write({'state': 'cancel'})
    
    def action_draft(self):
        """Kembalikan status ke draft (bisa diedit lagi)."""
        self.ensure_one()
        self.write({'state': 'draft'})
