from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

class ProductBorrowingReturnWizard(models.TransientModel):
    """
    Wizard untuk Proses Pengembalian Produk yang Dipinjam
    
    Tujuan: 
    - Interface untuk input kondisi return setiap item
    - Proses return: update status produk, restore stock, update borrowing status
    
    TransientModel: Data wizard akan otomatis terhapus setelah beberapa waktu
    """
    _name = 'product.borrowing.return.wizard'
    _description = 'Borrowing Return Wizard'
    
    borrowing_id = fields.Many2one('product.borrowing', string='Borrowing', required=True, readonly=True)
    return_date = fields.Datetime('Return Date', default=fields.Datetime.now, required=True)
    notes = fields.Text('Return Notes')
    line_ids = fields.One2many('product.borrowing.return.wizard.line', 'wizard_id', string='Items to Return')
    
    @api.model
    def default_get(self, fields_list):
        """
        Override default_get untuk auto-populate wizard lines
        
        Flow:
        1. Get borrowing_id dari context
        2. Loop semua borrowing lines dengan status pending/partial
        3. Create wizard lines dengan default condition='good' dan to_return=True
        
        Tujuan: Auto-fill wizard dengan items yang masih pending
        """
        # Call super untuk get default values
        res = super().default_get(fields_list)
        # Get borrowing_id dari context (dikirim dari action_return)
        borrowing_id = self.env.context.get('default_borrowing_id')

        if borrowing_id:
            borrowing = self.env['product.borrowing'].browse(borrowing_id)
            lines = []  

            for line in borrowing.line_ids.filtered(lambda l: l.return_status in ('pending', 'partial')):
                lines.append((0, 0, {
                    'borrowing_line_id': line.id,       
                    'barcode': line.barcode,            
                    'product_id': line.product_id.id,   
                    'return_condition': 'good',         
                    'to_return': True,                  
                }))

            res.update({
                'borrowing_id': borrowing_id,
                'line_ids': lines
            })

        return res
    
    def action_process_return(self):
        """
        Action: Process return dan restock
        
        Flow untuk setiap item yang di-check:
        1. Update status detail produk berdasarkan kondisi return
        2. Restore stock quantity (kecuali jika lost)
        3. Update borrowing line (return_status, return_date, return_condition)
        4. Update borrowing header status jika semua sudah dikembalikan
        
        Return: Notification dan close wizard
        """
        self.ensure_one()  
        StockQuant = self.env['stock.quant']

        # Validasi: harus ada minimal 1 item yang di-check untuk return
        if not self.line_ids.filtered(lambda l: l.to_return):
            raise UserError('Please select at least one item to return!')

        returned_count = 0  # Counter items yang berhasil di-return

        for line in self.line_ids.filtered(lambda l: l.to_return):
            borrow_line = line.borrowing_line_id
            if not borrow_line:
                raise UserError('Some return lines are missing the linked borrowing line!')

            # Get detail produk dengan sudo untuk bypass permission
            detail = borrow_line.detail_product_id.sudo()
            product = detail.product_id                          
            warehouse = detail.warehouse_id or self.borrowing_id.warehouse_id 
            location = warehouse.lot_stock_id if warehouse else False  

            if line.return_condition == 'lost':
                # Jika hilang: set status menjadi 'sold' (considered sold/lost)
                detail.write({'status_product': 'sold'})
                
            elif line.return_condition in ('damaged', 'minor_damage'):
                # Jika rusak: set available tapi tandai sebagai damaged
                detail.write({
                    'status_product': 'available',           # Masih available
                    'last_physical_condition': 'damaged'     # Tapi kondisi damaged
                })
                
            else:
                # Jika kondisi baik: set kembali available
                detail.write({'status_product': 'available'})

            # Hanya restore stock jika ada product, location, dan kondisi bukan lost
            if product and location and line.return_condition != 'lost':
                quant = StockQuant.search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id)
                ], limit=1)
                
                if quant:
                    # Jika quant  ada, tambah quantity +1
                    quant.sudo().write({'quantity': quant.quantity + 1})
                else:
                    # Jika quant belum ada, create baru dengan qty 1
                    StockQuant.sudo().create({
                        'product_id': product.id,
                        'location_id': location.id,
                        'quantity': 1,
                    })

            borrow_line.write({
                'return_status': 'returned',              
                'return_date': self.return_date,          
                'return_condition': line.return_condition,
                'return_notes': line.return_notes or self.notes,
            })
            
            returned_count += 1

        # Update borrowing status menjadi 'returned' dan set actual_return_date
        self.borrowing_id.write({
            'state': 'returned',
            'actual_return_date': fields.Datetime.now(),
        })

        # Return client action untuk show notification dan close wizard
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Return Processed',                           
                'message': f'{returned_count} item(s) successfully returned.',
                'type': 'success',                                     
                'sticky': False,                                       
                'next': {'type': 'ir.actions.act_window_close'},      
            },
        }


class ProductBorrowingReturnWizardLine(models.TransientModel):
    """
    Wizard Line untuk Detail Item yang Akan Dikembalikan
    
    Tujuan: Input kondisi return per item
    """
    _name = 'product.borrowing.return.wizard.line'
    _description = 'Product Borrowing Return Wizard Line'
    
    wizard_id = fields.Many2one(
        'product.borrowing.return.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    borrowing_line_id = fields.Many2one(
        'product.borrowing.line',
        string='Borrowing Line',
        required=True
    )

    barcode = fields.Char('Barcode', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)

    # Checkbox: Apakah item ini akan di-return? (default: True)
    to_return = fields.Boolean('Return?', default=True)
    
    return_condition = fields.Selection([
        ('good', 'Good'),              
        ('minor_damage', 'Minor Damage'),
        ('damaged', 'Damaged'),        
        ('lost', 'Lost')               
    ], string='Condition', required=True, default='good')

    # Catatan return (optional, jika kosong akan pakai notes dari wizard header)
    return_notes = fields.Text('Notes')