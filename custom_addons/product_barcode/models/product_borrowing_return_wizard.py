from odoo import models, fields, api
from odoo.exceptions import UserError


class ProductBorrowingReturnWizard(models.TransientModel):
    _name = 'product.borrowing.return.wizard'
    _description = 'Product Borrowing Return Wizard'

    borrowing_id = fields.Many2one('product.borrowing', string='Borrowing', required=True, readonly=True)
    return_date = fields.Datetime('Return Date', default=fields.Datetime.now, required=True)
    line_ids = fields.One2many('product.borrowing.return.wizard.line', 'wizard_id', string='Return Lines')

    notes = fields.Text('Return Notes')

    @api.onchange('borrowing_id')
    def _onchange_borrowing_id(self):
        if self.borrowing_id:
            # Auto-populate lines from borrowing lines yang pending
            lines = []
            for borrow_line in self.borrowing_id.line_ids.filtered(lambda l: l.return_status == 'pending'):
                lines.append((0, 0, {
                    'borrowing_line_id': borrow_line.id,
                    'barcode': borrow_line.barcode,
                    'product_id': borrow_line.product_id.id,
                    'to_return': True,
                    'return_condition': 'good',
                }))
            self.line_ids = lines

    def action_process_return(self):
        """Process the return"""
        self.ensure_one()

        if not self.line_ids.filtered(lambda l: l.to_return):
            raise UserError('Please select at least one item to return!')

        returned_count = 0

        for line in self.line_ids.filtered(lambda l: l.to_return):
            # Update borrowing line
            line.borrowing_line_id.write({
                'return_status': 'returned',
                'return_date': self.return_date,
                'return_condition': line.return_condition,
                'return_notes': line.return_notes or self.notes,
            })

            # Update product status based on return condition
            if line.borrowing_line_id.detail_product_id:
                detail = line.borrowing_line_id.detail_product_id

                if line.return_condition == 'lost':
                    # Mark as sold (removed from inventory)
                    detail.sudo().write({
                        'status_product': 'sold',
                        'last_opname_notes': f'Lost during borrowing {self.borrowing_id.name}'
                    })
                elif line.return_condition == 'damaged':
                    # Return to available but mark damage
                    note = f'Returned damaged from borrowing {self.borrowing_id.name}'
                    if line.return_notes:
                        note += f': {line.return_notes}'
                    detail.sudo().write({
                        'status_product': 'available',
                        'last_physical_condition': 'damaged',
                        'last_opname_notes': note
                    })
                elif line.return_condition == 'minor_damage':
                    # Return to available with minor damage note
                    note = f'Returned with minor damage from borrowing {self.borrowing_id.name}'
                    if line.return_notes:
                        note += f': {line.return_notes}'
                    detail.sudo().write({
                        'status_product': 'available',
                        'last_physical_condition': 'damaged',
                        'last_opname_notes': note
                    })
                else:
                    # Good condition - return to available
                    detail.sudo().write({
                        'status_product': 'available'
                    })

            returned_count += 1

        # Check if all items returned
        pending_lines = self.borrowing_id.line_ids.filtered(lambda l: l.return_status == 'pending')

        if not pending_lines:
            # All items returned
            self.borrowing_id.write({
                'state': 'returned',
                'actual_return_date': self.return_date
            })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Return Processed',
                'message': f'{returned_count} item(s) have been returned successfully.',
                'type': 'success',
                'sticky': False,
            }
        }


class ProductBorrowingReturnWizardLine(models.TransientModel):
    _name = 'product.borrowing.return.wizard.line'
    _description = 'Product Borrowing Return Wizard Line'

    wizard_id = fields.Many2one('product.borrowing.return.wizard', string='Wizard', required=True, ondelete='cascade')
    borrowing_line_id = fields.Many2one('product.borrowing.line', string='Borrowing Line', required=True)

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