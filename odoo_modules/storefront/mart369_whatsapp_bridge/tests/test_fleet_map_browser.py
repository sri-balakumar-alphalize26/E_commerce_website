"""The office's live map opens in a real browser and draws the rider.

Delivery > Fleet > Live Map was redrawn like the Delivery Partner app on
17 Nov 2026 (MapLibre on OpenFreeMap, the scooter turned to its heading).
This opens it in headless Chrome with one rider on duty and waits for the
rider on the map - the scooter on MapLibre, or the Leaflet marker when the
browser has no WebGL - and fails on any browser error.
"""

from odoo import fields
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestFleetMapBrowser(HttpCase):

    def test_the_live_map_draws_the_rider(self):
        self.env['sa.delivery.partner'].sudo().create({
            'name': 'Zz Map Rider', 'phone': '96890009999', 'on_duty': True,
            'last_lat': 25.2048, 'last_lng': 55.2708, 'last_fix_on': fields.Datetime.now(),
        })
        code = """
            const deadline = Date.now() + 30000;
            (function wait() {
                const scooter = document.querySelector('.sa_fm .sa_fm_rd img');
                const fallback = document.querySelector('.sa_fm .sa_fm_mk.rider');
                if (scooter || fallback) {
                    console.log(scooter ? 'drawn with MapLibre' : 'drawn with the Leaflet fallback');
                    console.log('test successful');
                    return;
                }
                if (Date.now() > deadline) {
                    console.error('the rider never appeared on the live map');
                    return;
                }
                setTimeout(wait, 250);
            })();
        """
        self.browser_js('/odoo/action-sales_automation_delivery.action_sa_fleet_map', code,
                        login='admin', timeout=90)
