from odoo import models, fields, api
from datetime import datetime


class InventoryReceiptProductDetail(models.Model):
    """
    Extend Model Inventory Receipt Product Detail
    Menambahkan field-field untuk tracking opname history
    
    Tujuan: Menyimpan informasi opname terakhir pada setiap produk
    """
    # Inherit dari model existing
    _inherit = 'inventory.receipt.product.detail'
    
    # Tanggal opname terakhir (readonly, di-update otomatis saat opname done)
    last_opname_date = fields.Datetime('Last Opname Date', readonly=True)
    # Relasi ke stock opname terakhir (readonly)
    last_opname_id = fields.Many2one('stock.opname', string='Last Opname', readonly=True)
    # Kondisi fisik terakhir saat di-opname (readonly)
    last_physical_condition = fields.Selection([
        ('good', 'Good'),
        ('damaged', 'Damaged'),
        ('missing_parts', 'Missing Parts'),
        ('defect', 'Defect'),              
        ('not_checked', 'Not Checked')     
    ], string='Last Physical Condition', default='not_checked', readonly=True)
    # Catatan dari opname terakhir (readonly)
    last_opname_notes = fields.Text('Last Opname Notes', readonly=True)
    # Counter: Berapa kali produk ini sudah di-opname (readonly)
    opname_count = fields.Integer('Opname Count', default=0, readonly=True,
                                  help='Number of times this item has been counted')

    # Relasi One2many ke history opname (untuk tracking semua history)
    opname_history_ids = fields.One2many('inventory.opname.history', 'detail_product_id',
                                         string='Opname History')


class InventoryOpnameHistory(models.Model):
    """
    Model untuk Menyimpan History Opname setiap Produk
    
    Tujuan: 
    - Tracking semua opname yang pernah dilakukan untuk satu produk
    - Audit trail kondisi produk dari waktu ke waktu
    """
    # Definisi nama internal model
    _name = 'inventory.opname.history'
    _description = 'Inventory Opname History'
    # Default ordering: opname_date descending
    _order = 'opname_date desc'
    
    # Relasi ke detail produk (required, cascade delete)
    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='Product Detail',
                                        required=True, ondelete='cascade')
    # Relasi ke stock opname (required, cascade delete)
    opname_id = fields.Many2one('stock.opname', string='Stock Opname', required=True, ondelete='cascade')
    # Tanggal opname (required)
    opname_date = fields.Datetime('Opname Date', required=True)

    # Menyimpan snapshot data produk saat opname untuk historical record
    barcode = fields.Char('Barcode')
    product_id = fields.Many2one('product.product', string='Product')
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

    # Kondisi fisik saat opname (required)
    physical_condition = fields.Selection([
        ('good', 'Good'),                 
        ('damaged', 'Damaged'),            
        ('missing_parts', 'Missing Parts'),
        ('defect', 'Defect'),              
        ('missing', 'Missing/Not Found')   
    ], string='Physical Condition', required=True)

    # Catatan opname
    notes = fields.Text('Notes')
    # User yang melakukan scan
    scanned_by = fields.Many2one('res.users', string='Scanned By')

    # Flag: Apakah produk ini di-scan atau tidak (missing)
    was_scanned = fields.Boolean('Was Scanned', default=True)
    # Status matching dengan sistem
    match_status = fields.Selection([
        ('matched', 'Matched'),            # Match dengan sistem
        ('status_mismatch', 'Status Mismatch'),  # Status tidak sesuai
        ('unmatched', 'Unmatched'),        # Tidak ada di sistem
        ('missing', 'Missing')             # Expected tapi tidak ditemukan
    ], string='Match Status')


