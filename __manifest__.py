# -*- coding: utf-8 -*-
{
    "name": """Importación de Libros de Compra para Chile\
    """,
    'version': '0.0.1',
    'category': 'Localization/Chile',
    'sequence': 12,
    'author':  'Konos',
    'website': 'https://konos.cl',
    'license': 'AGPL-3',
    'summary': '',
    'description': """
Importación de Libros de Compra para Chile.
""",
    'depends': [
            'l10n_cl_fe',
        ],

    'data': [
            'views/invoice_import.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
}
