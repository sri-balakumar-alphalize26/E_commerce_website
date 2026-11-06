from . import models
from . import controllers


def post_init_hook(env):
    """A fresh shop opens on a page arranged from its own catalogue.

    The grocery page in data/home_default_data.xml is still installed - as an
    example to copy from, switched off - but it is no longer what customers
    see first. See models/home_starter.py.
    """
    env['mart369.home.version'].sudo()._mart369_build_starter()
    # After the real page, so the shop always has something else to serve.
    env['mart369.home.version'].sudo()._mart369_ensure_demo()
