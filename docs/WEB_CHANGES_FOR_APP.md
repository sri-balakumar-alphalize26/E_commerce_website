# Website changes to copy into the customer app

This is a running log of changes made to the 369 Mart **website** that the **customer app** (`C:\Projects\APK's\E commerce`) should get too. Add a new entry at the bottom every time the website changes something a customer sees. Each entry has four parts:

1. **For the customer**: what is different, in plain words.
2. **Files touched**: on the website and in Odoo.
3. **API**: the routes and fields used, exactly as the app will call them.
4. **What the app must copy**: the behaviour to reproduce, step by step.

How the app reaches Odoo: the website's server calls `<ODOO_URL>/369mart/...` with the customer's Odoo session cookie (`session_id`) and `X-Odoo-Database`. The browser calls the website's proxy at `/api/mart/...`, which forwards to `/369mart/...` unchanged. The app can call the `/369mart/...` routes directly with the same session. Every route below is signed-in only (`auth='user'`). Someone else's order, or an order number that doesn't exist, answers **404**.

---

## 1. Live tracking on the order page, and the real rider's name (2026-10-07)

### For the customer

- While a rider is bringing the order, the order page shows a **Live tracking** card with:
  - a real map with the rider's position, the customer's home and the shop
  - a line between them
  - the status ("Out for delivery") and the promised time
  - "Updated 8s ago"
- If the rider's phone hasn't reported for 2 minutes, the card says **"Signal lost — showing last known spot"**. The rider's dot turns grey.
- Once the promised time has passed, the card says "Running late — was due by …" instead of "Arriving by …".
- **The rider's real name** is shown everywhere: the rider card, the map, the rating card's tip line and the help chat. It is the name on the rider's record in the delivery system. Until a rider has accepted the job, or if the record's name is a placeholder like "rider", the page says **"Your rider"**. It never invents a name. (It used to pick one of four made-up names from the order number.)
- A **Call** button (`tel:`) dials the rider while they are on the way. It is hidden once the order is delivered or the job ends.
- The help chat on the order page answers "Who is my rider?". The main support chatbot (Mitra) answers "who is my rider / delivery boy / delivery person". "Delivery person" used to go to a human agent by mistake. "Track my order" now adds "Your rider is …".
- The drawn (fake) map no longer shows a made-up rider dot or an invented "2.4 km away". It is only shown before a rider has the parcel.

### Files touched

**Website**
- `components/home/LiveTrackCard.jsx` (new): the map card
- `components/home/mapProvider.js` (new): the tiles (OpenStreetMap) and where Google Maps will go
- `components/home/OrderTrack.jsx`: polls the track route, shows the card and the rider card, help-chat rider answer
- `components/home/orderState.js`: the fake `RIDERS` / `riderFor()` were removed; added `riderName(order, track)` and `riderFirst(name)`
- `components/home/track.css`: `.ot-live*` and `.ot-lm*` styles
- `package.json`: added `leaflet`
- `tests/e2e/track.spec.js` (new): screenshots in `docs/screenshots/live-tracking-*.png`

**Odoo** (`odoo_modules/mart369_whatsapp_bridge`, version stays 19.0.1.3.0; needs `-u mart369_whatsapp_bridge`)
- `controllers/order_track.py` (new): the route
- `models/sale_order_track.py` (new): the payload, the rider name rules, and `rider` on the order JSON
- `models/bot_rider.py` (new) and `data/bot_rules_rider.xml` (new): the chatbot's rider answer
- `tests/test_order_track.py` (new): 16 tests

### API

**`GET /369mart/orders/<ref>/track`**. On the website this is `GET /api/mart/orders/<ref>/track`. `<ref>` is the order's `id` from the orders list, e.g. `369M-2609302111`.

```json
{
  "ok": true,
  "track": {
    "picking_id": 8299,
    "state": "out_for_delivery",
    "label": "Out for Delivery",
    "live": true,
    "ended": false,
    "show_rider": true,
    "lat": 10.35162, "lng": 77.975632,
    "fix_on": "2026-09-30T15:48:19Z",
    "age": 312,
    "stale": true,
    "eta": "2026-09-30T19:31:08Z",
    "eta_text": "Arriving in 10-20 mins",
    "dest": { "lat": 10.35162, "lng": 77.975632 },
    "shop": { "lat": 10.36201, "lng": 77.97389, "name": "Test Counter" },
    "route": null,
    "route_approx": true,
    "rider": { "name": "Bala", "phone": "+96891234567" }
  }
}
```

`track` is `null` when the order has no delivery job yet. That is not an error; show the normal order screen.

