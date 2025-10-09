{
    'name': 'Product Barcode',
    'version': '17.0.1.0',
    'category': 'Module',
    'summary': 'Product Barcode',
    'description': """
        Product barcode by Anggit
    """,
    'website': '',
    'author': 'Anggit',
    'depends': ['web','base', 'product', 'account', 'purchase', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/stock_opname_data.xml',
        'views/stock_picking_view.xml',
        'views/stock_opname_view.xml',
        'reports/inventory_receipt_barcode_report.xml',
        'views/product_product_view.xml',
    ],
    'installable': True,
    'license': 'OEEL-1',
}