from odoo import models, fields, api
from odoo.exceptions import UserError
import base64
import io
import xlsxwriter
from datetime import datetime


class StockOpnameExportWizard(models.TransientModel):
    _name = 'stock.opname.export.wizard'
    _description = 'Stock Opname Export Wizard'

    opname_id = fields.Many2one('stock.opname', string='Stock Opname', required=True, readonly=True)
    export_format = fields.Selection([
        ('excel', 'Excel (.xlsx)'),
        ('pdf', 'PDF')
    ], string='Export Format', required=True, default='excel')

    # Filtering options
    filter_match_status = fields.Selection([
        ('all', 'All'),
        ('matched', 'Matched Only'),
        ('status_mismatch', 'Status Mismatch Only'),
        ('unmatched', 'Unmatched Only')
    ], string='Filter by Match Status', required=True, default='all')

    filter_product_condition = fields.Selection([
        ('all', 'All'),
        ('good', 'Good Only'),
        ('damaged', 'Damaged Only'),
        ('missing_parts', 'Missing Parts Only'),
        ('defect', 'Defect Only')
    ], string='Filter by Product Condition', required=True, default='all')

    include_summary = fields.Boolean('Include Summary', default=True)
    include_details = fields.Boolean('Include Line Details', default=True)

    # Result file
    file_data = fields.Binary('File', readonly=True)
    file_name = fields.Char('File Name', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done')
    ], default='draft')

    def action_export(self):
        """Generate export file based on selected format"""
        self.ensure_one()

        if not self.include_summary and not self.include_details:
            raise UserError('Please select at least one option: Summary or Details')

        if self.export_format == 'excel':
            self._export_excel()
        else:
            self._export_pdf()

        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.opname.export.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': {'form_view_initial_mode': 'edit'}
        }

    def _get_filtered_lines(self):
        """Get filtered opname lines based on wizard settings"""
        lines = self.opname_id.line_ids

        # Filter by match status
        if self.filter_match_status != 'all':
            lines = lines.filtered(lambda l: l.match_status == self.filter_match_status)

        # Filter by product condition
        if self.filter_product_condition != 'all':
            lines = lines.filtered(lambda l: l.product_condition == self.filter_product_condition)

        return lines

    def _export_excel(self):
        """Export to Excel format"""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4472C4',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        title_format = workbook.add_format({
            'bold': True,
            'font_size': 14,
            'align': 'left'
        })

        cell_format = workbook.add_format({
            'border': 1,
            'align': 'left',
            'valign': 'vcenter'
        })

        cell_center_format = workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        # Status colors
        matched_format = workbook.add_format({
            'border': 1,
            'bg_color': '#C6EFCE',
            'font_color': '#006100'
        })

        mismatch_format = workbook.add_format({
            'border': 1,
            'bg_color': '#FFEB9C',
            'font_color': '#9C6500'
        })

        unmatched_format = workbook.add_format({
            'border': 1,
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006'
        })

        worksheet = workbook.add_worksheet('Stock Opname Report')

        row = 0

        # Header Information
        worksheet.write(row, 0, 'STOCK OPNAME REPORT', title_format)
        row += 2

        worksheet.write(row, 0, 'Opname Number:', cell_format)
        worksheet.write(row, 1, self.opname_id.name, cell_format)
        row += 1

        worksheet.write(row, 0, 'Warehouse:', cell_format)
        worksheet.write(row, 1, self.opname_id.warehouse_id.name, cell_format)
        row += 1

        worksheet.write(row, 0, 'Opname Date:', cell_format)
        worksheet.write(row, 1, self.opname_id.opname_date.strftime('%Y-%m-%d %H:%M:%S'), cell_format)
        row += 1

        worksheet.write(row, 0, 'Responsible:', cell_format)
        worksheet.write(row, 1, self.opname_id.responsible_id.name, cell_format)
        row += 1

        worksheet.write(row, 0, 'Status:', cell_format)
        worksheet.write(row, 1, self.opname_id.state.upper(), cell_format)
        row += 2

        # Summary Section
        if self.include_summary:
            worksheet.write(row, 0, 'SUMMARY', title_format)
            row += 1

            worksheet.write(row, 0, 'Total Scanned:', cell_format)
            worksheet.write(row, 1, self.opname_id.total_scanned, cell_format)
            row += 1

            worksheet.write(row, 0, 'Total Matched:', cell_format)
            worksheet.write(row, 1, self.opname_id.total_matched, matched_format)
            row += 1

            worksheet.write(row, 0, 'Total Status Mismatch:', cell_format)
            worksheet.write(row, 1, self.opname_id.total_status_mismatch, mismatch_format)
            row += 1

            worksheet.write(row, 0, 'Total Unmatched:', cell_format)
            worksheet.write(row, 1, self.opname_id.total_unmatched, unmatched_format)
            row += 2

        # Details Section
        if self.include_details:
            worksheet.write(row, 0, 'DETAIL ITEMS', title_format)
            row += 1

            # Column headers
            headers = ['No', 'Barcode', 'Product Code', 'Product Name', 'Warehouse',
                       'Product Condition', 'Match Status', 'System Status', 'Remarks',
                       'Receipt', 'Vendor', 'Information', 'Scanned Date']

            for col, header in enumerate(headers):
                worksheet.write(row, col, header, header_format)

            row += 1

            # Data rows
            lines = self._get_filtered_lines()
            no = 1

            for line in lines:
                # Choose format based on match status
                if line.match_status == 'matched':
                    status_format = matched_format
                elif line.match_status == 'status_mismatch':
                    status_format = mismatch_format
                else:
                    status_format = unmatched_format

                worksheet.write(row, 0, no, cell_center_format)
                worksheet.write(row, 1, line.barcode or '', cell_format)
                worksheet.write(row, 2, line.code_product or '', cell_format)
                worksheet.write(row, 3, line.product_id.name if line.product_id else '', cell_format)
                worksheet.write(row, 4, line.warehouse_id.name if line.warehouse_id else '', cell_format)
                worksheet.write(row, 5, line.product_condition or '', cell_format)
                worksheet.write(row, 6, line.match_status or '', status_format)
                worksheet.write(row, 7, line.detail_product_status or '', cell_format)
                worksheet.write(row, 8, line.match_remarks or '', cell_format)
                worksheet.write(row, 9, line.receipt_id.name if line.receipt_id else '', cell_format)
                worksheet.write(row, 10, line.vendor_id.name if line.vendor_id else '', cell_format)
                worksheet.write(row, 11, line.information or '', cell_format)
                worksheet.write(row, 12, line.scanned_date.strftime('%Y-%m-%d %H:%M:%S') if line.scanned_date else '',
                                cell_format)

                row += 1
                no += 1

        # Set column widths
        worksheet.set_column('A:A', 5)
        worksheet.set_column('B:B', 20)
        worksheet.set_column('C:C', 15)
        worksheet.set_column('D:D', 25)
        worksheet.set_column('E:E', 15)
        worksheet.set_column('F:F', 18)
        worksheet.set_column('G:G', 18)
        worksheet.set_column('H:H', 15)
        worksheet.set_column('I:I', 35)
        worksheet.set_column('J:J', 15)
        worksheet.set_column('K:K', 20)
        worksheet.set_column('L:L', 30)
        worksheet.set_column('M:M', 20)

        workbook.close()
        output.seek(0)

        # Save file
        file_name = f"Stock_Opname_{self.opname_id.name.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        self.file_data = base64.b64encode(output.read())
        self.file_name = file_name
        output.close()

    def _export_pdf(self):
        """Export to PDF format"""
        # Render template langsung tanpa report action
        template = 'product_barcode.report_stock_opname_document'

        # Prepare data for template
        docargs = {
            'docs': self.opname_id,
            'data': {
                'filter_match_status': self.filter_match_status,
                'filter_product_condition': self.filter_product_condition,
                'include_summary': self.include_summary,
                'include_details': self.include_details,
            }
        }

        # Render HTML first
        html_content = self.env['ir.qweb']._render(template, docargs)

        # Convert HTML to PDF
        pdf_content = self.env['ir.actions.report']._run_wkhtmltopdf(
            [html_content],
            landscape=False,
            specific_paperformat_args={
                'data-report-margin-top': 40,
                'data-report-header-spacing': 35
            }
        )

        file_name = f"Stock_Opname_{self.opname_id.name.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        self.file_data = base64.b64encode(pdf_content)
        self.file_name = file_name

    def action_download(self):
        """Download the generated file"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/stock.opname.export.wizard/{self.id}/file_data/{self.file_name}?download=true',
            'target': 'self',
        }