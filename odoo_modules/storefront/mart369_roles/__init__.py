from . import controllers
from . import models


def _mart369_give_roles(env):
    """Give today's staff a role, so installing this changes nobody's access.

    - An Odoo Administrator becomes **Owner** (Owner is Administrator too).
    - Anyone else internal with the website designer right - the old staff
      check - becomes **Manager**.
    Also run on upgrade (migrations/), because a hook only runs on install.
    """
    owner = env.ref('mart369_roles.group_owner')
    manager = env.ref('mart369_roles.group_manager')
    admins = env.ref('base.group_system').all_user_ids.filtered(lambda u: not u.share)
    new_owners = admins - owner.all_user_ids
    if new_owners:
        owner.write({'user_ids': [(4, u.id) for u in new_owners]})
    designer = env.ref('website.group_website_designer', raise_if_not_found=False)
    if designer:
        staff = (designer.all_user_ids.filtered(lambda u: not u.share)
                 - owner.all_user_ids - manager.all_user_ids)
        if staff:
            manager.write({'user_ids': [(4, u.id) for u in staff]})


def post_init_hook(env):
    _mart369_give_roles(env)