class StockOpname(models.Model):
    """
    Model untuk Stock Opname (Physical Inventory Count)
    
    Tujuan:
    - Mengelola proses stock opname
    - Membandingkan data sistem dengan physical count
    - Update data produk berdasarkan hasil opname
    
    Flow:
    1. Create opname -> auto-generate expected lines dari sistem
    2. Scan barcode -> create scanned lines
    3. Submit -> compare expected vs scanned, update product details
    """

    _name = 'stock.opname'
    _description = 'Stock Opname'
    _rec_name = 'name'
    _order = 'create_date desc'
    
    # Nomor opname (auto-generated dari sequence)
    name = fields.Char('Opname Number', required=True, copy=False, readonly=True, default='New')
    # Tanggal opname (default: sekarang, required)
    opname_date = fields.Datetime('Opname Date', default=fields.Datetime.now, required=True)
    # Warehouse yang di-opname (required)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', required=True)
    # User yang bertanggung jawab (default: current user)
    responsible_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    # Status workflow opname
    state = fields.Selection([
        ('draft', 'Draft'),              
        ('in_progress', 'In Progress'),  
        ('done', 'Done'),                
        ('cancel', 'Cancelled')          
    ], string='Status', default='draft', required=True)
    # Catatan opname
    notes = fields.Text('Notes')

    # One2many ke expected lines (produk yang seharusnya ada berdasarkan sistem)
    expected_line_ids = fields.One2many('stock.opname.expected.line', 'opname_id', string='Expected Items (System)')

    # One2many ke scanned lines (produk yang benar-benar di-scan)
    line_ids = fields.One2many('stock.opname.line', 'opname_id', string='Scanned Items (Physical)')

    # Total produk yang di-scan
    total_scanned = fields.Integer('Total Scanned', compute='_compute_totals', store=True)
    # Total yang match dengan sistem
    total_matched = fields.Integer('Total Matched', compute='_compute_totals', store=True)
    # Total yang tidak match
    total_unmatched = fields.Integer('Total Unmatched', compute='_compute_totals', store=True)
    # Total yang status mismatch (ada di sistem tapi status berbeda)
    total_status_mismatch = fields.Integer('Status Mismatch', compute='_compute_totals', store=True)
    # Total expected dari sistem
    total_expected = fields.Integer('Total Expected', compute='_compute_expected_total', store=True)

    @api.depends('line_ids', 'line_ids.match_status')
    def _compute_totals(self):
        """
        Compute statistik dari scanned lines
        
        Trigger: Ketika line_ids berubah atau match_status berubah
        """
        for rec in self:
            rec.total_scanned = len(rec.line_ids)
            rec.total_matched = len(rec.line_ids.filtered(lambda l: l.match_status == 'matched'))
            rec.total_unmatched = len(rec.line_ids.filtered(lambda l: l.match_status == 'unmatched'))
            rec.total_status_mismatch = len(rec.line_ids.filtered(lambda l: l.match_status == 'status_mismatch'))

    @api.depends('expected_line_ids')
    def _compute_expected_total(self):
        """
        Compute total expected items
        
        Trigger: Ketika expected_line_ids berubah
        """
        for rec in self:
            rec.total_expected = len(rec.expected_line_ids)
    
    @api.model
    def create(self, vals):
        """
        Override create untuk:
        1. Generate nomor opname dari sequence
        2. Auto-generate expected lines dari sistem
        """
        # Generate opname number jika masih 'New'
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.opname') or 'New'

        record = super().create(vals)

        # Auto-generate expected lines jika warehouse sudah di-set
        if record.warehouse_id:
            record._generate_expected_lines()

        return record

    def write(self, vals):
        """
        Override write untuk:
        Regenerate expected lines jika warehouse berubah (dan masih draft)
        """
        res = super().write(vals)

        # Jika warehouse berubah dan state masih draft
        if 'warehouse_id' in vals and vals['warehouse_id']:
            for rec in self:
                if rec.state == 'draft':
                    # Regenerate expected lines
                    rec._generate_expected_lines()

        return res

    def _generate_expected_lines(self):
        """
        Generate expected lines dari data sistem
        
        Flow:
        1. Clear existing expected lines
        2. Get semua produk available di warehouse
        3. Create expected line untuk setiap produk
        4. Include data opname terakhir jika ada
        
        Tujuan: Membuat daftar produk yang seharusnya ada berdasarkan sistem
        """
        self.ensure_one()

        self.expected_line_ids.unlink()

        # Get semua available products di warehouse ini
        expected_products = self.env['inventory.receipt.product.detail'].search([
            ('warehouse_id', '=', self.warehouse_id.id),
            ('status_product', '=', 'available')  # Hanya yang available
        ])

        expected_lines = []  # List untuk create expected lines
        
        for detail in expected_products:
            # Cek apakah sudah pernah di-opname sebelumnya
            if detail.last_opname_date:
                # Jika sudah pernah, gunakan data opname terakhir
                condition = detail.last_physical_condition if detail.last_physical_condition != 'not_checked' else 'N/A'
                information = detail.last_opname_notes or 'N/A'
                remarks = f"Last checked: {detail.last_opname_date.strftime('%Y-%m-%d')} - {detail.last_opname_notes or 'No issues'}"
                last_updated = detail.last_opname_date
            else:
                # Jika belum pernah, gunakan default values
                condition = 'N/A'
                information = 'N/A'
                remarks = 'Never checked before'
                last_updated = detail.write_date or detail.create_date

            # Append data untuk create expected line
            expected_lines.append({
                'opname_id': self.id,                          
                'barcode': detail.barcode,                     
                'code_product': detail.code_product,           
                'product_id': detail.product_id.id,            
                'warehouse_id': detail.warehouse_id.id,        
                'receipt_id': detail.receipt_id.id if detail.receipt_id else False,  
                'vendor_id': detail.vendor_id.id if detail.vendor_id else False,     
                'vendor_code': detail.vendor_code,             
                'system_status': detail.status_product,        
                'product_condition': condition,                
                'information': information,                    
                'match_remarks': remarks,                      
                'last_updated': last_updated,                  
                'detail_product_id': detail.id,                
            })

        # Bulk create expected lines
        self.env['stock.opname.expected.line'].create(expected_lines)

    def action_start_opname(self):
        """
        Action: Start opname process (draft -> in_progress)
        
        Tujuan: Mulai proses scan barcode
        """
        self.write({'state': 'in_progress'})

    def action_done(self):
        """
        Action: Finalize opname (in_progress -> done)
        
        Flow:
        1. Update state menjadi done
        2. Update stock quantities berdasarkan hasil opname
        3. Update expected lines dengan scanned data
        
        Tujuan: Finalisasi opname dan update data produk
        """
        self.write({'state': 'done'})

        # Update stock dan product details berdasarkan opname result
        self._update_stock_from_opname()

        # Update expected lines dengan scanned information
        self._update_expected_with_scanned_data()

    def _update_stock_from_opname(self):
        """
        Update inventory.receipt.product.detail berdasarkan hasil opname
        
        Flow untuk setiap scanned item:
        1. Update last_opname_date, last_opname_id, dll
        2. Increment opname_count
        3. Create opname history record
        
        Flow untuk expected tapi tidak di-scan:
        1. Mark sebagai not_checked
        2. Create history record dengan status missing
        
        Tujuan: Update master data produk berdasarkan physical count
        """
        history_records = []  # List untuk bulk create history

        for line in self.line_ids:
            # Hanya process yang matched dan ada detail_product_id
            if line.match_status == 'matched' and line.detail_product_id:
                # Update detail product dengan informasi dari physical count
                line.detail_product_id.write({
                    'last_opname_date': self.opname_date,              
                    'last_opname_id': self.id,                         
                    'last_physical_condition': line.product_condition, 
                    'last_opname_notes': line.information or 'Scanned and verified',  
                    'opname_count': line.detail_product_id.opname_count + 1,  
                })

                history_records.append({
                    'detail_product_id': line.detail_product_id.id,
                    'opname_id': self.id,
                    'opname_date': self.opname_date,
                    'barcode': line.barcode,
                    'product_id': line.product_id.id,
                    'warehouse_id': line.warehouse_id.id,
                    'physical_condition': line.product_condition,
                    'notes': line.information,
                    'scanned_by': self.responsible_id.id,
                    'was_scanned': True,                    
                    'match_status': line.match_status,
                })

        # Handle missing items (expected tapi tidak di-scan)
        for expected_line in self.expected_line_ids.filtered(lambda e: not e.is_scanned):
            if expected_line.detail_product_id:
                # Update sebagai not found
                expected_line.detail_product_id.write({
                    'last_opname_date': self.opname_date,
                    'last_opname_id': self.id,
                    'last_physical_condition': 'not_checked',
                    'last_opname_notes': 'Item not found during physical count',
                    'opname_count': expected_line.detail_product_id.opname_count + 1,
                })

                history_records.append({
                    'detail_product_id': expected_line.detail_product_id.id,
                    'opname_id': self.id,
                    'opname_date': self.opname_date,
                    'barcode': expected_line.barcode,
                    'product_id': expected_line.product_id.id,
                    'warehouse_id': expected_line.warehouse_id.id,
                    'physical_condition': 'missing',
                    'notes': 'Item expected but not found during physical count',
                    'scanned_by': self.responsible_id.id,
                    'was_scanned': False,               
                    'match_status': 'missing',
                })

        if history_records:
            self.env['inventory.opname.history'].create(history_records)

    def _update_expected_with_scanned_data(self):
        """
        Update expected lines dengan actual scanned data
        
        Tujuan: Update data expected untuk referensi opname berikutnya
        """
        for expected_line in self.expected_line_ids:
            if expected_line.is_scanned:
                # Cari scanned line yang match berdasarkan barcode
                scanned_line = self.line_ids.filtered(lambda l: l.barcode == expected_line.barcode)
                if scanned_line:
                    scanned_line = scanned_line[0]  # Ambil record pertama

                    # Update expected line dengan scanned data
                    expected_line.write({
                        'product_condition': scanned_line.product_condition,  
                        'information': scanned_line.information or 'Scanned OK',  
                        'match_remarks': scanned_line.match_remarks,         
                        'last_updated': scanned_line.scanned_date,           
                    })

    def action_cancel(self):
        """
        Action: Cancel opname
        """
        self.write({'state': 'cancel'})

    def action_reset_to_draft(self):
        """
        Action: Reset ke draft (dari done/cancel)
        """
        self.write({'state': 'draft'})

    def action_open_export_wizard(self):
        """
        Action: Open export wizard untuk export ke Excel/PDF
        
        Return: Action untuk open wizard
        """
        return {
            'type': 'ir.actions.act_window',
            'name': 'Export Stock Opname',
            'res_model': 'stock.opname.export.wizard',
            'view_mode': 'form',
            'target': 'new',                    
            'context': {
                'default_opname_id': self.id,   
            }
        }


