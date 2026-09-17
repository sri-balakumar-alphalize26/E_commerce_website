# 369 Mart Delivery Addresses (`mart369_address`)

Customers keep several delivery addresses. The app asks the phone for its
location, turns that into an area, city, state and pincode, and the customer
fills in the rest — flat, name, mobile, and whether it is Home or Work.

An address is an ordinary Odoo **delivery contact under the customer**, so sale
orders, delivery and invoicing all understand it. No new model.

## For staff

**369 Mart → Customers & Addresses** is the screen to use: every customer, their
addresses folded underneath, and anything incomplete — no mobile, no pincode, no
map location — marked in red so it is visible without opening a record. Search
by name, email, mobile or city, filter, and export what is on screen to CSV.

**369 Mart → Addresses** is the plain list and kanban, for Odoo's own grouping
and filtering.

## The API

Called by the storefront's own server, not the browser. All `auth='user'`
except geocoding.

| Route | Does |
|---|---|
| `GET /369mart/addresses` | the customer's addresses, which is selected, and what the phone field should show |
| `POST /369mart/addresses` | add one; the first becomes the default |
| `PATCH /369mart/addresses/<id>` | change one |
| `DELETE /369mart/addresses/<id>` | archive one (past orders keep theirs) |
| `POST /369mart/addresses/<id>/default` | choose the delivery address |
| `POST /369mart/geocode/reverse` | `{lat, lng}` → area, city, state, pincode |

A customer can only ever reach their own addresses: every route resolves the id
through one helper that requires the address to hang off their partner, and
answers 404 otherwise.

## Mobile numbers

The rule is not written down anywhere — it follows the country Odoo has, via
Google's libphonenumber. India means +91, ten digits, starting 6-9; Oman means
+968 and eight digits. A landline is refused even where it is a "valid" number.

The helper lives in `mart369_auth` (`res.partner._mart369_check_mobile`), because
signup collects a mobile too.

## Geocoding

Odoo's own `base_geolocalize` calling OpenStreetMap Nominatim — **no API key and
no billing**. Nominatim asks for about one request a second, so answers are
cached per rounded coordinate. Odoo blocks these calls inside tests, so the test
stubs the reply and checks the mapping.

## Tests

`odoo-bin -d <db> --test-enable --test-tags=/mart369_address --stop-after-init`
