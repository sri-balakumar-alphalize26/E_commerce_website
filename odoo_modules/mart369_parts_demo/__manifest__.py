{
    'name': '369 Mart Sample Catalogue - Computer Parts',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'A shop full of computer parts, so every screen has something to show.',
    'description': """
369 Mart Sample Catalogue
=========================

A worked example of a computer parts shop: six sections, twenty-three
subcategories and ninety-two products with real brands and plausible prices,
plus a home page built around them.

It exists so the app can be looked at, demonstrated and tested against
something coherent instead of four empty categories. **It is not stock.**
Nothing here is ordered, counted or priced for sale.

While it is installed:

* the grocery categories left over from the old sample data are **hidden**,
  not deleted - untick nothing and they come straight back;
* the grocery home page that ships with the home module is **switched off**,
  so the customer sees one set of tabs rather than two.

Uninstalling puts both back and takes every sample product with it.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': ['mart369_home', 'mart369_catalog', 'mart369_product'],
    'data': [
        # Order matters: products point at categories, and the home page points
        # at both.
        'data/parts_categories.xml',
        'data/parts_products.xml',
        'data/parts_home.xml',
    ],
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