class StockOpnameExpectedLine(models.Model):
    """
    Model untuk Expected Line (Data Sistem)
    
    Tujuan: Menyimpan daftar produk yang seharusnya ada berdasarkan sistem
    """
    _name = 'stock.opname.expected.line'
    _description = 'Stock Opname Expected Line (System Data)'
    _rec_name = 'barcode'
    _order = 'code_product'
    
    # Relasi ke opname header (required, cascade delete)
    opname_id = fields.Many2one('stock.opname', string='Stock Opname', required=True, ondelete='cascade')
    # Barcode produk (required)
    barcode = fields.Char('Barcode', required=True)
    # Kode produk
    code_product = fields.Char('Product Code')
    # Relasi ke master product
    product_id = fields.Many2one('product.product', string='Product')
    # Warehouse
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    # Receipt
    receipt_id = fields.Many2one('stock.picking', string='Receipt')
    # Vendor
    vendor_id = fields.Many2one('res.partner', string='Vendor')
    # Kode vendor
    vendor_code = fields.Char('Vendor Code')

    # Status di sistem
    system_status = fields.Selection([
        ('waiting', 'Waiting'),
        ('available', 'Available'),
        ('sold', 'Sold')
    ], string='System Status')

    # Kondisi produk terakhir (default: N/A)
    product_condition = fields.Char('Condition', default='N/A')
    # Informasi tambahan (default: N/A)
    information = fields.Text('Information', default='N/A')
    # Remarks matching (default: Expected from system)
    match_remarks = fields.Text('Remarks', default='Expected from system')
    # Last updated timestamp (readonly)
    last_updated = fields.Datetime('Last Updated', readonly=True)

    # Link ke detail produk di sistem
    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='Detail Product')

    # Flag: Apakah produk ini sudah di-scan
    is_scanned = fields.Boolean('Scanned', compute='_compute_is_scanned', store=True)

    @api.depends('opname_id.line_ids', 'opname_id.line_ids.barcode', 'barcode')
    def _compute_is_scanned(self):
        """
        Compute apakah expected line ini sudah di-scan
        
        Trigger: Ketika scanned lines berubah atau barcode berubah
        Logika: Check apakah ada scanned line dengan barcode yang sama
        """
        for rec in self:
            # Cari scanned line dengan barcode yang sama
            rec.is_scanned = bool(rec.opname_id.line_ids.filtered(lambda l: l.barcode == rec.barcode))


