"""The route shape every public 369 Mart feed uses.

Deliberately type='http' returning a plain JSON body, not type='json'. In
Odoo 19 type='json' is a deprecated alias for 'jsonrpc', which only accepts
POST and wraps everything in a {"jsonrpc": "2.0", "result": ...} envelope the
app would have to unwrap. A browser fetch() wants a GET and a bare object.

website=True gives the pricelist and fiscal position the price calculation
needs. It also switches on Odoo's language redirects, so multilang=False is
then required or a French browser gets a 302 to /fr/369mart/home.

Lived in mart369_home's controller until the home page stopped being the
foundation - the product page and the catalogue import it too, and a route
decorator is not something they should need a home page for.
"""

PUBLIC_JSON = {
    'type': 'http',
    'auth': 'public',
    'methods': ['GET'],
    'cors': '*',
    'csrf': False,
    'website': True,
    'multilang': False,
    'sitemap': False,
    'readonly': True,
    'save_session': False,
}

# The old name, kept so the modules that already import it keep working.
_PUBLIC_JSON = PUBLIC_JSON
