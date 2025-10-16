from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ProductBorrowingReturnWizard(models.TransientModel):
    _name = 'product.borrowing.return.wizard'
    _description = 'Borrowing Return Wizard'

    borrowing_id = fields.Many2one('product.borrowing', string='Borrowing', required=True, readonly=True)
    return_date = fields.Datetime('Return Date', default=fields.Datetime.now, required=True)
    notes = fields.Text('Return Notes')
    line_ids = fields.One2many('product.borrowing.return.wizard.line', 'wizard_id', string='Items to Return')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
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
        """Process the return and restock."""
        self.ensure_one()
        StockQuant = self.env['stock.quant']

        if not self.line_ids.filtered(lambda l: l.to_return):
            raise UserError('Please select at least one item to return!')

        returned_count = 0

        for line in self.line_ids.filtered(lambda l: l.to_return):
            borrow_line = line.borrowing_line_id
            if not borrow_line:
                raise UserError('Some return lines are missing the linked borrowing line!')

            detail = borrow_line.detail_product_id.sudo()
            product = detail.product_id
            warehouse = detail.warehouse_id or self.borrowing_id.warehouse_id
            location = warehouse.lot_stock_id if warehouse else False

            # Update product status
            if line.return_condition == 'lost':
                detail.write({'status_product': 'sold'})
            elif line.return_condition in ('damaged', 'minor_damage'):
                detail.write({
                    'status_product': 'available',
                    'last_physical_condition': 'damaged'
                })
            else:
                detail.write({'status_product': 'available'})

            # Update stock
            if product and location and line.return_condition != 'lost':
                quant = StockQuant.search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id)
                ], limit=1)
                if quant:
                    quant.sudo().write({'quantity': quant.quantity + 1})
                else:
                    StockQuant.sudo().create({
                        'product_id': product.id,
                        'location_id': location.id,
                        'quantity': 1,
                    })

            # Update borrow line
            borrow_line.write({
                'return_status': 'returned',
                'return_date': self.return_date,
                'return_condition': line.return_condition,
                'return_notes': line.return_notes or self.notes,
            })
            returned_count += 1

        # Update borrowing main record
        self.borrowing_id.write({
            'state': 'returned',
            'actual_return_date': fields.Datetime.now(),
        })

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

    to_return = fields.Boolean('Return?', default=True)
    return_condition = fields.Selection([
        ('good', 'Good'),
        ('minor_damage', 'Minor Damage'),
        ('damaged', 'Damaged'),
        ('lost', 'Lost')
    ], string='Condition', required=True, default='good')

    return_notes = fields.Text('Notes')
