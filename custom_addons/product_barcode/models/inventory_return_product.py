from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class InventoryReturnProduct(models.Model):
    _name = 'inventory.return.product'
    _description = 'Product Return from Delivery'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'return_date desc, id desc'

    name = fields.Char('Return Number', required=True, copy=False, 
                       default='New', readonly=True, tracking=True)
    
    # Reference ke Delivery Order
    delivery_id = fields.Many2one('stock.picking', string='Delivery Order',
                                  domain="[('picking_type_id.code','=','outgoing'), ('state','=','done')]",
                                  required=True, tracking=True, readonly=True,
                                  states={'draft': [('readonly', False)]})
    
    partner_id = fields.Many2one('res.partner', string='Customer', 
                                 related='delivery_id.partner_id', store=True, readonly=True)
    
    return_date = fields.Datetime('Return Date', default=fields.Datetime.now,
                                   required=True, tracking=True, readonly=True,
                                   states={'draft': [('readonly', False)]})
    
    warehouse_id = fields.Many2one('stock.warehouse', string='Return To Warehouse',
                                    required=True, tracking=True, readonly=True,
                                    states={'draft': [('readonly', False)]})
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True, readonly=True)
    
    # Lines untuk detail return
    line_ids = fields.One2many('inventory.return.product.line', 'return_id', 
                               string='Return Lines', readonly=True,
                               states={'draft': [('readonly', False)], 'confirmed': [('readonly', False)]})
    
    # Operations lines untuk stock movement
    operation_ids = fields.One2many('inventory.return.product.operation', 'return_id',
                                    string='Operations', readonly=True,
                                    states={'draft': [('readonly', False)]})
    
    notes = fields.Text('Notes')
    user_id = fields.Many2one('res.users', string='Responsible', 
                              default=lambda self: self.env.user, tracking=True)
    
    # Computed fields
    total_lines = fields.Integer('Total Items', compute='_compute_total_lines', store=True)
    returned_count = fields.Integer('Returned Count', compute='_compute_returned_count', store=True)

    @api.depends('line_ids')
    def _compute_total_lines(self):
        for rec in self:
            rec.total_lines = len(rec.line_ids)

    @api.depends('line_ids.is_processed')
    def _compute_returned_count(self):
        for rec in self:
            rec.returned_count = len(rec.line_ids.filtered(lambda l: l.is_processed))

    @api.onchange('delivery_id')
    def _onchange_delivery_id(self):
        """Set warehouse otomatis dari delivery order"""
        if self.delivery_id:
            self.warehouse_id = self.delivery_id.picking_type_id.warehouse_id

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('inventory.return.product') or 'New'
        return super().create(vals)

    def action_confirm(self):
        """Confirm return order"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Tidak ada produk yang akan di-return. Silakan tambahkan minimal 1 produk.'))
        
        # Auto-generate operations dari return lines
        self._generate_operations()
        
        self.write({'state': 'confirmed'})

    def _generate_operations(self):
        """Generate operations berdasarkan return lines yang sudah di-scan"""
        self.ensure_one()
        
        # Hapus operations yang ada (jika ada)
        self.operation_ids.unlink()
        
        # Group return lines by product
        product_quantities = {}
        for line in self.line_ids:
            if line.product_id:
                if line.product_id.id not in product_quantities:
                    product_quantities[line.product_id.id] = {
                        'product': line.product_id,
                        'quantity': 0,
                        'lines': []
                    }
                product_quantities[line.product_id.id]['quantity'] += 1
                product_quantities[line.product_id.id]['lines'].append(line.id)
        
        # Create operation lines
        for product_data in product_quantities.values():
            self.env['inventory.return.product.operation'].create({
                'return_id': self.id,
                'product_id': product_data['product'].id,
                'quantity': product_data['quantity'],
                'demand': product_data['quantity'],  # Default demand = quantity
            })

    def action_process_return(self):
        """Process all returns and update product status & stock"""
        self.ensure_one()
        
        if not self.line_ids:
            raise UserError(_('Tidak ada produk untuk diproses.'))
        
        unprocessed_lines = self.line_ids.filtered(lambda l: not l.is_processed)
        if not unprocessed_lines:
            raise UserError(_('Semua produk sudah diproses.'))
        
        # Process each line (update status product)
        for line in unprocessed_lines:
            line.action_process_return()
        
        # Process stock movements berdasarkan operations (QUANTITY yang mempengaruhi stock)
        self._process_stock_movements()
        
        # Check if all lines are processed
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
        """Create stock moves untuk menambah stock di warehouse berdasarkan QUANTITY"""
        self.ensure_one()
        
        # Validasi: harus ada operations
        if not self.operation_ids:
            raise UserError(_('Tidak ada operations untuk diproses.'))
        
        StockMove = self.env['stock.move']
        StockPicking = self.env['stock.picking']
        
        # Cari picking type untuk return (incoming)
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', self.warehouse_id.id),
            ('code', '=', 'incoming')
        ], limit=1)
        
        if not picking_type:
            raise UserError(_('Picking type incoming tidak ditemukan untuk warehouse %s') % self.warehouse_id.name)
        
        # Customer location
        customer_location = self.env.ref('stock.stock_location_customers')
        
        # Buat stock picking untuk return
        picking = StockPicking.create({
            'picking_type_id': picking_type.id,
            'location_id': customer_location.id,
            'location_dest_id': self.warehouse_id.lot_stock_id.id,
            'origin': self.name,
            'move_type': 'direct',
        })
        
        # Create stock moves untuk setiap operation
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
        
        # Validate picking
        if picking.move_ids:
            # Confirm picking
            picking.action_confirm()
            
            # Set quantity done = product_uom_qty
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
            
            # Validate (done)
            picking.button_validate()
            
            # Log message
            self.message_post(
                body=_('Stock movement created: <a href="#" data-oe-model="stock.picking" data-oe-id="%s">%s</a><br/>'
                    'Total stock added: %s items') % (picking.id, picking.name, sum(self.operation_ids.mapped('quantity'))),
                subject=_('Stock Updated')
            )

    def action_done(self):
        """Mark return as done"""
        self.ensure_one()
        
        # Validasi: semua line harus sudah diproses
        unprocessed = self.line_ids.filtered(lambda l: not l.is_processed)
        if unprocessed:
            raise UserError(_('Masih ada %s produk yang belum diproses. Silakan proses semua produk terlebih dahulu.') % len(unprocessed))
        
        self.write({'state': 'done'})
    
    def action_cancel(self):
        """Cancel return order"""
        self.ensure_one()
        if self.state == 'done':
            raise UserError(_('Return yang sudah Done tidak bisa dibatalkan.'))
        self.write({'state': 'cancel'})
    
    def action_draft(self):
        """Set back to draft"""
        self.ensure_one()
        self.write({'state': 'draft'})