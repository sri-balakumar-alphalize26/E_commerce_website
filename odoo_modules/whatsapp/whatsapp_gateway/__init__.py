"""WhatsApp connector for Odoo, talking to an Evolution API gateway.

Two things that used to happen here no longer do, and both were hazards:

* This file used to run `pip install neonize qrcode[pil] Pillow` as a side
  effect of being imported. A module import silently installing packages into
  the running interpreter is not something a server operator can predict or
  audit, and it hid the real failure - a missing library - behind a confusing
  one. There is nothing left to install: the gateway owns the WhatsApp library.
* It used to reconnect sessions on startup by opening WhatsApp clients inside
  the Odoo process. Nothing to reconnect now; the gateway holds the connection
  and outlives Odoo restarts.
"""

from . import models
from . import controllers
from . import wizards


def _post_init_hook(env):
    """File the groups under their app for this particular Odoo 19 build."""
    _link_whatsapp_groups(env, 'whatsapp_gateway')



def _link_groups_to_app(env, module, category_xmlid, privilege_xmlid,
                        privilege_name, group_xmlids, sequence=10):
    """File this module's groups under its app, whichever shape the build uses.

    Odoo 19 changed how a group is grouped. Newer builds put a
    `res.groups.privilege` record between the group and `ir.module.category`
    and give `res.groups` a `privilege_id`; earlier ones hang `category_id`
    straight on the group and have no privilege model at all.

    Declaring either shape in the security XML makes the module installable on
    one kind of build and broken on the other: the data file fails, the groups
    are never created, and then every ACL row naming one dies with "No matching
    record found for external id" - which is a confusing way to be told the
    server is a different Odoo 19 than the module was written on.

    So the XML now creates only what every build agrees on - the category and
    the groups themselves - and the linking happens here, against whatever the
    running build actually has. A build with neither field simply keeps the
    groups ungrouped, which costs a little tidiness in the user form and
    nothing else.
    """
    Groups = env['res.groups']
    groups = Groups.browse()
    for xmlid in group_xmlids:
        record = env.ref('%s.%s' % (module, xmlid), raise_if_not_found=False)
        if record:
            groups |= record
    if not groups:
        return
    category = env.ref('%s.%s' % (module, category_xmlid),
                       raise_if_not_found=False)

    if 'privilege_id' in Groups._fields and 'res.groups.privilege' in env:
        privilege = env.ref('%s.%s' % (module, privilege_xmlid),
                            raise_if_not_found=False)
        if privilege:
            # A row left over from when this record was declared in XML. Its
            # external id is in no data file any more, so `_process_end` would
            # delete it at the very end of this same upgrade - after this code
            # has already pointed the groups at it - and they would be back to
            # filed under nothing. Marking it noupdate is what spares it.
            env['ir.model.data'].sudo().search([
                ('module', '=', module),
                ('name', '=', privilege_xmlid),
                ('model', '=', 'res.groups.privilege'),
            ]).write({'noupdate': True})
        else:
            privilege = env['res.groups.privilege'].create({
                'name': privilege_name,
                'sequence': sequence,
                'category_id': category.id if category else False,
            })
            # Registered with an external id so a later run finds it instead of
            # making a second one, and noupdate so it is never a candidate for
            # removal when the module's data files change.
            env['ir.model.data'].create({
                'module': module,
                'name': privilege_xmlid,
                'model': 'res.groups.privilege',
                'res_id': privilege.id,
                'noupdate': True,
            })
        groups.write({'privilege_id': privilege.id})
    elif 'category_id' in Groups._fields and category:
        groups.write({'category_id': category.id})


def _link_whatsapp_groups(env, module):
    _link_groups_to_app(
        env, module,
        category_xmlid='module_category_whatsapp',
        privilege_xmlid='privilege_whatsapp',
        privilege_name='WhatsApp',
        group_xmlids=('group_whatsapp_user', 'group_whatsapp_manager'),
        sequence=10,
    )
