# 369ai Image Server Connector (ERP 19)

Every image saved in the ERP goes to the 369ai image server. The database keeps only the link. Screens, POS and the website load each picture straight from `https://images.369ai.biz`.

## What it covers
- **Every image field in every app.** This includes standard apps, custom modules and Studio fields, plus any app installed later, with single or multiple images.
- **Product images** are stored in the server folders `products/<category>/<brand>/<internal reference>/`. The product image is `main`, and extra (website) images are `1, 2, 3…`.
- **Everything else** goes to the ERP server's own folder `media/<server>/<module>/…`:
  - images of public models (contacts, users, employees, products…) → public link, e.g. `https://images.369ai.biz/danat-oman-erp/contacts/acme-trading-45.jpg`
  - all other files — cheques, PDFs, Office files, chatter attachments, custom modules → **private** (`🔒`, no public link, opened only inside the ERP after login): `media/<server>/<module>/<yyyy>/<mm>/<record>-<id>-<field>.<ext>`
  - Settings › Image Server › *Public or private* lists the models whose images are public.
- **Direct upload:** the image box sends the picture straight from the browser to the image server with a short-lived single-use upload link; the ERP only saves the link. Screens always use the permanent public link. If the image server can't be reached, the normal upload is used and the picture is sent later.
- **Change / delete** a picture: the server file is replaced (link gets a new `?v=`) or deleted automatically.
- **Changes to category, brand or internal reference** move the server folder automatically.
- **If the server is offline**, the image stays in the ERP and is uploaded automatically every 5 minutes.
- **Existing images:** Image Server › Migration › *Move all*. *Bring all back* undoes it. Uninstalling the module also copies every image back first.

## Install
```bash
# 1. image server (upload the imgserver folder to /home/ubuntu first)
cd /home/ubuntu/imgserver && sudo bash update.sh

# 2. ERP server (upload the folder to /home/ubuntu with WinSCP first)
sudo cp -r /home/ubuntu/ai369_image_server /opt/odoo/odoo19-custom-addons/
sudo chown -R odoo:odoo /opt/odoo/odoo19-custom-addons/ai369_image_server
sudo -u odoo /opt/odoo/odoo19-venv/bin/python3 /opt/odoo/odoo19/odoo-bin -c /etc/odoo19.conf -d <db> \
     -i ai369_image_server --stop-after-init --http-port=8999 --gevent-port=8998
sudo systemctl restart odoo19
```

## Setup (Settings › Image Server)
1. Tick **Store images on the Image Server**.
2. On the image server admin open **ERP Connections › + Add ERP connection** (name, database name, ERP address) and copy the key it shows once.
3. Enter Server URL `https://images.369ai.biz`, paste the key in **Enter / change key**, then **Save**.
4. Click **Test connection**. It should say "Connected … as connection “<name>”".
5. Click **Open migration** › **Move all (background)**. Press Refresh to watch the counts.

Options:
- **Which images:** all (default), products only, or a list of models.
- **Similar folder names:** for a name like "Laptop Batteries" when "Laptop Battery" already exists. Use existing (default), create new, or send to the image server admin for approval.
- **Brand field:** `auto` uses `product_brand_id`, `brand_id`, `x_brand` or `x_studio_brand` if present.

## Where to see it
- **Product form › Image Server tab:** status, folder, image and thumbnail URLs (copy button), extra image URLs, *Send to image server*, *Load image from server*.
- **Product list › Action:** send or load images for many products.
- **Image Server › Image Files:** every image with its status and URL. Filter by *Failed* / *Waiting to upload*.

Module icons, payment logos and other app-shipped pictures stay in the ERP, because app updates reload them.
