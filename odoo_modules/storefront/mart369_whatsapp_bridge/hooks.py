"""Widen the backend board's action to both channels - and put it back.

The act_window's domain is a stored string on another module's record.
Written from a hook rather than a data record, because a data record's write
would survive uninstalling this module - and then the board would filter on
a field that no longer exists.

Installing also copies the pictures added by hand to the Confirmation pictures
and Variant images tabs into Photographs: those tabs now draw Photographs, and
they would otherwise drop out of sight.
"""
import logging

_logger = logging.getLogger(__name__)

WIDE = ("['|', ('mart369_ref', '!=', False), "
        "('mart369_channel', '=', 'whatsapp'), "
        "('mart369_state', 'not in', (False, 'draft'))]")
NARROW = ("[('mart369_ref', '!=', False), "
          "('mart369_state', 'not in', (False, 'draft'))]")
# Set on a Confirmation picture once it is in Photographs, so a reinstall
# does not copy it twice. What a past internet search saved is left alone.
COPIED = 'photographs'


def copy_confirmation_pictures(env):
    """The product's card picture if it has none, else its gallery. The original
    stays, marked as copied."""
    pictures = env['sa.confirm.picture'].sudo().search([
        ('product_tmpl_id', '!=', False),
        ('source', 'not in', ('internet', COPIED)),
    ], order='sequence, id')
    for picture in pictures.filtered('image'):
        product = picture.product_tmpl_id
        try:
            with env.cr.savepoint():
                if product.image_1920:
                    env['product.image'].sudo().create({
                        'name': product.name,
                        'product_tmpl_id': product.id,
                        'image_1920': picture.image,
                    })
                else:
                    product.sudo().image_1920 = picture.image
                picture.source = COPIED
        except Exception as err:  # noqa: BLE001 - one bad picture never stops the install
            _logger.warning("369 Mart bridge: confirmation picture %s not copied: %s", picture.id, err)


def copy_variant_pictures(env):
    """A variant's Variant images tab into its Extra Variant Media, in order. The
    original stays, marked as copied; the WhatsApp page no longer shows those."""
    pictures = env['sa.confirm.picture'].sudo().search([
        ('product_id', '!=', False),
        ('source', 'not in', ('internet', COPIED)),
    ], order='product_id, sequence, id')
    for picture in pictures.filtered('image'):
        try:
            with env.cr.savepoint():
                env['product.image'].sudo().create({
                    'name': picture.name or picture.product_id.name,
                    'product_variant_id': picture.product_id.id,
                    'sequence': picture.sequence,
                    'image_1920': picture.image,
                })
                picture.source = COPIED
        except Exception as err:  # noqa: BLE001 - one bad picture never stops the install
            _logger.warning("369 Mart bridge: variant picture %s not copied: %s", picture.id, err)


def post_init_hook(env):
    action = env.ref('mart369_order.action_mart369_orders',
                     raise_if_not_found=False)
    if action:
        action.domain = WIDE
    copy_confirmation_pictures(env)
    copy_variant_pictures(env)


def uninstall_hook(env):
    action = env.ref('mart369_order.action_mart369_orders',
                     raise_if_not_found=False)
    if action:
        action.domain = NARROW