| Field | Meaning |
|---|---|
| `state` | The delivery job's stage: `to_assign`, `awaiting_shop`, `preparing`, `ready`, `offered`, `accepted`, `picked`, `dispatched`, `out_for_delivery`, `delivered`, `returning`, `returned`, `cancelled` or `failed`. |
| `label` | The stage in words, ready to show. |
| `live` | `true` while a rider is moving the parcel (`accepted`, `picked`, `dispatched` or `out_for_delivery`). **Show the live card only when `live` is true and `ended` is false.** |
| `ended` | `true` once there is nothing left to follow. **Stop polling.** |
| `show_rider` | Whether the rider's dot may be drawn. The server decides; on the newer delivery stack, Express hides the rider between stops. |
| `lat`, `lng` | The rider's last position. `0` when hidden or when the job is over. |
| `fix_on` | When that position was taken (UTC, ISO-8601). |
| `age` | That position's age in seconds when the server answered. Add the time since the response arrived to show "Updated Xs ago". |
| `stale` | `true` when the last position is more than 120 s old. Show "Signal lost". |
| `eta` | The promised time (UTC, ISO-8601), or `""`. If it has passed, say "running late", not "arriving by". |
| `eta_text` | The order's own wording ("Arriving in 10-20 mins"). Use it when `eta` is empty. |
| `dest` | The delivery address's map point, or `null`. If `null`, use `address.lat` / `address.lng` from the order. |
| `shop` | The shop's map point and name, or `null`. |
| `route` | A list of `[lat, lng]` points along the roads, or `null`. When `null`, draw a dashed straight line and say it is approximate. |
| `route_approx` | `true` when the line is not the real road. |
| `rider.name` | The real name, or `""`. Show **"Your rider"** when it is empty. |
| `rider.phone` | `+` and digits, only while `live`, otherwise `""`. For the Call button. |

The secret WhatsApp tracking token (`sa_track_token`) and its link (`/wa/track/...`) are **never** sent. Don't try to get them; this route replaces them.

**`GET /369mart/orders` and `GET /369mart/orders/<ref>`**: each order now has

| Field | Meaning |
|---|---|
| `rider` | `{ "name": "Bala" }` once a rider has accepted the job, otherwise `null`. Same name rules as above. Use it for "Delivered by Bala" and the tip line after the live tracking has ended. |

**The chatbot** is server-side (`mart369.bot`). If the app uses the same bot route, it gets the rider answer with no change. A new rule kind, `rider` (sequence 35), matches `rider`, `driver`, `delivery boy/guy/man/person/partner/executive/agent` and `who … deliver`.

### What the app must copy

1. **Poll the track route on the order screen** while the order is not `delivered` or `cancelled`:
   - every **6 s** while `track.live` is true
   - every **20 s** before that, while the parcel is still at the shop
   - stop when `track.ended` is true, then re-read the order so the screen moves on to "Delivered"
   - pause while the app is in the background