class StockOpnameLine(models.Model):
    """
    Model untuk Scanned Line (Data Physical Count)
    
    Tujuan: Menyimpan hasil physical count (barcode yang di-scan)
    """
    _name = 'stock.opname.line'
    _description = 'Stock Opname Line'
    _rec_name = 'barcode'

    # Relasi ke opname header (required, cascade delete)
    opname_id = fields.Many2one('stock.opname', string='Stock Opname', required=True, ondelete='cascade')
    # Barcode yang di-scan (required)
    barcode = fields.Char('Barcode', required=True)
    # Kode produk (auto-filled dari matching)
    code_product = fields.Char('Product Code')
    # Product (auto-filled dari matching)
    product_id = fields.Many2one('product.product', string='Product')
    # Warehouse (auto-filled dari matching)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')

    # Kondisi fisik produk saat di-scan (required)
    product_condition = fields.Selection([
        ('good', 'Good'),                  
        ('damaged', 'Damaged'),            
        ('missing_parts', 'Missing Parts'),
        ('defect', 'Defect')               
    ], string='Product Condition', default='good', required=True)

    # Informasi tambahan saat scan
    information = fields.Text('Information')
    # Tanggal scan (default: sekarang)
    scanned_date = fields.Datetime('Scanned Date', default=fields.Datetime.now)

    # Status matching dengan sistem (readonly, auto-computed saat create)
    match_status = fields.Selection([
        ('matched', 'Matched'),                    # Match: ada di sistem dan available
        ('unmatched', 'Unmatched'),                # Unmatched: tidak ada di sistem
        ('status_mismatch', 'Status Mismatch')     # Mismatch: ada di sistem tapi status beda
    ], string='Match Status', readonly=True)

    match_remarks = fields.Text('Match Remarks', readonly=True)

    # Link ke detail produk (readonly, auto-filled saat create)
    detail_product_id = fields.Many2one('inventory.receipt.product.detail', string='Detail Product', readonly=True)
    # Status produk di sistem (readonly, auto-filled saat create)
    detail_product_status = fields.Selection([
        ('waiting', 'Waiting'),
        ('available', 'Available'),
        ('sold', 'Sold')
    ], string='System Status', readonly=True)

    # Related fields untuk display
    receipt_id = fields.Many2one('stock.picking', string='Receipt', related='detail_product_id.receipt_id', store=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', related='detail_product_id.vendor_id', store=True)

    @api.model
    def create(self, vals):
        """
        Override create untuk:
        1. Auto-match barcode dengan inventory.receipt.product.detail
        2. Validasi status produk
        3. Set match_status dan match_remarks
        
        Matching Logic:
        - Matched: Barcode ditemukan dan status = available
        - Status Mismatch: Barcode ditemukan tapi status bukan available
        - Unmatched: Barcode tidak ditemukan di sistem
        """
        if vals.get('barcode'):
            # Search detail produk berdasarkan barcode
            detail = self.env['inventory.receipt.product.detail'].sudo().search([
                ('barcode', '=', vals['barcode'])
            ], limit=1)

            if detail:
                # Barcode ditemukan - fill data dari detail
                vals['detail_product_id'] = detail.id
                vals['code_product'] = detail.code_product
                vals['product_id'] = detail.product_id.id
                vals['warehouse_id'] = detail.warehouse_id.id
                vals['detail_product_status'] = detail.status_product

                # Validasi status produk dan set match_status
                if detail.status_product == 'available':
                    # Status available = MATCHED
                    vals['match_status'] = 'matched'
                    vals['match_remarks'] = 'Product found and status is available'
                    
                elif detail.status_product == 'waiting':
                    # Status waiting = STATUS MISMATCH
                    vals['match_status'] = 'status_mismatch'
                    vals['match_remarks'] = 'Product found but status is WAITING (not yet available in system)'
                    
                elif detail.status_product == 'sold':
                    # Status sold = STATUS MISMATCH (seharusnya tidak ada di warehouse)
                    vals['match_status'] = 'status_mismatch'
                    vals['match_remarks'] = 'Product found but status is SOLD (already sold, should not be in warehouse)'
                    
                else:
                    # Status lainnya = STATUS MISMATCH
                    vals['match_status'] = 'status_mismatch'
                    vals['match_remarks'] = f'Product found but status is {detail.status_product}'
            else:
                # Barcode tidak ditemukan = UNMATCHED
                vals['match_status'] = 'unmatched'
                vals['match_remarks'] = 'Barcode not found in system'

        return super().create(vals)