2. **Draw the live card only when `live && !ended`:**
   - the rider's dot only when `show_rider` is true and `lat`/`lng` are not 0
   - the home pin from `dest` (or the order's `address.lat`/`lng`)
   - the shop pin from `shop`
   - the line from `route`, or else a dashed straight line from rider (or shop) to home, labelled "approximate"
   - zoom so the shop, the rider and home all fit
3. **Status line:**
   - `label`
   - "Arriving by <time of `eta`>", or "Running late — was due by …" once it has passed, or else `eta_text`
   - "Updated Xs ago", counting up between polls (`age` + seconds since the response)
4. **Signal lost:** when `stale` is true, or the counted age passes 120 s, show "Signal lost — showing last known spot" and grey the rider's dot.
5. **Rider name everywhere:**
   - use `track.rider.name`, falling back to `order.rider.name`, falling back to **"Your rider"**
   - never show a made-up name, a login or an email
   - the app must not keep its own list of riders
6. **Call button:** only when `track.rider.phone` is not empty, which the server allows only while `live`. Dial with `tel:`.
7. **Help on the order screen:** "Who is my rider?" answers:
   - "<name> is delivering your order — <label>."
   - "<name> delivered this order." once it has been delivered
   - "A rider hasn't been assigned yet." when there is no name
8. **Map tiles:** the website uses OpenStreetMap through Leaflet, with "© OpenStreetMap" shown as OSM's terms require. Google Maps is planned once the shop's key exists. When it does, both the website (`components/home/mapProvider.js`) and the app should switch together.

---

## 2. The same real map before the rider sets off and after delivery (2026-10-07)

Made by session 369mart-7e at the user's request: "show the same map as WhatsApp's tracking link". It builds on entry 1.

### For the customer

- The order page shows the **real map** (home, shop, and the rider while moving) whenever there is a real place to put on it, not only while the rider is moving. That matches the map WhatsApp's tracking link opens.
- **Before the rider sets off:** the map shows home and shop, the status label and the promised time, and the note "Your rider shows here once they set off." There is no "Live" dot.
- **While moving:** unchanged from entry 1 ("Live · Out for delivery", the rider's dot, "Updated Xs ago", "Signal lost", the approximate-line hint).
- **After delivery:** the map stays, with home and shop, the label "Delivered" and the note "Delivered to your door." There is no rider dot, no arrival time and no approximate-line hint.
- The drawn picture map is now only a fallback, for an order with no delivery job or with no coordinates at all.

### Files touched

- `components/home/OrderTrack.jsx`
  - the track route is read for every order except cancelled ones
  - a delivered order is read once, with no polling
  - the card shows when there is a real point: `track.dest`, `order.address.lat/lng`, `track.shop`, or the rider while `show_rider`
- `components/home/LiveTrackCard.jsx`: "Live ·" only while moving, the before and after notes, no arrival time once ended, and the approximate hint only while moving.

No change to the API. It uses the same `GET /369mart/orders/<ref>/track` fields as entry 1. The server already blanks the rider's position and phone once the delivery isn't live.

### What the app must copy

1. Call the track route for every order that isn't cancelled:
   - poll it as in entry 1 while the order isn't delivered
   - read it **once** for a delivered order
2. Draw the real map whenever any of `dest`, the order's address, `shop`, or (while `show_rider`) the rider has coordinates. Fall back to the app's own illustration only when none do.
3. **Words by phase:**
   - before moving (`live` false, `ended` false): the label plus "Your rider shows here once they set off."
   - moving: as in entry 1
   - ended and `state` is `delivered`: "Delivered to your door.", with no arrival time
4. Show "Live ·" and the approximate-line hint only while moving (`live && !ended`).

### Also in this round (Odoo only, nothing for the app to copy)

`mart369_whatsapp_bridge` is now 19.0.1.3.1:
- A WhatsApp address is copied into the customer's address book by matching its words and PIN, not the exact text. A PIN typed inside the street is stripped out.
- A migration (`_mart369_book_tidy`) archives old duplicate WhatsApp addresses. Old orders keep the address they went to.

---

## 3. No "Demo" account, no demo shop: sign in again, a home page from the real catalogue, services not listed (2026-10-07)

### For the customer

- **No more "Demo" account.** If the shop no longer accepts a customer's sign-in (expired, or reset on the server), the account, checkout, order and tracking pages send them to sign-in, with "You were signed out. Please sign in again." Before, the account page quietly showed a made-up person, "Demo" / "abc".
- **The sign-in link works behind the live server.** A signed-out visitor who opens an account page is sent to `/login` on the same site. Before, they were sent to the server's internal address (`https://localhost:3002/login`), which never opened.
- **A brief server outage doesn't sign anyone out.** If the shop can't be reached, the sign-in is kept.
- **The home page comes from the shop's own catalogue.** Tabs, banners, tiles and product rows are its biggest categories (on Dubai: laptop keyboards, toner, laptop batteries, CCTV, laptops). It used to be the grocery example page ("Fruits picked this morning").
- **No sample content:**
  - no sample categories (Fresh Fruits, Daily Essentials) in the category list
  - no sample notices ("Weekend grocery sale is live", "Deliveries are running late today [demo]")
  - no sample deals
- **Service items aren't listed.** Gift Card, Top-up eWallet and repair charges no longer appear in product rows, category lists, search or offers. They still work when bought (e.g. a wallet top-up).

### Files touched

**Website**
- `middleware.js`: relative redirect to `/login?next=…`
- `app/api/auth/me/route.js`: 503 (not 401) when Odoo is unreachable; the cookie is kept
- `components/home/Home.jsx`: on 401 or a `369mart:signedout` event, pages that need an account go to `/login?again=1&next=…`
- `components/home/Account.jsx`: the "Demo" default is removed; "Checking your account…" shows while loading
- `app/login/page.jsx`, `app/globals.css`: the "signed out" message
- `components/admin/HomeSection.jsx`: an "Arrange from my catalogue" button

**Odoo**
- **`mart369`:** `product.template._mart369_listed_domain()` (published, not a service)
- **`mart369_home`:**
  - `models/home_starter.py` (the automatic layout)
  - `__init__.py` `post_init_hook`
  - `POST /369mart/admin/home/pages/starter`
  - a "Rebuild from my catalogue" button
  - migration 19.0.1.5.0 (replaces the untouched grocery page)
- **`mart369_catalog`:** listing queries use the rule; the 5 sample categories are hidden while empty; invented search counts are removed
- **Sample-data steps no longer run on install:** `mart369_account` (with a migration that archives sample notices), `mart369_cart` (migration archives the 2 sample deals), `mart369_support` (migration switches off the "[demo]" bot answers), `mart369_address`, `mart369_payment`

### API

- `GET /api/auth/me` (website):
  - **401** means not signed in; the stale cookie is cleared
  - **503** means the shop is unreachable; stay signed in and try later
- `GET /369mart/home/<mode>`: same shape as before; the content is now the catalogue-built page.
- Every list route (`/369mart/browse`, `/369mart/search`, `/369mart/offers`, home rows) leaves out products whose `type` is `service`. `/369mart/products?ids=` still returns them.

### What the app must copy

1. Never show a placeholder user. Until "who am I" answers, show a loading state.
2. On **401** from "who am I" (or any signed-in call), drop the saved session and open sign-in with a short "you were signed out" message, then come back to where the customer was.
3. On **503**, keep the session and show "can't reach the shop".
4. Don't list service items in any list the app builds itself (`type == 'service'`). The server's lists already leave them out.
