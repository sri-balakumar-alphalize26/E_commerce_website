# import logging
# import re
# from datetime import timedelta

# from odoo import models, fields, api

# _logger = logging.getLogger(__name__)


# class WaAutoReply(models.Model):
#     """Tracks auto-replies sent to customers."""
#     _name = 'wa.auto.reply'
#     _description = 'WhatsApp Auto Reply Log'
#     _order = 'create_date desc'

#     conversation_id = fields.Many2one('wa.conversation', string='Conversation', index=True)
#     employee_session_id = fields.Many2one('wa.employee.session', string='Employee Session')
#     trigger_message_id = fields.Many2one('wa.communication.log', string='Trigger Message')
#     phone = fields.Char('Phone')
#     customer_message = fields.Text('Customer Message')
#     reply_message = fields.Text('Auto Reply Sent')
#     matched_products = fields.Text('Matched Products')
#     selected_product_id = fields.Many2one('product.template', string='Selected Product')
#     order_id = fields.Many2one('sale.order', string='Sale Order')
#     reply_type = fields.Selection([
#         ('product_search', 'Product Search'),
#         ('product_detail', 'Product Detail'),
#         ('order_confirm', 'Order Confirmation'),
#         ('order_created', 'Order Created'),
#         ('quantity_ask', 'Quantity Ask'),
#         ('no_match', 'No Match'),
#         ('general', 'General'),
#     ], string='Reply Type', default='product_search')
#     status = fields.Selection([
#         ('sent', 'Sent'),
#         ('failed', 'Failed'),
#         ('no_match', 'No Match'),
#     ], string='Status', default='sent')
#     error = fields.Text('Error Details')

#     @api.model
#     def _cron_check_auto_reply(self):
#         """Cron job: check for unanswered messages and auto-reply."""
#         sessions = self.env['wa.employee.session'].search([
#             ('auto_reply_enabled', '=', True),
#             ('monitoring_enabled', '=', True),
#             ('active', '=', True),
#         ])

#         for session in sessions:
#             try:
#                 self._process_session_auto_reply(session)
#             except Exception as e:
#                 _logger.error("Auto-reply error for session %s: %s", session.id, e)

#     def _process_session_auto_reply(self, session):
#         """Check conversations for unanswered messages in one session."""
#         timeout_seconds = session.auto_reply_timeout or 120
#         cutoff_time = fields.Datetime.now() - timedelta(seconds=timeout_seconds)

#         # Find conversations with recent incoming messages that have no reply
#         conversations = self.env['wa.conversation'].search([
#             ('employee_session_id', '=', session.id),
#         ])

#         for conv in conversations:
#             try:
#                 self._check_conversation(conv, session, cutoff_time)
#             except Exception as e:
#                 _logger.error("Auto-reply error conv %s: %s", conv.id, e)

#     def _check_conversation_for_message(self, conv, session, cutoff_time, trigger_log):
#         """Like _check_conversation but always uses a specific trigger_log as the 'last message'.
#         This fixes the case where the user sends multiple messages quickly (e.g. 'i need laptop'
#         then 'hi') and the earlier timer would abort because a newer message existed."""
#         # Temporarily monkey-patch the search so _check_conversation sees trigger_log as last
#         # Instead, we call the inner processing logic directly.
#         phone = conv.phone or ''
#         if not phone or not phone.strip():
#             return
#         if 'broadcast' in phone.lower() or 'status' in phone.lower() or 'g.us' in phone.lower():
#             return

#         last_log = trigger_log
#         customer_text = last_log.message_text or ''
#         if not customer_text.strip():
#             return

#         # Check if we already auto-replied to this exact message
#         existing = self.search([
#             ('trigger_message_id', '=', last_log.id),
#         ], limit=1)
#         if existing:
#             return

#         _logger.info("Auto-reply (specific msg) triggered for conv %s, phone %s: '%s'",
#                      conv.id, conv.phone, customer_text[:50])

#         stripped = customer_text.strip().lower()

#         # Pure greeting — reply with greeting only
#         greeting_words = {
#             'hi', 'hello', 'hey', 'hii', 'hiii', 'helo', 'helo', 'hai',
#             'good morning', 'good evening', 'good afternoon', 'good night',
#             'greetings', 'howdy', 'sup', 'yo',
#         }
#         if stripped in greeting_words:
#             greeting = session.auto_reply_greeting or 'Hi! Thank you for reaching out. 😊'
#             reply = (
#                 f"{greeting}\n\n"
#                 f"How can I help you today? Please tell me what product you're looking for "
#                 f"and I'll find the best options for you! 🛍️\n\n"
#                 f"_(This is an automated reply. Our agent will be with you shortly.)_"
#             )
#             self._send_message_smart(session, conv.phone, reply)
#             self.create({
#                 'conversation_id': conv.id,
#                 'employee_session_id': session.id,
#                 'trigger_message_id': last_log.id,
#                 'phone': conv.phone,
#                 'customer_message': customer_text,
#                 'reply_message': reply,
#                 'reply_type': 'general',
#                 'status': 'sent',
#             })
#             return

#         # Determine if sender is an existing contact
#         is_existing_contact = False
#         phone_to_check = conv.phone or ''
#         if phone_to_check:
#             partner = self._find_existing_partner(phone_to_check)
#             if partner and self._is_real_contact(partner):
#                 is_existing_contact = True
#                 _logger.info("Found existing contact! %s (ID: %s)", partner.name, partner.id)

#         # Get previous reply for flow context
#         prev_reply = self.search([
#             ('conversation_id', '=', conv.id),
#             ('status', '=', 'sent'),
#             ('create_date', '<', last_log.message_date),
#         ], order='create_date desc', limit=1)

#         reply = ''
#         reply_type = 'product_search'
#         selected_product = None
#         order = None
#         matched = ''

#         # Product search flow
#         products = self._search_products(customer_text, session.auto_reply_max_products or 5)
#         reply = self._build_product_list_reply(session, customer_text, products, is_existing_contact)
#         matched = ', '.join(products.mapped('name')) if products else ''

#         # Send the reply
#         status = 'sent'
#         error = ''
#         try:
#             if conv.phone:
#                 self._send_message_smart(session, conv.phone, reply)
#                 _logger.info("Auto-reply (specific msg) sent to %s: %s", conv.phone, reply[:80])
#             else:
#                 status = 'failed'
#                 error = 'No phone number'
#         except Exception as e:
#             status = 'failed'
#             error = str(e)
#             _logger.error("Failed to send auto-reply (specific msg) to %s: %s", conv.phone, e)

#         self.create({
#             'conversation_id': conv.id,
#             'employee_session_id': session.id,
#             'trigger_message_id': last_log.id,
#             'phone': conv.phone,
#             'customer_message': customer_text,
#             'reply_message': reply,
#             'matched_products': matched,
#             'selected_product_id': selected_product.id if selected_product else False,
#             'order_id': order.id if order else False,
#             'reply_type': reply_type,
#             'status': status,
#             'error': error,
#         })

#     def _build_product_list_reply(self, session, customer_text, products, is_existing_contact):
#         """Build the product listing reply (same logic as inside _check_conversation)."""
#         no_match_msg = session.auto_reply_no_match or \
#             'Sorry, I could not find matching products. An agent will assist you shortly.'
#         if not products:
#             return (
#                 f"{no_match_msg}\n\n"
#                 "_(This is an automated reply. Our agent will be with you shortly.)_"
#             )
#         greeting = session.auto_reply_greeting or 'Hi! Thank you for reaching out. 😊'
#         lines = [
#             f"{greeting}\n",
#             f"Here are the products I found for *\"{customer_text[:60]}\"*:\n",
#         ]
#         for i, p in enumerate(products, 1):
#             price = p.list_price if is_existing_contact else p.wa_retail_price
#             line = f"{i}. 📦 *{p.name}*"
#             if price:
#                 line += f" — 💰 Rate: {price:.2f}"
#             lines.append(line)
#         lines.append("\nReply with the *number* (e.g. 1, 2, 3) to get more details about a product! 😊")
#         lines.append("\n_(Price may vary, our assistant will contact you.)_")
#         lines.append("\n_(This is an automated reply. Our agent will be with you shortly.)_")
#         return '\n'.join(lines)

#     def _check_conversation(self, conv, session, cutoff_time):
#         """Check if a conversation needs auto-reply."""
#         phone = conv.phone or ''
#         if not phone or not phone.strip():

#             return

#         # Skip broadcast/status/group conversations
#         if 'broadcast' in phone.lower() or 'status' in phone.lower() or 'g.us' in phone.lower():
#             return

#         # Get last message in conversation
#         last_log = self.env['wa.communication.log'].search([
#             ('conversation_id', '=', conv.id),
#         ], order='message_date desc', limit=1)

#         if not last_log:
#             return

#         # Only auto-reply if last message is INCOMING and older than timeout
#         if last_log.direction != 'incoming':
#             return  # Employee already replied

#         # Check if we already auto-replied to this exact message
#         existing = self.search([
#             ('trigger_message_id', '=', last_log.id),
#         ], limit=1)
#         if existing:
#             return  # Already handled

#         # Check if this conversation has had a previous auto-reply
#         # If yes, respond faster (customer is in active conversation with bot)
#         prev_auto_reply = self.search([
#             ('conversation_id', '=', conv.id),
#             ('status', '=', 'sent'),
#         ], limit=1)

#         # Use the passed cutoff_time for both first and follow-up messages.
#         # But if the customer is actively interacting with the bot (we sent a reply recently),
#         # don't wait the full timeout_seconds. Allow immediate replies to follow-ups.
#         if prev_auto_reply:
#             # Check if our last reply was within the last 15 minutes (active session)
#             active_window = fields.Datetime.now() - timedelta(minutes=15)
#             if prev_auto_reply.create_date >= active_window:
#                 # Bypass the strict timeout for active conversations
#                 cutoff_time = fields.Datetime.now()

#         if not last_log.message_date or last_log.message_date > cutoff_time:
#             return  # Not yet timed out

#         # Don't auto-reply to very old messages (more than 30 min)
#         max_age = fields.Datetime.now() - timedelta(minutes=30)
#         if last_log.message_date < max_age:
#             return

#         customer_text = last_log.message_text or ''
#         if not customer_text.strip():
#             return  # Empty message

#         _logger.info("Auto-reply triggered for conv %s, phone %s: '%s'",
#                      conv.id, conv.phone, customer_text[:50])

#         stripped = customer_text.strip().lower()

#         # Pure greeting — reply with greeting only, no product search
#         greeting_words = {
#             'hi', 'hello', 'hey', 'hii', 'hiii', 'helo', 'helo', 'hai',
#             'good morning', 'good evening', 'good afternoon', 'good night',
#             'greetings', 'howdy', 'sup', 'yo',
#         }
#         if stripped in greeting_words:
#             greeting = session.auto_reply_greeting or 'Hi! Thank you for reaching out. 😊'
#             reply = (
#                 f"{greeting}\n\n"
#                 f"How can I help you today? Please tell me what product you're looking for "
#                 f"and I'll find the best options for you! 🛍️\n\n"
#                 f"_(This is an automated reply. Our agent will be with you shortly.)_"
#             )
#             self._send_message_smart(session, conv.phone, reply)
#             self.create({
#                 'conversation_id': conv.id,
#                 'employee_session_id': session.id,
#                 'trigger_message_id': last_log.id,
#                 'phone': conv.phone,
#                 'customer_message': customer_text,
#                 'reply_message': reply,
#                 'reply_type': 'general',
#                 'status': 'sent',
#             })
#             return

#         # Get last auto-reply for this conversation to understand context
#         prev_reply = self.search([
#             ('conversation_id', '=', conv.id),
#             ('status', '=', 'sent'),
#         ], order='create_date desc', limit=1)

# #         # Determine if the sender is an existing contact
#         is_existing_contact = False
#         phone_to_check = conv.phone or ''
#         if phone_to_check:
#             partner = self._find_existing_partner(phone_to_check)
#             if partner and self._is_real_contact(partner):
#                 is_existing_contact = True
#                 _logger.info(f"[CRON] Found existing contact! {partner.name} (ID: {partner.id})")

#         reply = ''
#         reply_type = 'general'
#         selected_product = None
#         order = None
#         matched = ''

#         # --- FLOW: Customer says "yes"/"confirm"/"order" after product detail ---
#         if prev_reply and prev_reply.reply_type == 'product_detail' and prev_reply.selected_product_id:
#             if stripped in ('yes', 'y', 'ok', 'confirm', 'order', 'buy', 'yeah', 'yep', 'sure'):
#                 # Ask for quantity
#                 product = prev_reply.selected_product_id
#                 price = product.list_price if is_existing_contact else product.wa_retail_price
#                 reply = (
#                     f"Great choice! 🎉\n\n"
#                     f"📦 *{product.name}*\n"
#                     f"💰 *Rate:* {price:.2f}\n\n"
#                     f"How many units would you like to order? Please reply with the *quantity* (e.g. 1, 2, 5)."
#                 )
#                 reply_type = 'quantity_ask'
#                 selected_product = product
#                 matched = product.name
#             elif stripped == 'no' or stripped == 'cancel':
#                 reply = (
#                     "No problem! 😊 Feel free to ask about any other product. "
#                     "Just type what you're looking for and I'll help you find it!"
#                 )
#                 reply_type = 'general'
#             else:
#                 # Treat as new product search
#                 products = self._search_products(customer_text, session.auto_reply_max_products or 5)
#                 reply = self._build_reply(session, customer_text, products, is_existing_contact)
#                 reply_type = 'product_search'
#                 matched = ', '.join(products.mapped('name')) if products else ''

#         # --- FLOW: Customer gives quantity after "quantity_ask" ---
#         elif prev_reply and prev_reply.reply_type == 'quantity_ask' and prev_reply.selected_product_id:
#             qty = self._parse_quantity(stripped)
#             if qty and qty > 0:
#                 product = prev_reply.selected_product_id
#                 # Create the Sale Order!
#                 order = self._create_sale_order(session, conv, product, qty, is_existing_contact)
#                 if order:
#                     price = product.list_price if is_existing_contact else product.wa_retail_price
#                     total = price * qty
#                     reply = (
#                         f"✅ *Order Confirmed!* 🎉\n\n"
#                         f"📋 *Order Reference:* {order.name}\n"
#                         f"📦 *Product:* {product.name}\n"
#                         f"🔢 *Quantity:* {qty}\n"
#                         f"💰 *Unit Price:* {price:.2f}\n"
#                         f"💵 *Total:* {total:.2f}\n\n"
#                         f"Your order has been placed successfully! Our team will process it and get back to you with delivery details. 🚀\n\n"
#                         f"Need anything else? Just type your request! 😊\n\n"
#                         f"_(This is an automated reply. Our agent will be with you shortly.)_"
#                     )
#                     reply_type = 'order_created'
#                     selected_product = product
#                     matched = product.name
#                 else:
#                     reply = "Sorry, there was an issue creating your order. Our agent will assist you shortly! 🙏"
#                     reply_type = 'general'
#             else:
#                 reply = "Please reply with a valid quantity number (e.g. *1*, *2*, *5*). 😊"
#                 reply_type = 'quantity_ask'
#                 selected_product = prev_reply.selected_product_id
#                 matched = prev_reply.selected_product_id.name if prev_reply.selected_product_id else ''

#         # --- FLOW: Customer replies with product number (1, 2, 3...) ---
#         elif prev_reply and prev_reply.matched_products and stripped.isdigit():
#             product_num = int(stripped)
#             result = self._get_selected_product(prev_reply, product_num, is_existing_contact)
#             if result:
#                 product, reply = result
#                 reply_type = 'product_detail'
#                 selected_product = product
#                 matched = f'Product #{stripped}: {product.name}'
#             else:
#                 reply = self._build_product_detail_reply(session, prev_reply, product_num, is_existing_contact)
#                 reply_type = 'product_detail'
#                 matched = f'Product #{stripped} detail'

#         # --- FLOW: New product search ---
#         else:
#             products = self._search_products(customer_text, session.auto_reply_max_products or 5)
#             reply = self._build_reply(session, customer_text, products, is_existing_contact)
#             reply_type = 'product_search'
#             matched = ', '.join(products.mapped('name')) if products else ''

#         # Send via WhatsApp - supports both real numbers and LID
#         status = 'sent'
#         error = ''
#         try:
#             phone = conv.phone or ''
#             if phone:
#                 self._send_message_smart(session, phone, reply)
#                 _logger.info("Auto-reply sent to %s: %s", phone, reply[:80])
#             else:
#                 status = 'failed'
#                 error = 'No phone number'
#         except Exception as e:
#             status = 'failed'
#             error = str(e)
#             _logger.error("Failed to send auto-reply to %s: %s", conv.phone, e)

#         # Log the auto-reply
#         self.create({
#             'conversation_id': conv.id,
#             'employee_session_id': session.id,
#             'trigger_message_id': last_log.id,
#             'phone': conv.phone,
#             'customer_message': customer_text,
#             'reply_message': reply,
#             'matched_products': matched,
#             'selected_product_id': selected_product.id if selected_product else False,
#             'order_id': order.id if order else False,
#             'reply_type': reply_type,
#             'status': status,
#             'error': error,
#         })

#     def _build_product_detail_reply(self, session, prev_reply, product_num, is_existing_contact):
#         """Build detailed product info when customer replies with a number."""
#         # Get the products from previous reply
#         product_names = [p.strip() for p in (prev_reply.matched_products or '').split(',') if p.strip()]

#         if product_num < 1 or product_num > len(product_names):
#             return (
#                 f"Sorry, please reply with a number between *1* and *{len(product_names)}* "
#                 f"to select a product from the list above. 😊"
#             )

#         selected_name = product_names[product_num - 1]

#         # Find the product in database
#         product = self.env['product.template'].sudo().search([
#             ('name', '=', selected_name),
#             ('active', '=', True),
#         ], limit=1)

#         if not product:
#             # Try partial match
#             product = self.env['product.template'].sudo().search([
#                 ('name', 'ilike', selected_name[:30]),
#                 ('active', '=', True),
#             ], limit=1)

#         if not product:
#             return f"Sorry, I couldn't find details for that product. Our agent will help you shortly! 🙏"

#         # Build detailed product info
#         lines = [f"📦 *{product.name}*"]
#         lines.append('')

#         price = product.list_price if is_existing_contact else product.wa_retail_price
#         if price:
#             lines.append(f"💰 *Rate:* {price:.2f}")

#         if product.categ_id:
#             lines.append(f"📂 *Category:* {product.categ_id.name}")

#         if product.description_sale:
#             desc = product.description_sale[:200]
#             lines.append(f"📝 *Description:* {desc}")

#         # Check stock if available
#         try:
#             if hasattr(product, 'qty_available'):
#                 qty = product.qty_available
#                 if qty > 0:
#                     lines.append(f"✅ *In Stock:* {qty:.0f} units available")
#                 else:
#                     lines.append("⚠️ *Stock:* Currently out of stock - please check with our agent")
#         except Exception:
#             pass

#         lines.append('')
#         lines.append("\nWould you like to place an order for this product? Reply *yes* to confirm or ask about another product! 😊")
#         lines.append("\n_(Price may vary, our assistant will contact you.)_")
#         lines.append("\n_(This is an automated reply. Our agent will be with you shortly.)_")

#         return '\n'.join(lines)

#     def _get_selected_product(self, prev_reply, product_num, is_existing_contact):
#         """Get product from previous reply's product list by number."""
#         product_names = [p.strip() for p in (prev_reply.matched_products or '').split(',') if p.strip()]

#         if product_num < 1 or product_num > len(product_names):
#             return None

#         selected_name = product_names[product_num - 1]

#         # Find the product
#         product = self.env['product.template'].sudo().search([
#             ('name', '=', selected_name),
#             ('active', '=', True),
#         ], limit=1)

#         if not product:
#             product = self.env['product.template'].sudo().search([
#                 ('name', 'ilike', selected_name[:30]),
#                 ('active', '=', True),
#             ], limit=1)

#         if not product:
#             return None

#         # Build detail reply
#         lines = [f"📦 *{product.name}*"]
#         lines.append('')

#         price = product.list_price if is_existing_contact else product.wa_retail_price
#         if price:
#             lines.append(f"💰 *Price:* {price:.2f}")

#         if product.categ_id:
#             lines.append(f"📂 *Category:* {product.categ_id.name}")

#         if product.description_sale:
#             desc = product.description_sale[:200]
#             lines.append(f"📝 *Description:* {desc}")

#         try:
#             if hasattr(product, 'qty_available'):
#                 qty = product.qty_available
#                 if qty > 0:
#                     lines.append(f"✅ *In Stock:* {qty:.0f} units available")
#                 else:
#                     lines.append("⚠️ *Stock:* Currently out of stock")
#         except Exception:
#             pass

#         lines.append('')
#         lines.append("\nWould you like to order this product? Reply *yes* to proceed or type another product name to search! 😊")
#         lines.append("\n_(Price may vary, our assistant will contact you.)_")
#         lines.append("\n_(This is an automated reply. Our agent will be with you shortly.)_")

#         return (product, '\n'.join(lines))

#     def _parse_quantity(self, text):
#         """Parse quantity from customer text."""
#         text = text.strip().lower()
#         # Direct number
#         if text.isdigit():
#             return int(text)
#         # Extract number from text like "i want 5" or "5 pieces"
#         numbers = re.findall(r'\d+', text)
#         if numbers:
#             return int(numbers[0])
#         return None

#     def _create_sale_order(self, session, conv, product_template, qty, is_existing_contact):
#         """Create a sale order in Odoo from WhatsApp conversation."""
#         try:
#             # Find or create customer partner
#             partner = self._get_or_create_partner(conv)

#             # Get the product variant
#             product = product_template.product_variant_id
#             if not product:
#                 product = product_template.product_variant_ids[:1]
#             if not product:
#                 _logger.error("No product variant found for template %s", product_template.name)
#                 return None

#             # Create Sale Order
#             order_vals = {
#                 'partner_id': partner.id,
#                 'origin': f'WhatsApp Auto-Reply ({conv.phone})',
#                 'note': f'Order created via WhatsApp auto-reply.\nEmployee: {session.employee_id.name}\nCustomer Phone: {conv.phone}\nCustomer Name: {conv.contact_name or ""}',
#             }

#             # Set company if available
#             if session.session_id.company_id:
#                 order_vals['company_id'] = session.session_id.company_id.id

#             order = self.env['sale.order'].sudo().create(order_vals)

#             price = product_template.list_price if is_existing_contact else product_template.wa_retail_price

#             # Add order line
#             line_vals = {
#                 'order_id': order.id,
#                 'product_id': product.id,
#                 'product_uom_qty': qty,
#                 'price_unit': price,
#                 'product_uom_id': product.uom_id.id,
#             }

#             self.env['sale.order.line'].sudo().create(line_vals)

#             _logger.info("Sale order %s created from WhatsApp for phone %s, product %s x%s",
#                          order.name, conv.phone, product_template.name, qty)

#             return order

#         except Exception as e:
#             _logger.error("Failed to create sale order: %s", e)
#             return None

#     def _get_or_create_partner(self, conv):
#         """Find or create a partner for the WhatsApp customer."""
#         phone = conv.phone or ''
#         contact_name = conv.contact_name or ''

#         # Try to find existing partner by phone
#         if phone:
#             partner = self.env['res.partner'].sudo().search([
#                 ('phone', 'ilike', phone[-10:]),
#             ], limit=1)
#             if not partner:
#                 partner = self.env['res.partner'].sudo().search([
#                     ('phone', 'ilike', phone),
#                 ], limit=1)
#             if partner:
#                 return partner

#         # Create new partner
#         name = contact_name or f'WhatsApp Customer ({phone})'
#         partner = self.env['res.partner'].sudo().create({
#             'name': name,
#             'phone': phone,
#             'comment': f'Auto-created from WhatsApp conversation',
#         })
#         _logger.info("Created partner %s for WhatsApp phone %s", partner.name, phone)
#         return partner

#     def _send_message_smart(self, session, phone, message):
#         """Send WhatsApp message - handles both real numbers and LID numbers."""
#         from neonize.utils import build_jid

#         wa_session = session.session_id
#         client = wa_session._get_connected_client()

#         phone_clean = phone.strip().replace('+', '').replace(' ', '').replace('-', '')
#         phone_digits = ''.join(c for c in phone_clean if c.isdigit())

#         jid = build_jid(phone_digits)

#         # LID numbers: more than 14 digits = use LID server
#         if len(phone_digits) > 14:
#             jid.Server = "lid"
#             _logger.info("Using LID JID for phone %s", phone_digits)

#         client.send_message(jid, message)

#         # Log as whatsapp.message
#         wa_session.env['whatsapp.message'].sudo().create({
#             'session_id': wa_session.id,
#             'phone': phone_clean,
#             'message': message,
#             'direction': 'outgoing',
#             'status': 'sent',
#         })

#     def _search_products(self, customer_text, max_results=5):
#         """Search products matching customer message keywords."""
#         # Clean and extract keywords
#         text = customer_text.lower().strip()
#         # Remove common words
#         stop_words = {
#             'i', 'need', 'want', 'looking', 'for', 'a', 'an', 'the', 'do',
#             'you', 'have', 'any', 'please', 'hi', 'hello', 'hey', 'can',
#             'get', 'me', 'is', 'there', 'it', 'this', 'that', 'what',
#             'how', 'much', 'price', 'cost', 'available', 'stock', 'buy',
#             'sir', 'madam', 'thanks', 'thank', 'ok', 'okay', 'yes', 'no',
#             'good', 'morning', 'evening', 'afternoon', 'bro', 'dear',
#         }

#         # Extract meaningful words
#         words = re.findall(r'[a-zA-Z0-9]+', text)
#         keywords = [w for w in words if w.lower() not in stop_words and len(w) > 1]

#         if not keywords:
#             return self.env['product.template']

#         _logger.info("Product search keywords: %s", keywords)

#         # Strategy 1: Search with all keywords combined
#         all_products = self.env['product.template']

#         # Try full phrase first
#         full_phrase = ' '.join(keywords)
#         products = self.env['product.template'].search([
#             ('sale_ok', '=', True),
#             ('active', '=', True),
#             ('name', 'ilike', full_phrase),
#         ], limit=max_results)

#         if products:
#             return products

#         # Try each keyword individually and score by matches
#         product_scores = {}
#         for kw in keywords:
#             matches = self.env['product.template'].search([
#                 ('sale_ok', '=', True),
#                 ('active', '=', True),
#                 '|',
#                 ('name', 'ilike', kw),
#                 ('categ_id.name', 'ilike', kw),
#             ], limit=50)
#             for p in matches:
#                 product_scores[p.id] = product_scores.get(p.id, 0) + 1

#         if not product_scores:
#             return self.env['product.template']

#         # Sort by score (most keyword matches first)
#         sorted_ids = sorted(product_scores.keys(),
#                            key=lambda pid: product_scores[pid],
#                            reverse=True)[:max_results]

#         return self.env['product.template'].browse(sorted_ids)

#     def _build_reply(self, session, customer_text, products, is_existing_contact):
#         """Build the auto-reply message."""
#         greeting = session.auto_reply_greeting or 'Hi! Thank you for reaching out. 😊'

#         if not products:
#             # No exact match - suggest popular/alternative products
#             alternatives = self._get_alternative_products(customer_text, session.auto_reply_max_products or 5)

#             if alternatives:
#                 lines = [greeting]
#                 lines.append('')
#                 lines.append(f"We couldn't find an exact match for *\"{customer_text.strip()}\"*, but here are some products you might be interested in:")
#                 lines.append('')
#                 for i, product in enumerate(alternatives, 1):
#                     price_str = ''
#                     price = product.list_price if is_existing_contact else product.wa_retail_price
#                     if price:
#                         price_str = f' - *Price: {price:.2f}*'
#                     lines.append(f'{i}. {product.name}{price_str}')
#                 lines.append('')
#                 lines.append("Would any of these work for you? Or feel free to describe what you're looking for and we'll find the best option! 🔍")
#                 lines.append('')
#                 lines.append('_(This is an automated reply. Our agent will be with you shortly.)_')
#                 return '\n'.join(lines)
#             else:
#                 no_match = session.auto_reply_no_match or \
#                     "We appreciate your interest! We're currently checking availability for your request. Our team will get back to you shortly with the best options. 🙏"
#                 return f"{greeting}\n\n{no_match}"

#         lines = [greeting]
#         lines.append('')
#         lines.append("Great news! We have the following products matching your request:")
#         lines.append('')

#         for i, product in enumerate(products, 1):
#             price_str = ''
#             price = product.list_price if is_existing_contact else product.wa_retail_price
#             if price:
#                 price_str = f' - *Price: {price:.2f}*'
#             lines.append(f'{i}. {product.name}{price_str}')

#         lines.append('')
#         lines.append("Simply reply with the *product number* to know more, or let us know if you need something different! 😊")
#         lines.append('')
#         lines.append('_(This is an automated reply. Our agent will be with you shortly.)_')

#         return '\n'.join(lines)

#     def _get_alternative_products(self, customer_text, max_results=5):
#         """Get alternative/popular products when no exact match is found."""
#         # Try to find products from broader categories
#         text = customer_text.lower().strip()
#         words = re.findall(r'[a-zA-Z0-9]+', text)

#         # Remove all stop words to get core keywords
#         stop_words = {
#             'i', 'need', 'want', 'looking', 'for', 'a', 'an', 'the', 'do',
#             'you', 'have', 'any', 'please', 'hi', 'hello', 'hey', 'can',
#             'get', 'me', 'is', 'there', 'it', 'this', 'that', 'what',
#             'how', 'much', 'price', 'cost', 'available', 'stock', 'buy',
#             'sir', 'madam', 'thanks', 'thank', 'ok', 'okay', 'yes', 'no',
#             'good', 'morning', 'evening', 'afternoon', 'bro', 'dear',
#         }
#         keywords = [w for w in words if w.lower() not in stop_words and len(w) > 1]

#         if not keywords:
#             # If no keywords, return some popular/recent products
#             return self.env['product.template'].sudo().search([
#                 ('sale_ok', '=', True),
#                 ('active', '=', True),
#                 ('list_price', '>', 0),
#             ], order='write_date desc', limit=max_results)

#         # Try matching by category name
#         categories = self.env['product.category'].sudo().search([
#             ('name', 'ilike', keywords[0]),
#         ])

#         if categories:
#             products = self.env['product.template'].sudo().search([
#                 ('categ_id', 'in', categories.ids),
#                 ('sale_ok', '=', True),
#                 ('active', '=', True),
#             ], limit=max_results)
#             if products:
#                 return products

#         # Try single keyword partial match on product name
#         for kw in keywords:
#             products = self.env['product.template'].sudo().search([
#                 ('name', 'ilike', kw),
#                 ('sale_ok', '=', True),
#                 ('active', '=', True),
#             ], limit=max_results)
#             if products:
#                 return products

#         # Fallback: popular products
#         return self.env['product.template'].sudo().search([
#             ('sale_ok', '=', True),
#             ('active', '=', True),
#             ('list_price', '>', 0),
#         ], order='write_date desc', limit=max_results)
import logging
import re
from datetime import timedelta

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class WaAutoReply(models.Model):
    """Tracks auto-replies sent to customers."""
    _name = 'wa.auto.reply'
    _description = 'WhatsApp Auto Reply Log'
    _order = 'create_date desc'

    conversation_id = fields.Many2one('wa.conversation', string='Conversation', index=True)
    employee_session_id = fields.Many2one('wa.employee.session', string='Employee Session')
    trigger_message_id = fields.Many2one('wa.communication.log', string='Trigger Message')
    phone = fields.Char('Phone')
    customer_message = fields.Text('Customer Message')
    reply_message = fields.Text('Auto Reply Sent')
    matched_products = fields.Text('Matched Products')
    selected_product_id = fields.Many2one('product.template', string='Selected Product')
    order_id = fields.Many2one('sale.order', string='Sale Order')
    reply_type = fields.Selection([
        ('product_search', 'Product Search'),
        ('product_detail', 'Product Detail'),
        ('order_confirm', 'Order Confirmation'),
        ('order_created', 'Order Created'),
        ('quantity_ask', 'Quantity Ask'),
        ('price_negotiate', 'Price Negotiation'),
        ('await_delivery', 'Awaiting Delivery Address'),
        ('await_address', 'Awaiting Customer Details'),
        ('await_payment', 'Awaiting Payment'),
        ('no_match', 'No Match'),
        ('general', 'General'),
    ], string='Reply Type', default='product_search')
    status = fields.Selection([
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('no_match', 'No Match'),
    ], string='Status', default='sent')
    error = fields.Text('Error Details')
    offered_price = fields.Float('Negotiated Price')

    @api.model
    def _cron_check_auto_reply(self):
        """Cron job: check for unanswered messages and auto-reply."""
        sessions = self.env['wa.employee.session'].search([
            ('auto_reply_enabled', '=', True),
            ('monitoring_enabled', '=', True),
            ('active', '=', True),
        ])

        for session in sessions:
            try:
                self._process_session_auto_reply(session)
            except Exception as e:
                _logger.error("Auto-reply error for session %s: %s", session.id, e)

    def _process_session_auto_reply(self, session):
        """Check conversations for unanswered messages in one session."""
        timeout_seconds = session.auto_reply_timeout or 120
        cutoff_time = fields.Datetime.now() - timedelta(seconds=timeout_seconds)

        # Find conversations with recent incoming messages that have no reply
        conversations = self.env['wa.conversation'].search([
            ('employee_session_id', '=', session.id),
        ])

        for conv in conversations:
            try:
                self._check_conversation(conv, session, cutoff_time)
            except Exception as e:
                _logger.error("Auto-reply error conv %s: %s", conv.id, e)

    def _check_conversation_for_message(self, conv, session, cutoff_time, trigger_log):
        """Like _check_conversation but always uses a specific trigger_log as the 'last message'.
        This fixes the case where the user sends multiple messages quickly (e.g. 'i need laptop'
        then 'hi') and the earlier timer would abort because a newer message existed."""
        # Temporarily monkey-patch the search so _check_conversation sees trigger_log as last
        # Instead, we call the inner processing logic directly.
        phone = conv.phone or ''
        if not phone or not phone.strip():
            return
        if 'broadcast' in phone.lower() or 'status' in phone.lower() or 'g.us' in phone.lower():
            return

        last_log = trigger_log
        # For voice messages, use English translation for product search (falls back to transcription)
        if last_log.is_voice_message and last_log.voice_transcription:
            customer_text = last_log.voice_translation or last_log.voice_transcription
        else:
            customer_text = last_log.message_text or ''
        if not customer_text.strip() or customer_text.strip() == '[Voice Message]':
            return

        # Check if we already auto-replied to this exact message
        existing = self.search([
            ('trigger_message_id', '=', last_log.id),
        ], limit=1)
        if existing:
            return

        _logger.info("Auto-reply (specific msg) triggered for conv %s, phone %s: '%s'",
                     conv.id, conv.phone, customer_text[:50])

        stripped = customer_text.strip().lower()

        # Pure greeting — reply with greeting only
        greeting_words = {
            'hi', 'hello', 'hey', 'hii', 'hiii', 'helo', 'helo', 'hai',
            'good morning', 'good evening', 'good afternoon', 'good night',
            'greetings', 'howdy', 'sup', 'yo',
        }
        if stripped in greeting_words:
            greeting = session.auto_reply_greeting or 'Hi! Thank you for reaching out. 😊'
            reply = (
                f"{greeting}\n\n"
                f"How can I help you today? Please tell me what product you're looking for "
                f"and I'll find the best options for you! 🛍️\n\n"
                f"_(This is an automated reply. Our agent will be with you shortly.)_"
            )
            self._dispatch_auto_reply(session, conv, reply, 'greeting', None, '')
            self.create({
                'conversation_id': conv.id,
                'employee_session_id': session.id,
                'trigger_message_id': last_log.id,
                'phone': conv.phone,
                'customer_message': customer_text,
                'reply_message': reply,
                'reply_type': 'general',
                'status': 'sent',
            })
            return

        # Determine if sender is an existing contact (LID-aware)
        is_existing_contact = self._resolve_is_existing_contact(conv, last_log=last_log)

        # Get the most recent reply for context
        prev_reply = self.search([
            ('conversation_id', '=', conv.id),
            ('status', '=', 'sent'),
            ('create_date', '<', last_log.message_date),
        ], order='create_date desc', limit=1)

        # If the most recent reply broke context (no_match/general from a stray message),
        # look back for the last meaningful state within the last 15 minutes.
        # BUT: never restore context past a completed order — that starts fresh.
        import datetime as _dt
        _fifteen_min_ago = last_log.message_date - _dt.timedelta(minutes=15)
        _needs_restore = (
            prev_reply and prev_reply.reply_type in ('no_match', 'general')
        ) or (
            prev_reply
            and prev_reply.reply_type == 'product_search'
            and not prev_reply.selected_product_id
            and not prev_reply.matched_products
        )
        if _needs_restore:
            meaningful = self.search([
                ('conversation_id', '=', conv.id),
                ('status', '=', 'sent'),
                ('reply_type', 'in', ['product_detail', 'quantity_ask', 'product_search']),
                ('create_date', '>=', _fifteen_min_ago),
                ('create_date', '<', last_log.message_date),
            ], order='create_date desc', limit=1)
            if meaningful and (meaningful.selected_product_id or meaningful.matched_products):
                # Don't restore if an order was already completed after this state
                order_done = self.search([
                    ('conversation_id', '=', conv.id),
                    ('reply_type', '=', 'order_created'),
                    ('create_date', '>', meaningful.create_date),
                    ('create_date', '<', last_log.message_date),
                ], limit=1)
                if not order_done:
                    prev_reply = meaningful

        # --- PRICE BARGAIN (handled early, returns) ---
        if (getattr(session, 'auto_reply_bargain_enabled', True)
                and prev_reply and prev_reply.selected_product_id
                and (prev_reply.reply_type == 'price_negotiate'
                     or (prev_reply.reply_type == 'product_detail'
                         and self._detect_bargain_intent(stripped)))):
            _bprod = prev_reply.selected_product_id
            _breply, _btype, _bprice = self._handle_bargain(
                session, prev_reply, stripped, is_existing_contact)
            try:
                self._dispatch_auto_reply(session, conv, _breply, _btype, _bprod, _bprod.name)
                _bstatus = 'sent'
            except Exception as _be:
                _logger.error("Bargain send failed: %s", _be)
                _bstatus = 'failed'
            self.create({
                'conversation_id': conv.id,
                'employee_session_id': session.id,
                'trigger_message_id': last_log.id,
                'phone': conv.phone,
                'customer_message': customer_text,
                'reply_message': _breply,
                'matched_products': _bprod.name,
                'selected_product_id': _bprod.id,
                'reply_type': _btype,
                'offered_price': _bprice,
                'status': _bstatus,
            })
            return

        # --- POST-ORDER: delivery address (early-handled) ---
        if prev_reply and prev_reply.reply_type in ('await_delivery', 'await_address') and prev_reply.order_id:
            _order = prev_reply.order_id.sudo()
            try:
                if prev_reply.reply_type == 'await_delivery' and stripped in ('addr_same', 'same', 'yes', 'y', 'same address'):
                    _addr = _order.partner_id.address_get(['delivery']).get('delivery') or _order.partner_id.id
                    _order.partner_shipping_id = _addr
                else:
                    self._wa_apply_address(_order, customer_text)
            except Exception as _de:
                _logger.error('Delivery address error: %s', _de)
            _r, _t = self._payment_or_finalize(session, conv, _order)
            self._dispatch_auto_reply(session, conv, _r, _t, None, '')
            self.create({
                'conversation_id': conv.id, 'employee_session_id': session.id,
                'trigger_message_id': last_log.id, 'phone': conv.phone,
                'customer_message': customer_text, 'reply_message': _r,
                'order_id': _order.id, 'reply_type': _t, 'status': 'sent'})
            return

        # --- POST-ORDER: payment (early-handled) ---
        if prev_reply and prev_reply.reply_type == 'await_payment' and prev_reply.order_id:
            _order = prev_reply.order_id.sudo()
            if stripped in ('cod', 'cash', 'cash on delivery', 'c.o.d', 'cashondelivery'):
                try:
                    _order.wa_payment_mode = 'cod'
                except Exception:
                    pass
                _order._wa_settle(paid=False)
                self.create({
                    'conversation_id': conv.id, 'employee_session_id': session.id,
                    'trigger_message_id': last_log.id, 'phone': conv.phone,
                    'customer_message': customer_text, 'reply_message': '[COD settled]',
                    'order_id': _order.id, 'reply_type': 'order_created', 'status': 'sent'})
                return
            elif stripped in ('upi', 'card', 'pay', 'pay online', 'online', 'pay_online'):
                _r = self._online_pay_msg(_order, stripped)
                _t = 'await_payment'
            else:
                _r, _t = self._payment_step(session, _order)
            self._dispatch_auto_reply(session, conv, _r, _t, None, '')
            self.create({
                'conversation_id': conv.id, 'employee_session_id': session.id,
                'trigger_message_id': last_log.id, 'phone': conv.phone,
                'customer_message': customer_text, 'reply_message': _r,
                'order_id': _order.id, 'reply_type': _t, 'status': 'sent'})
            return

        reply = ''
        reply_type = 'product_search'
        selected_product = None
        order = None
        matched = ''

        # ---- Confirmation helpers ----
        # Broader YES words: also checks if text STARTS WITH a yes-word (handles "yes, select the")
        _yes_words = {
            'yes', 'y', 'ok', 'okay', 'confirm', 'order', 'buy', 'yeah', 'yep', 'sure',
            'go ahead', 'proceed', 'place order', 'do it', 'fine', 'alright', 'agreed',
            'correct', 'right', 'sounds good', 'great', 'perfect', 'done',
            'thanks', 'thank you', 'thank', 'gracias', 'شكرا', 'धन्यवाद', 'നന്ദി',
            'ok cool', 'cool', 'nice', 'good', 'please', 'pls', 'asap',
        }
        _no_words = {'no', 'nope', 'cancel', 'stop', 'nevermind', 'never mind', 'not now', 'skip', 'dont', "don't"}

        def _is_yes(text):
            if text in _yes_words:
                return True
            # "yes, select the first one" → starts with yes
            for w in _yes_words:
                if text.startswith(w + ' ') or text.startswith(w + ',') or text.startswith(w + '.'):
                    return True
            return False

        def _is_no(text):
            if text in _no_words:
                return True
            for w in _no_words:
                if text.startswith(w + ' ') or text.startswith(w + ',') or text.startswith(w + '.'):
                    return True
            return False

        # --- FLOW: Customer says "yes"/"confirm"/"order" after product detail ---
        if prev_reply and prev_reply.reply_type == 'product_detail' and prev_reply.selected_product_id:
            if _is_yes(stripped):
                product = prev_reply.selected_product_id
                price = product.list_price if is_existing_contact else product.wa_retail_price
                reply = (
                    f"Great choice! 🎉\n\n"
                    f"📦 *{product.name}*\n"
                    f"💰 *Rate:* {price:.2f}\n\n"
                    f"How many units would you like to order?\n"
                    f"Please reply with the *quantity* (e.g. 1, 2, 5 — or say it: \"five\"). 🎤"
                )
                reply_type = 'quantity_ask'
                selected_product = product
                matched = product.name
            elif _is_no(stripped):
                reply = (
                    "No problem! 😊 Feel free to ask about any other product. "
                    "Just type or say what you're looking for and I'll help you find it!"
                )
                reply_type = 'general'
            else:
                # Could be a product number reply — try parsing before giving up context
                product_num = self._parse_product_number(stripped)
                if product_num and prev_reply.matched_products:
                    result = self._get_selected_product(prev_reply, product_num, is_existing_contact)
                    if result:
                        product, reply = result
                        reply_type = 'product_detail'
                        selected_product = product
                        matched = f'Product #{product_num}: {product.name}'
                    else:
                        # Re-prompt rather than breaking context
                        reply = (
                            f"I couldn't find that option. 😊\n\n"
                            f"Would you like to order *{prev_reply.selected_product_id.name}*?\n"
                            f"Reply *yes* to order, *no* to search again, or send a number to pick a different product."
                        )
                        reply_type = 'product_detail'
                        selected_product = prev_reply.selected_product_id
                        matched = prev_reply.selected_product_id.name
                elif len(stripped.split()) >= 3:
                    # Looks like a new product query (3+ words) — start fresh search
                    products = self._search_products(customer_text, session.auto_reply_max_products or 5)
                    reply = self._build_product_list_reply(session, customer_text, products, is_existing_contact)
                    reply_type = 'product_search'
                    matched = ', '.join(products.mapped('name')) if products else ''
                else:
                    # Short unrecognized message — re-prompt, keep context
                    reply = (
                        f"Would you like to order *{prev_reply.selected_product_id.name}*? 😊\n\n"
                        f"Reply *yes* to proceed with order, *no* to search for something else."
                    )
                    reply_type = 'product_detail'
                    selected_product = prev_reply.selected_product_id
                    matched = prev_reply.selected_product_id.name

        # --- FLOW: Customer gives quantity after "quantity_ask" ---
        elif prev_reply and prev_reply.reply_type == 'quantity_ask' and prev_reply.selected_product_id:
            if _is_no(stripped):
                reply = "Order cancelled. 😊 Feel free to search for another product anytime!"
                reply_type = 'general'
            elif _is_yes(stripped):
                # Customer re-confirmed without quantity — re-ask
                reply = (
                    f"How many units of *{prev_reply.selected_product_id.name}* would you like?\n"
                    f"Please reply with a number (e.g. *2*, *5* or say \"three\"). 🎤"
                )
                reply_type = 'quantity_ask'
                selected_product = prev_reply.selected_product_id
                matched = prev_reply.selected_product_id.name
            else:
                qty = self._parse_quantity(stripped)
                _bprod = prev_reply.selected_product_id
                _sok = True; _savail = 0
                if qty and qty > 0:
                    _sok, _savail = self._stock_check(session, _bprod, qty)
                if qty and qty > 0 and not _sok:
                    reply = self._stock_short_msg(session, _bprod, _savail)
                    reply_type = 'quantity_ask'
                    selected_product = _bprod
                    matched = _bprod.name
                elif qty and qty > 0:
                    product = prev_reply.selected_product_id
                    order = self._create_sale_order(session, conv, product, qty, is_existing_contact, unit_price=(prev_reply.offered_price or None))
                    if order:
                        price = prev_reply.offered_price or (product.list_price if is_existing_contact else product.wa_retail_price)
                        total = price * qty
                        reply, reply_type = self._route_after_order(session, conv, order, product, qty, price)
                        selected_product = product
                        matched = product.name
                    else:
                        reply = "Sorry, there was an issue creating your order. Our agent will assist you shortly! 🙏"
                        reply_type = 'general'
                else:
                    reply = (
                        f"Please reply with the quantity for *{prev_reply.selected_product_id.name}*.\n"
                        f"You can type a number (e.g. *5*) or say it (e.g. \"five units\"). 🎤"
                    )
                    reply_type = 'quantity_ask'
                    selected_product = prev_reply.selected_product_id
                    matched = prev_reply.selected_product_id.name if prev_reply.selected_product_id else ''

        # --- FLOW: Customer replies with product number (typed or voice-spoken) ---
        elif prev_reply and prev_reply.matched_products:
            product_num = self._parse_product_number(stripped)
            if product_num:
                result = self._get_selected_product(prev_reply, product_num, is_existing_contact)
                if result:
                    product, reply = result
                    reply_type = 'product_detail'
                    selected_product = product
                    matched = f'Product #{product_num}: {product.name}'
                else:
                    reply = self._build_product_detail_reply(session, prev_reply, product_num, is_existing_contact)
                    reply_type = 'product_detail'
                    matched = f'Product #{product_num} detail'
            else:
                # Number not detected — treat as new product search
                products = self._search_products(customer_text, session.auto_reply_max_products or 5)
                reply = self._build_product_list_reply(session, customer_text, products, is_existing_contact)
                reply_type = 'product_search'
                matched = ', '.join(products.mapped('name')) if products else ''

        # --- FLOW: New product search ---
        else:
            # Product search flow
            products = self._search_products(customer_text, session.auto_reply_max_products or 5)
            reply = self._build_product_list_reply(session, customer_text, products, is_existing_contact)
            reply_type = 'product_search'
            matched = ', '.join(products.mapped('name')) if products else ''

        # Send the reply
        status = 'sent'
        error = ''
        try:
            if conv.phone:
                self._dispatch_auto_reply(session, conv, reply, reply_type, selected_product, matched)
                _logger.info("Auto-reply (specific msg) sent to %s: %s", conv.phone, reply[:80])
            else:
                status = 'failed'
                error = 'No phone number'
        except Exception as e:
            status = 'failed'
            error = str(e)
            _logger.error("Failed to send auto-reply (specific msg) to %s: %s", conv.phone, e)

        self.create({
            'conversation_id': conv.id,
            'employee_session_id': session.id,
            'trigger_message_id': last_log.id,
            'phone': conv.phone,
            'customer_message': customer_text,
            'reply_message': reply,
            'matched_products': matched,
            'selected_product_id': selected_product.id if selected_product else False,
            'order_id': order.id if order else False,
            'reply_type': reply_type,
            'status': status,
            'error': error,
        })

    def _resolve_is_existing_contact(self, conv, last_log=None):
        """Check if phone number exists in Odoo contacts → wholesale, otherwise → retail.

        Simple rule:
        - conv.partner_id already linked (and not a ghost) → wholesale (True)
        - Phone number found in res.partner (phone or phone_sanitized) → wholesale (True)
        - Phone number NOT found or LID number → retail (False)
        """
        try:
            # Fast path: conversation already linked to a real partner
            if conv.partner_id:
                comment = (conv.partner_id.comment or '').lower()
                if 'auto-created from whatsapp' not in comment:
                    _logger.info("[CONTACT CHECK] Conv has real partner '%s' (ID=%s) → wholesale",
                                 conv.partner_id.name, conv.partner_id.id)
                    return True
                else:
                    _logger.info("[CONTACT CHECK] Conv partner is ghost '%s' → continue phone check",
                                 conv.partner_id.name)

            phone_to_check = conv.phone or ''
            clean_phone = ''.join(filter(str.isdigit, phone_to_check))

            # LID numbers (18+ digits) or clearly invalid (too short) → retail
            # Valid international numbers: 7–15 digits (ITU-T E.164 standard)
            # WhatsApp JIDs strip the '+' so a +91 XXXXX XXXXX = 12 digits is valid
            if len(clean_phone) < 5:
                _logger.info("[CONTACT CHECK] '%s' too short → retail", phone_to_check)
                return False

            if len(clean_phone) > 17:
                # True LID numbers are 18+ digits — not real phone numbers
                _logger.info("[CONTACT CHECK] '%s' appears to be LID (>17 digits) → retail", phone_to_check)
                return False

            # Search by last 5 digits in phone and phone_sanitized fields
            last_5 = clean_phone[-5:] if len(clean_phone) >= 5 else clean_phone
            _logger.info("[CONTACT CHECK] Searching for phone='%s' (digits='%s', last_5='%s')",
                         phone_to_check, clean_phone, last_5)

            # Odoo 19: res.partner has no 'mobile' field.
            # Use both 'phone' and 'phone_sanitized' (stores E.164 digits e.g. +919944080209)
            partners_by_phone = self.env['res.partner'].sudo().search([
                '&', ('phone', 'ilike', last_5), ('active', '=', True),
            ])
            partners_by_sanitized = self.env['res.partner'].sudo().search([
                '&', ('phone_sanitized', 'ilike', last_5), ('active', '=', True),
            ])
            partners = partners_by_phone | partners_by_sanitized

            _logger.info("[CONTACT CHECK] Candidates found: %d (phone=%d, sanitized=%d)",
                         len(partners), len(partners_by_phone), len(partners_by_sanitized))

            # Verify match: exact digits OR last-10-digit suffix (handles country code variants)
            for p in partners:
                # Skip ghost contacts auto-created by WhatsApp module — these are NOT real wholesale contacts
                comment = (p.comment or '').lower()
                if 'auto-created from whatsapp' in comment:
                    _logger.info("[CONTACT CHECK] SKIP ghost contact: '%s' (ID=%s)", p.name, p.id)
                    continue

                p_phone = ''.join(filter(str.isdigit, p.phone or ''))
                p_sanitized = ''.join(filter(str.isdigit, p.phone_sanitized or ''))
                matched = (
                    (p_phone and p_phone == clean_phone) or
                    (p_sanitized and p_sanitized == clean_phone) or
                    (len(p_phone) >= 7 and len(clean_phone) >= 7 and p_phone[-10:] == clean_phone[-10:]) or
                    (len(p_sanitized) >= 7 and len(clean_phone) >= 7 and p_sanitized[-10:] == clean_phone[-10:])
                )
                if matched:
                    _logger.info("[CONTACT CHECK] MATCH: partner='%s' (ID=%s) phone='%s' sanitized='%s' → wholesale",
                                 p.name, p.id, p_phone, p_sanitized)
                    return True
                else:
                    _logger.debug("[CONTACT CHECK] No match: partner='%s' phone='%s' sanitized='%s'",
                                  p.name, p_phone, p_sanitized)

            _logger.info("[CONTACT CHECK] No Odoo contact matched phone='%s' → retail", clean_phone)
            return False

        except Exception as e:
            _logger.error("[CONTACT CHECK] Error: %s", e, exc_info=True)
            return False

    def _build_product_list_reply(self, session, customer_text, products, is_existing_contact):
        """Build the product listing reply (same logic as inside _check_conversation)."""
        no_match_msg = session.auto_reply_no_match or \
            'Sorry, I could not find matching products. An agent will assist you shortly.'
        if not products:
            return (
                f"{no_match_msg}\n\n"
                "_(This is an automated reply. Our agent will be with you shortly.)_"
            )
        greeting = session.auto_reply_greeting or 'Hi! Thank you for reaching out. 😊'
        lines = [
            f"{greeting}\n",
            f"Here are the products I found for *\"{customer_text[:60]}\"*:\n",
        ]
        for i, p in enumerate(products, 1):
            price = p.list_price if is_existing_contact else p.wa_retail_price
            line = f"{i}. 📦 *{p.name}*"
            if price:
                line += f" — 💰 Rate: {price:.2f}"
            lines.append(line)
        lines.append("\nReply with the *number* (e.g. 1, 2, 3) to get more details about a product! 😊")
        lines.append("\n_(Price may vary, our assistant will contact you.)_")
        lines.append("\n_(This is an automated reply. Our agent will be with you shortly.)_")
        return '\n'.join(lines)

    def _check_conversation(self, conv, session, cutoff_time):
        """Check if a conversation needs auto-reply."""
        phone = conv.phone or ''
        if not phone or not phone.strip():

            return

        # Skip broadcast/status/group conversations
        if 'broadcast' in phone.lower() or 'status' in phone.lower() or 'g.us' in phone.lower():
            return

        # Get last message in conversation
        last_log = self.env['wa.communication.log'].search([
            ('conversation_id', '=', conv.id),
        ], order='message_date desc', limit=1)

        if not last_log:
            return

        # Only auto-reply if last message is INCOMING and older than timeout
        if last_log.direction != 'incoming':
            return  # Employee already replied

        # Check if we already auto-replied to this exact message
        existing = self.search([
            ('trigger_message_id', '=', last_log.id),
        ], limit=1)
        if existing:
            return  # Already handled

        if not last_log.message_date or last_log.message_date > cutoff_time:
            return  # Not yet timed out

        # Don't auto-reply to very old messages (older than 30 minutes)
        max_age = fields.Datetime.now() - timedelta(minutes=30)
        if last_log.message_date < max_age:
            return

        # For voice messages, use English translation for product search (falls back to transcription)
        if last_log.is_voice_message and last_log.voice_transcription:
            customer_text = last_log.voice_translation or last_log.voice_transcription
        else:
            customer_text = last_log.message_text or ''
        if not customer_text.strip() or customer_text.strip() == '[Voice Message]':
            return  # Empty or untranscribed voice message

        _logger.info("Auto-reply triggered for conv %s, phone %s: '%s'",
                     conv.id, conv.phone, customer_text[:50])

        stripped = customer_text.strip().lower()

        # Pure greeting — reply with greeting only, no product search
        greeting_words = {
            'hi', 'hello', 'hey', 'hii', 'hiii', 'helo', 'helo', 'hai',
            'good morning', 'good evening', 'good afternoon', 'good night',
            'greetings', 'howdy', 'sup', 'yo',
        }
        if stripped in greeting_words:
            greeting = session.auto_reply_greeting or 'Hi! Thank you for reaching out. 😊'
            reply = (
                f"{greeting}\n\n"
                f"How can I help you today? Please tell me what product you're looking for "
                f"and I'll find the best options for you! 🛍️\n\n"
                f"_(This is an automated reply. Our agent will be with you shortly.)_"
            )
            self._dispatch_auto_reply(session, conv, reply, 'greeting', None, '')
            self.create({
                'conversation_id': conv.id,
                'employee_session_id': session.id,
                'trigger_message_id': last_log.id,
                'phone': conv.phone,
                'customer_message': customer_text,
                'reply_message': reply,
                'reply_type': 'general',
                'status': 'sent',
            })
            return

        # Get last auto-reply for this conversation to understand context
        # IMPORTANT: must be BEFORE the current incoming message to get proper flow context
        prev_reply = self.search([
            ('conversation_id', '=', conv.id),
            ('status', '=', 'sent'),
            ('create_date', '<=', last_log.message_date),
        ], order='create_date desc', limit=1)

        # Determine if the sender is an existing contact (LID-aware)
        is_existing_contact = self._resolve_is_existing_contact(conv)

        # --- PRICE BARGAIN (handled early, returns) ---
        if (getattr(session, 'auto_reply_bargain_enabled', True)
                and prev_reply and prev_reply.selected_product_id
                and (prev_reply.reply_type == 'price_negotiate'
                     or (prev_reply.reply_type == 'product_detail'
                         and self._detect_bargain_intent(stripped)))):
            _bprod = prev_reply.selected_product_id
            _breply, _btype, _bprice = self._handle_bargain(
                session, prev_reply, stripped, is_existing_contact)
            try:
                self._dispatch_auto_reply(session, conv, _breply, _btype, _bprod, _bprod.name)
                _bstatus = 'sent'
            except Exception as _be:
                _logger.error("Bargain send failed: %s", _be)
                _bstatus = 'failed'
            self.create({
                'conversation_id': conv.id,
                'employee_session_id': session.id,
                'trigger_message_id': last_log.id,
                'phone': conv.phone,
                'customer_message': customer_text,
                'reply_message': _breply,
                'matched_products': _bprod.name,
                'selected_product_id': _bprod.id,
                'reply_type': _btype,
                'offered_price': _bprice,
                'status': _bstatus,
            })
            return

        # --- POST-ORDER: delivery address (early-handled) ---
        if prev_reply and prev_reply.reply_type in ('await_delivery', 'await_address') and prev_reply.order_id:
            _order = prev_reply.order_id.sudo()
            try:
                if prev_reply.reply_type == 'await_delivery' and stripped in ('addr_same', 'same', 'yes', 'y', 'same address'):
                    _addr = _order.partner_id.address_get(['delivery']).get('delivery') or _order.partner_id.id
                    _order.partner_shipping_id = _addr
                else:
                    self._wa_apply_address(_order, customer_text)
            except Exception as _de:
                _logger.error('Delivery address error: %s', _de)
            _r, _t = self._payment_or_finalize(session, conv, _order)
            self._dispatch_auto_reply(session, conv, _r, _t, None, '')
            self.create({
                'conversation_id': conv.id, 'employee_session_id': session.id,
                'trigger_message_id': last_log.id, 'phone': conv.phone,
                'customer_message': customer_text, 'reply_message': _r,
                'order_id': _order.id, 'reply_type': _t, 'status': 'sent'})
            return

        # --- POST-ORDER: payment (early-handled) ---
        if prev_reply and prev_reply.reply_type == 'await_payment' and prev_reply.order_id:
            _order = prev_reply.order_id.sudo()
            if stripped in ('cod', 'cash', 'cash on delivery', 'c.o.d', 'cashondelivery'):
                try:
                    _order.wa_payment_mode = 'cod'
                except Exception:
                    pass
                _order._wa_settle(paid=False)
                self.create({
                    'conversation_id': conv.id, 'employee_session_id': session.id,
                    'trigger_message_id': last_log.id, 'phone': conv.phone,
                    'customer_message': customer_text, 'reply_message': '[COD settled]',
                    'order_id': _order.id, 'reply_type': 'order_created', 'status': 'sent'})
                return
            elif stripped in ('upi', 'card', 'pay', 'pay online', 'online', 'pay_online'):
                _r = self._online_pay_msg(_order, stripped)
                _t = 'await_payment'
            else:
                _r, _t = self._payment_step(session, _order)
            self._dispatch_auto_reply(session, conv, _r, _t, None, '')
            self.create({
                'conversation_id': conv.id, 'employee_session_id': session.id,
                'trigger_message_id': last_log.id, 'phone': conv.phone,
                'customer_message': customer_text, 'reply_message': _r,
                'order_id': _order.id, 'reply_type': _t, 'status': 'sent'})
            return

        reply = ''
        reply_type = 'general'
        selected_product = None
        order = None
        matched = ''

        # --- FLOW: Customer says "yes"/"confirm"/"order" after product detail ---
        if prev_reply and prev_reply.reply_type == 'product_detail' and prev_reply.selected_product_id:
            if stripped in ('yes', 'y', 'ok', 'confirm', 'order', 'buy', 'yeah', 'yep', 'sure'):
                # Ask for quantity
                product = prev_reply.selected_product_id
                price = product.list_price if is_existing_contact else product.wa_retail_price
                reply = (
                    f"Great choice! 🎉\n\n"
                    f"📦 *{product.name}*\n"
                    f"💰 *Rate:* {price:.2f}\n\n"
                    f"How many units would you like to order? Please reply with the *quantity* (e.g. 1, 2, 5)."
                )
                reply_type = 'quantity_ask'
                selected_product = product
                matched = product.name
            elif stripped == 'no' or stripped == 'cancel':
                reply = (
                    "No problem! 😊 Feel free to ask about any other product. "
                    "Just type what you're looking for and I'll help you find it!"
                )
                reply_type = 'general'
            else:
                # Treat as new product search
                products = self._search_products(customer_text, session.auto_reply_max_products or 5)
                reply = self._build_reply(session, customer_text, products, is_existing_contact)
                reply_type = 'product_search'
                matched = ', '.join(products.mapped('name')) if products else ''

        # --- FLOW: Customer gives quantity after "quantity_ask" ---
        elif prev_reply and prev_reply.reply_type == 'quantity_ask' and prev_reply.selected_product_id:
            qty = self._parse_quantity(stripped)
            _bprod = prev_reply.selected_product_id
            _sok = True; _savail = 0
            if qty and qty > 0:
                _sok, _savail = self._stock_check(session, _bprod, qty)
            if qty and qty > 0 and not _sok:
                reply = self._stock_short_msg(session, _bprod, _savail)
                reply_type = 'quantity_ask'
                selected_product = _bprod
                matched = _bprod.name
            elif qty and qty > 0:
                product = prev_reply.selected_product_id
                # Create the Sale Order!
                order = self._create_sale_order(session, conv, product, qty, is_existing_contact, unit_price=(prev_reply.offered_price or None))
                if order:
                    price = prev_reply.offered_price or (product.list_price if is_existing_contact else product.wa_retail_price)
                    total = price * qty
                    reply, reply_type = self._route_after_order(session, conv, order, product, qty, price)
                    selected_product = product
                    matched = product.name
                else:
                    reply = "Sorry, there was an issue creating your order. Our agent will assist you shortly! 🙏"
                    reply_type = 'general'
            else:
                reply = "Please reply with a valid quantity number (e.g. *1*, *2*, *5*). 😊"
                reply_type = 'quantity_ask'
                selected_product = prev_reply.selected_product_id
                matched = prev_reply.selected_product_id.name if prev_reply.selected_product_id else ''

        # --- FLOW: Customer replies with product number (1, 2, 3...) ---
        elif prev_reply and prev_reply.matched_products and stripped.isdigit():
            product_num = int(stripped)
            result = self._get_selected_product(prev_reply, product_num, is_existing_contact)
            if result:
                product, reply = result
                reply_type = 'product_detail'
                selected_product = product
                matched = f'Product #{stripped}: {product.name}'
            else:
                reply = self._build_product_detail_reply(session, prev_reply, product_num, is_existing_contact)
                reply_type = 'product_detail'
                matched = f'Product #{stripped} detail'

        # --- FLOW: New product search ---
        else:
            products = self._search_products(customer_text, session.auto_reply_max_products or 5)
            reply = self._build_reply(session, customer_text, products, is_existing_contact)
            reply_type = 'product_search'
            matched = ', '.join(products.mapped('name')) if products else ''

        # Send via WhatsApp - supports both real numbers and LID
        status = 'sent'
        error = ''
        try:
            phone = conv.phone or ''
            if phone:
                self._dispatch_auto_reply(session, conv, reply, reply_type, selected_product, matched)
                _logger.info("Auto-reply sent to %s: %s", phone, reply[:80])
            else:
                status = 'failed'
                error = 'No phone number'
        except Exception as e:
            status = 'failed'
            error = str(e)
            _logger.error("Failed to send auto-reply to %s: %s", conv.phone, e)

        # Log the auto-reply
        self.create({
            'conversation_id': conv.id,
            'employee_session_id': session.id,
            'trigger_message_id': last_log.id,
            'phone': conv.phone,
            'customer_message': customer_text,
            'reply_message': reply,
            'matched_products': matched,
            'selected_product_id': selected_product.id if selected_product else False,
            'order_id': order.id if order else False,
            'reply_type': reply_type,
            'status': status,
            'error': error,
        })

    def _build_product_detail_reply(self, session, prev_reply, product_num, is_existing_contact):
        """Build detailed product info when customer replies with a number."""
        # Get the products from previous reply
        product_names = [p.strip() for p in (prev_reply.matched_products or '').split(',') if p.strip()]

        if product_num < 1 or product_num > len(product_names):
            return (
                f"Sorry, please reply with a number between *1* and *{len(product_names)}* "
                f"to select a product from the list above. 😊"
            )

        selected_name = product_names[product_num - 1]

        # Find the product in database
        product = self.env['product.template'].sudo().search([
            ('name', '=', selected_name),
            ('active', '=', True),
        ], limit=1)

        if not product:
            # Try partial match
            product = self.env['product.template'].sudo().search([
                ('name', 'ilike', selected_name[:30]),
                ('active', '=', True),
            ], limit=1)

        if not product:
            return f"Sorry, I couldn't find details for that product. Our agent will help you shortly! 🙏"

        # Build detailed product info
        lines = [f"📦 *{product.name}*"]
        lines.append('')

        price = product.list_price if is_existing_contact else product.wa_retail_price
        if price:
            lines.append(f"💰 *Rate:* {price:.2f}")

        if product.categ_id:
            lines.append(f"📂 *Category:* {product.categ_id.name}")

        if product.description_sale:
            desc = product.description_sale[:200]
            lines.append(f"📝 *Description:* {desc}")

        # Check stock if available
        try:
            if hasattr(product, 'qty_available') and not getattr(session, 'auto_reply_hide_quantity', False):
                qty = product.qty_available
                if qty > 0:
                    lines.append(f"✅ *In Stock:* {qty:.0f} units available")
                else:
                    lines.append("⚠️ *Stock:* Currently out of stock - please check with our agent")
        except Exception:
            pass

        lines.append('')
        lines.append("\nWould you like to place an order for this product? Reply *yes* to confirm or ask about another product! 😊")
        lines.append("\n_(Price may vary, our assistant will contact you.)_")
        lines.append("\n_(This is an automated reply. Our agent will be with you shortly.)_")

        return '\n'.join(lines)

    def _get_selected_product(self, prev_reply, product_num, is_existing_contact):
        """Get product from previous reply's product list by number."""
        product_names = [p.strip() for p in (prev_reply.matched_products or '').split(',') if p.strip()]

        if product_num < 1 or product_num > len(product_names):
            return None

        selected_name = product_names[product_num - 1]

        # Find the product
        product = self.env['product.template'].sudo().search([
            ('name', '=', selected_name),
            ('active', '=', True),
        ], limit=1)

        if not product:
            product = self.env['product.template'].sudo().search([
                ('name', 'ilike', selected_name[:30]),
                ('active', '=', True),
            ], limit=1)

        if not product:
            return None

        # Build detail reply
        lines = [f"📦 *{product.name}*"]
        lines.append('')

        price = product.list_price if is_existing_contact else product.wa_retail_price
        if price:
            lines.append(f"💰 *Price:* {price:.2f}")

        if product.categ_id:
            lines.append(f"📂 *Category:* {product.categ_id.name}")

        if product.description_sale:
            desc = product.description_sale[:200]
            lines.append(f"📝 *Description:* {desc}")

        try:
            if hasattr(product, 'qty_available') and not (prev_reply.employee_session_id and prev_reply.employee_session_id.auto_reply_hide_quantity):
                qty = product.qty_available
                if qty > 0:
                    lines.append(f"✅ *In Stock:* {qty:.0f} units available")
                else:
                    lines.append("⚠️ *Stock:* Currently out of stock")
        except Exception:
            pass

        lines.append('')
        lines.append("\nWould you like to order this product? Reply *yes* to proceed or type another product name to search! 😊")
        lines.append("\n_(Price may vary, our assistant will contact you.)_")
        lines.append("\n_(This is an automated reply. Our agent will be with you shortly.)_")

        return (product, '\n'.join(lines))

    # Word-to-number map shared by quantity parser and product number parser
    _WORD_TO_NUM = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14,
        'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18,
        'nineteen': 19, 'twenty': 20, 'thirty': 30, 'forty': 40,
        'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80,
        'ninety': 90, 'hundred': 100,
        # ordinals
        'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
        'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
        '1st': 1, '2nd': 2, '3rd': 3, '4th': 4, '5th': 5,
    }

    # Common phone autocorrect / typo variants that map to numbers
    _FUZZY_NUM = {
        # five
        'fai': 5, 'fie': 5, 'fiv': 5, 'fife': 5, 'fve': 5, 'fice': 5,
        # two
        'tow': 2, 'tw': 2, 'tue': 2, 'tow': 2, 'too': 2,
        # three
        'tree': 3, 'thee': 3, 'thre': 3, 'thr': 3, 'thrée': 3,
        # four
        'fore': 4, 'fur': 4, 'fir': 4, 'fo': 4,
        # six
        'sic': 6, 'si': 6, 'sec': 6,
        # seven
        'seve': 7, 'sevan': 7, 'sevem': 7,
        # eight
        'eigh': 8, 'eit': 8, 'egt': 8,
        # nine
        'nin': 9, 'nien': 9, 'nne': 9,
        # ten
        'tem': 10, 'tn': 10,
        # one
        'ine': 1, 'oje': 1, 'oné': 1,
    }

    def _word_to_int(self, text):
        """Convert word-based number to int, or return None if not found.
        Strips trailing punctuation and also checks fuzzy/autocorrect variants."""
        t = text.strip().lower().rstrip('.,!?')
        if t in self._WORD_TO_NUM:
            return self._WORD_TO_NUM[t]
        if t in self._FUZZY_NUM:
            return self._FUZZY_NUM[t]
        # "number one", "number 1", "option two", "no 3"
        for prefix in ('number ', 'option ', 'no ', 'no. ', '#'):
            if t.startswith(prefix):
                rest = t[len(prefix):].strip()
                if rest.isdigit():
                    return int(rest)
                if rest in self._WORD_TO_NUM:
                    return self._WORD_TO_NUM[rest]
                if rest in self._FUZZY_NUM:
                    return self._FUZZY_NUM[rest]
        return None

    def _parse_product_number(self, text):
        """Parse product selection number from text. Handles digits, voice-spoken words, typos."""
        t = text.strip().lower().rstrip('.,!?')
        if t.isdigit():
            return int(t)
        n = self._word_to_int(t)
        if n:
            return n
        # Extract first digit from mixed text like "i want number 2"
        nums = re.findall(r'\d+', t)
        if nums:
            return int(nums[0])
        # Word number anywhere in text e.g. "send me three"
        for word, num in self._WORD_TO_NUM.items():
            if re.search(r'\b' + word + r'\b', t):
                return num
        # Fuzzy match on single short word (autocorrect typos like "fai"→5)
        words = t.split()
        if len(words) == 1 and words[0] in self._FUZZY_NUM:
            return self._FUZZY_NUM[words[0]]
        return None

    def _parse_quantity(self, text):
        """Parse quantity from customer text, including voice-spoken and typo'd word numbers."""
        t = text.strip().lower().rstrip('.,!?')
        # Direct digit
        if t.isdigit():
            return int(t)
        # Word-based number (exact or prefix match)
        n = self._word_to_int(t)
        if n:
            return n
        # Extract digit from mixed text like "i want 5" or "5 pieces"
        numbers = re.findall(r'\d+', t)
        if numbers:
            return int(numbers[0])
        # Word number inside longer text e.g. "send me five units"
        for word, num in self._WORD_TO_NUM.items():
            if re.search(r'\b' + word + r'\b', t):
                return num
        # Fuzzy match on any token (handles autocorrect like "fai"→5)
        for token in t.split():
            if token in self._FUZZY_NUM:
                return self._FUZZY_NUM[token]
        return None

    def _create_sale_order(self, session, conv, product_template, qty, is_existing_contact, unit_price=None):
        """Create a sale order in Odoo from WhatsApp conversation."""
        try:
            # Find or create customer partner
            partner = self._get_or_create_partner(conv)

            # Get the product variant
            product = product_template.product_variant_id
            if not product:
                product = product_template.product_variant_ids[:1]
            if not product:
                _logger.error("No product variant found for template %s", product_template.name)
                return None

            # Create Sale Order
            order_vals = {
                'partner_id': partner.id,
                'origin': f'WhatsApp Auto-Reply ({conv.phone})',
                'note': f'Order created via WhatsApp auto-reply.\nEmployee: {session.employee_id.name}\nCustomer Phone: {conv.phone}\nCustomer Name: {conv.contact_name or ""}',
            }

            # Set company (config override, else session company)
            _co = getattr(session, 'auto_reply_company_id', False) or session.session_id.company_id
            if _co:
                order_vals['company_id'] = _co.id

            order = self.env['sale.order'].sudo().create(order_vals)

            if unit_price is not None:
                price = unit_price
            else:
                price = product_template.list_price if is_existing_contact else product_template.wa_retail_price

            # Add order line
            line_vals = {
                'order_id': order.id,
                'product_id': product.id,
                'product_uom_qty': qty,
                'price_unit': price,
                'product_uom_id': product.uom_id.id,
            }

            self.env['sale.order.line'].sudo().create(line_vals)

            _logger.info("Sale order %s created from WhatsApp for phone %s, product %s x%s (Price: %s)",
                         order.name, conv.phone, product_template.name, qty, price)

            return order

        except Exception as e:
            _logger.error("Failed to create sale order: %s", e)
            return None

    def _get_or_create_partner(self, conv):
        """Find or create a partner for the WhatsApp customer."""
        phone = conv.phone or ''
        contact_name = conv.contact_name or ''

        # One lookup for every module (res.partner._sa_phone_matches): other
        # modules override it, e.g. to keep unproven website accounts out.
        Partner = self.env['res.partner'].sudo()
        if phone:
            found = Partner._sa_phone_matches(phone)[:1]
            if found:
                return found

        # Create new partner - the number saved with "+", or a database in
        # another country reads 91... as one of its own local numbers
        name = contact_name or f'WhatsApp Customer ({phone})'
        partner = Partner.create({
            'name': name,
            'phone': Partner._sa_phone_e164(phone),
            'comment': f'Auto-created from WhatsApp conversation',
        })
        _logger.info("Created partner %s for WhatsApp phone %s", partner.name, phone)
        return partner

    def _parse_price(self, text):
        """Extract the first number from text as a float, or None."""
        import re as _re
        m = _re.findall(r'\d+(?:\.\d+)?', (text or '').replace(',', ''))
        if m:
            try:
                return float(m[0])
            except ValueError:
                return None
        return None

    def _detect_bargain_intent(self, text):
        """True if the customer message looks like a price negotiation."""
        t = (text or '').lower().strip()
        keywords = (
            'reduce', 'less', 'cheap', 'cheaper', 'discount', 'offer',
            'expensive', 'costly', 'best price', 'last price', 'final price',
            'lower', 'low price', 'bargain', 'kammi', 'can you do',
            'any discount', 'negotiate', 'deal', 'too high', 'high price',
        )
        if any(k in t for k in keywords):
            return True
        if self._parse_price(t) is not None and len(t.split()) <= 4:
            return True
        return False

    def _handle_bargain(self, session, prev_reply, stripped, is_existing_contact):
        """Return (reply_text, reply_type, offered_price) for a bargaining turn.
        New customers negotiate from MRP (wa_retail_price) down to, but never
        below, the sale price (list_price). Existing customers are already at
        the floor."""
        product = prev_reply.selected_product_id
        floor = product.list_price or 0.0
        mrp = product.wa_retail_price or floor
        accept = stripped in (
            'yes', 'y', 'ok', 'okay', 'confirm', 'accept', 'accept_price',
            'sure', 'deal', 'done', 'buy', 'order', 'proceed',
        )
        cancel = stripped in ('no', 'cancel', 'stop', 'nevermind', 'never mind')
        negotiating = prev_reply.reply_type == 'price_negotiate'

        if negotiating and accept:
            deal = prev_reply.offered_price or floor
            reply = (
                "Perfect! \U0001F91D Deal at *%.2f* for *%s*.\n\n"
                "How many units would you like? Reply with the *quantity* "
                "(e.g. 1, 2, 5)." % (deal, product.name)
            )
            return reply, 'quantity_ask', deal

        if negotiating and cancel:
            return ("No problem! \U0001F60A Type another product name to "
                    "search anytime.", 'general', 0.0)

        if is_existing_contact:
            reply = (
                "\U0001F4E6 *%s*\n\U0001F4B0 That's already our best price: "
                "*%.2f* \U0001F64F\n\nReply *yes* to order, or send another "
                "product name to search." % (product.name, floor)
            )
            return reply, 'product_detail', floor

        if negotiating and prev_reply.offered_price and prev_reply.offered_price <= floor:
            reply = (
                "I've given my best price *%.2f* for *%s*. \U0001F64F\n"
                "Our agent will contact you shortly to assist further."
                % (floor, product.name)
            )
            return reply, 'general', floor

        current = prev_reply.offered_price or mrp
        if not negotiating:
            current = mrp
        target = self._parse_price(stripped)
        if target is not None:
            if target >= current:
                offer = current
            elif target >= floor:
                offer = target
            else:
                offer = floor
        else:
            offer = round((current + floor) / 2.0, 2)
            if negotiating:
                offer = floor
        if offer < floor:
            offer = floor

        if offer <= floor:
            reply = (
                "\U0001F4E6 *%s*\n\U0001F4B0 Best I can do: *%.2f* \U0001F64F\n\n"
                "This is our final price. Reply *yes* to order." % (product.name, offer)
            )
        else:
            reply = (
                "\U0001F4E6 *%s*\n\U0001F4B0 Special price for you: *%.2f* "
                "(MRP %.2f) \U0001F389\n\nReply *yes* to accept, or send your "
                "price / *lower* to negotiate more." % (product.name, offer, mrp)
            )
        return reply, 'price_negotiate', offer

    def _stock_check(self, session, product, qty):
        """Return (ok, available). ok=True if not restricting or enough stock."""
        if not getattr(session, 'auto_reply_stock_restrict', False):
            return True, 0
        try:
            variant = product.product_variant_id or product.product_variant_ids[:1]
            avail = variant.sudo().qty_available
            return (qty <= avail), avail
        except Exception:
            return True, 0

    def _stock_short_msg(self, session, product, avail):
        if getattr(session, 'auto_reply_hide_quantity', False):
            return ("Sorry, that quantity isn't available right now. \U0001F64F\n"
                    "Please try a smaller quantity, or our agent will assist.")
        return ("Only *%d* units of *%s* are available.\n"
                "Please reply with a quantity up to %d." % (int(avail), product.name, int(avail)))

    def _route_after_order(self, session, conv, order, product, qty, price):
        """After a Sale Order is created, decide the next step."""
        try:
            order.sudo().write({
                'wa_conversation_id': conv.id if conv else False,
                'wa_employee_session_id': session.id,
            })
        except Exception:
            pass
        if getattr(session, 'auto_reply_ask_delivery', False):
            return self._delivery_step(order)
        return self._payment_or_finalize(session, conv, order)

    def _wa_apply_address(self, order, text):
        import re as _re
        p = order.partner_id.sudo()
        text = (text or '').strip()
        vals = {'street': text[:250]}
        _m = _re.search(r'\b(\d{5,6})\b', text)
        if _m:
            vals['zip'] = _m.group(1)
        _ghost = ('auto-created from whatsapp' in (p.comment or '').lower()
                  or (p.name or '').startswith('WhatsApp Customer'))
        if _ghost:
            _first = text.split(',')[0].strip()
            if _first and not _first.replace(' ', '').isdigit():
                vals['name'] = _first[:80]
        try:
            p.write(vals)
        except Exception as e:
            _logger.error('apply address: %s', e)
        order.partner_shipping_id = p.id

    def _delivery_step(self, order):
        p = order.partner_id
        if p.street:
            reply = ("\U0001F4CD *Where should we deliver?*\n\n"
                     "Tap *Same as my address*, or type your full delivery address with pincode.")
            return reply, 'await_delivery'
        reply = ("\U0001F4CD *Please share your delivery details* in one message:\n\n"
                 "*Name, Full Address, City, Pincode*\n\n"
                 "Example: Karthik, 13B Beach Road, Kollam, 691001")
        return reply, 'await_address'

    def _payment_or_finalize(self, session, conv, order):
        if getattr(session, 'auto_reply_payment_enabled', False):
            return self._payment_step(session, order)
        return ("✅ *Order placed!* \U0001F4CB %s — Total %.2f\n"
                "Our team will contact you shortly. \U0001F64F" % (order.name, order.amount_total),
                'order_created')

    def _pay_link(self, order):
        try:
            w = self.env['payment.link.wizard'].sudo().create({
                'res_model': 'sale.order', 'res_id': order.id,
                'amount': order.amount_total, 'currency_id': order.currency_id.id,
                'partner_id': order.partner_id.id,
            })
            return w.link or ''
        except Exception as e:
            _logger.warning("Payment link failed for SO %s: %s", order.id, e)
            return ''

    def _online_pay_msg(self, order, method):
        try:
            token = order.sudo()._portal_ensure_token()
        except Exception:
            token = order.sudo().access_token or ''
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url') or ''
        m = 'card' if method == 'card' else 'upi'
        url = "%s/wa/pay/%s?method=%s&token=%s" % (base, order.id, m, token)
        label = 'Card' if m == 'card' else 'UPI'
        return ("\U0001F4B3 Pay by %s here:\n%s\n\nComplete the quick payment and your "
                "invoice will be sent here automatically. ✅" % (label, url))

    def _payment_step(self, session, order):
        lines = ["\U0001F9FE *Order %s* — Total: *%.2f*" % (order.name, order.amount_total), ""]
        lines.append("Choose your payment method \U0001F447")
        _opts = ["UPI", "Card"]
        if getattr(session, 'auto_reply_cod_enabled', True):
            _opts.append("Cash on Delivery")
        lines.append("(or reply: " + " / ".join(_opts) + ")")
        return "\n".join(lines), 'await_payment'

    def _cod_confirm_msg(self, order):
        return ("✅ *Order Confirmed (Cash on Delivery)* \U0001F389\n\n"
                "\U0001F4CB *Order:* %s\n\U0001F4B5 *Total:* %.2f\n\n"
                "Your invoice is attached. Please pay on delivery. \U0001F69A"
                % (order.name, order.amount_total))

    def _finalize_order(self, session, conv, order, paid=False):
        """Confirm SO, create+post invoice, optionally register payment, send PDF."""
        try:
            if order.state in ('draft', 'sent'):
                order.sudo().action_confirm()
            inv = order.sudo().invoice_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
            if not inv:
                inv = order.sudo()._create_invoices()
            inv.filtered(lambda m: m.state == 'draft').action_post()
            if paid:
                reg = self.env['account.payment.register'].sudo().with_context(
                    active_model='account.move', active_ids=inv.ids).create({})
                reg._create_payments()
            pdf, _x = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
                'account.account_invoices', inv.ids)
            fname = ((inv[:1].name or 'Invoice').replace('/', '_')) + '.pdf'
            cap = 'Invoice (Paid)' if paid else 'Invoice - Pay on delivery'
            session.session_id.send_document(conv.phone, pdf, fname, caption=cap)
            return True
        except Exception as e:
            _logger.error("Finalize order %s failed: %s", order.id, e)
            return False

    def _dispatch_auto_reply(self, session, conv, reply, reply_type,
                             selected_product=None, matched=''):
        """Send the auto-reply as tappable WhatsApp buttons where possible.
        The reply text already contains a numbered list + instructions, so the
        customer can ALSO type a number / word. LID numbers and any button
        failure fall back to plain text."""
        phone = conv.phone or ''
        if not phone:
            raise Exception('No phone number')
        wa_session = session.session_id
        digits = ''.join(c for c in phone if c.isdigit())
        is_lid = len(digits) > 14  # buttons do not route reliably to LID

        def _plain():
            if reply_type == 'product_detail' and selected_product:
                self._send_product_with_image(session, phone, selected_product, reply)
            else:
                self._send_message_smart(session, phone, reply)

        if is_lid:
            _plain()
            return

        try:
            if reply_type == 'product_search':
                names = [n.strip() for n in (matched or '').split(',') if n.strip()]
                if not names:
                    self._send_message_smart(session, phone, reply)
                    return
                buttons = [{'id': str(i), 'title': n[:24]} for i, n in enumerate(names, 1)]
                wa_session.send_buttons(phone, reply, buttons, include_numbers=False)

            elif reply_type == 'product_detail' and selected_product:
                try:
                    self._send_product_with_image(session, phone, selected_product, reply)
                except Exception:
                    self._send_message_smart(session, phone, reply)
                buttons = [
                    {'id': 'yes', 'title': '✅ Order Now'},
                    {'id': 'lower', 'title': '\U0001F4AC Negotiate Price'},
                    {'id': 'no', 'title': '\U0001F50D Search Other'},
                ]
                wa_session.send_buttons(
                    phone, 'Reply *yes* to order, tap *Negotiate Price* for a deal, or search another product.',
                    buttons, include_numbers=False)

            elif reply_type == 'await_address':
                self._send_message_smart(session, phone, reply)

            elif reply_type == 'await_delivery':
                buttons = [{'id': 'addr_same', 'title': '✅ Same as my address'}]
                wa_session.send_buttons(phone, reply, buttons, include_numbers=False)

            elif reply_type == 'await_payment':
                _b = [{'id': 'upi', 'title': '📱 UPI'}, {'id': 'card', 'title': '💳 Card'}]
                if getattr(session, 'auto_reply_cod_enabled', True):
                    _b.append({'id': 'cod', 'title': '🚚 Cash on Delivery'})
                wa_session.send_buttons(phone, reply, _b, include_numbers=False)

            elif reply_type == 'price_negotiate':
                buttons = [
                    {'id': 'yes', 'title': '✅ Accept'},
                    {'id': 'lower', 'title': '💬 Lower price'},
                ]
                wa_session.send_buttons(phone, reply, buttons, include_numbers=False)

            elif reply_type == 'quantity_ask':
                buttons = [
                    {'id': '1', 'title': '1'},
                    {'id': '2', 'title': '2'},
                    {'id': '5', 'title': '5'},
                ]
                wa_session.send_buttons(phone, reply, buttons, include_numbers=False)

            elif reply_type in ('general', 'greeting'):
                prods = self.env['product.template'].sudo().search(
                    [('sale_ok', '=', True), ('active', '=', True)], limit=200)
                cats = prods.mapped('categ_id')[:3]
                buttons = [{'id': c.name, 'title': c.name[:24]} for c in cats if c.name]
                if buttons:
                    wa_session.send_buttons(phone, reply, buttons, include_numbers=False)
                else:
                    self._send_message_smart(session, phone, reply)
            else:
                self._send_message_smart(session, phone, reply)
        except Exception as e:
            _logger.warning("Button send failed (%s) - falling back to text: %s",
                            reply_type, e)
            _plain()

    def _send_message_smart(self, session, phone, message):
        """Send a WhatsApp message through the gateway.

        This used to assemble a neonize JID by hand and pick between the normal
        and the LID address space by counting digits. The gateway resolves
        addressing itself, and `send_message` already writes the
        whatsapp.message row - logging here as well would double every line in
        the message list.
        """
        return session.session_id.send_message(phone, message)

    def _send_product_with_image(self, session, phone, product, caption):
        """Send a product image, falling back to the caption on its own.

        The WebP-to-JPEG conversion that used to live here was working around
        neonize, which opened the image with PIL and could not sniff WebP.
        Nothing opens the image now - the bytes go to the gateway as they are,
        and it logs the message itself.
        """
        wa_session = session.session_id
        if product.image_1920:
            try:
                return wa_session.send_image(phone, product.image_1920, caption=caption)
            except Exception as err:  # noqa: BLE001 - a picture is not worth losing the reply over
                _logger.warning(
                    "Product image for '%s' would not send (%s) - sending the text instead.",
                    product.name, err)
        return wa_session.send_message(phone, caption)

    def _search_products(self, customer_text, max_results=5):
        """Search products matching customer message keywords."""
        # Clean and extract keywords
        text = customer_text.lower().strip()
        # Remove common words
        stop_words = {
            'i', 'need', 'want', 'looking', 'for', 'a', 'an', 'the', 'do',
            'you', 'have', 'any', 'please', 'hi', 'hello', 'hey', 'can',
            'get', 'me', 'is', 'there', 'it', 'this', 'that', 'what',
            'how', 'much', 'price', 'cost', 'available', 'stock', 'buy',
            'sir', 'madam', 'thanks', 'thank', 'ok', 'okay', 'yes', 'no',
            'good', 'morning', 'evening', 'afternoon', 'bro', 'dear',
        }

        # Extract meaningful words
        words = re.findall(r'[a-zA-Z0-9]+', text)
        keywords = [w for w in words if w.lower() not in stop_words and len(w) > 1]

        if not keywords:
            return self.env['product.template']

        _logger.info("Product search keywords: %s", keywords)

        # Strategy 1: Search with all keywords combined
        all_products = self.env['product.template']

        # Try full phrase first
        full_phrase = ' '.join(keywords)
        products = self.env['product.template'].search([
            ('sale_ok', '=', True),
            ('active', '=', True),
            ('name', 'ilike', full_phrase),
        ], limit=max_results)

        if products:
            return products

        # Try each keyword individually and score by matches
        product_scores = {}
        for kw in keywords:
            matches = self.env['product.template'].search([
                ('sale_ok', '=', True),
                ('active', '=', True),
                '|',
                ('name', 'ilike', kw),
                ('categ_id.name', 'ilike', kw),
            ], limit=50)
            for p in matches:
                product_scores[p.id] = product_scores.get(p.id, 0) + 1

        if not product_scores:
            return self.env['product.template']

        # Sort by score (most keyword matches first)
        sorted_ids = sorted(product_scores.keys(),
                           key=lambda pid: product_scores[pid],
                           reverse=True)[:max_results]

        return self.env['product.template'].browse(sorted_ids)

    def _build_reply(self, session, customer_text, products, is_existing_contact):
        """Build the auto-reply message."""
        greeting = session.auto_reply_greeting or 'Hi! Thank you for reaching out. 😊'

        if not products:
            # No exact match - suggest popular/alternative products
            alternatives = self._get_alternative_products(customer_text, session.auto_reply_max_products or 5)

            if alternatives:
                lines = [greeting]
                lines.append('')
                lines.append(f"We couldn't find an exact match for *\"{customer_text.strip()}\"*, but here are some products you might be interested in:")
                lines.append('')
                for i, product in enumerate(alternatives, 1):
                    price_str = ''
                    price = product.list_price if is_existing_contact else product.wa_retail_price
                    if price:
                        price_str = f' - *Price: {price:.2f}*'
                    lines.append(f'{i}. {product.name}{price_str}')
                lines.append('')
                lines.append("Would any of these work for you? Or feel free to describe what you're looking for and we'll find the best option! 🔍")
                lines.append('')
                lines.append('_(This is an automated reply. Our agent will be with you shortly.)_')
                return '\n'.join(lines)
            else:
                no_match = session.auto_reply_no_match or \
                    "We appreciate your interest! We're currently checking availability for your request. Our team will get back to you shortly with the best options. 🙏"
                return f"{greeting}\n\n{no_match}"

        lines = [greeting]
        lines.append('')
        lines.append("Great news! We have the following products matching your request:")
        lines.append('')

        for i, product in enumerate(products, 1):
            price_str = ''
            price = product.list_price if is_existing_contact else product.wa_retail_price
            if price:
                price_str = f' - *Price: {price:.2f}*'
            lines.append(f'{i}. {product.name}{price_str}')

        lines.append('')
        lines.append("Simply reply with the *product number* to know more, or let us know if you need something different! 😊")
        lines.append('')
        lines.append('_(This is an automated reply. Our agent will be with you shortly.)_')

        return '\n'.join(lines)

    def _get_alternative_products(self, customer_text, max_results=5):
        """Get alternative/popular products when no exact match is found."""
        # Try to find products from broader categories
        text = customer_text.lower().strip()
        words = re.findall(r'[a-zA-Z0-9]+', text)

        # Remove all stop words to get core keywords
        stop_words = {
            'i', 'need', 'want', 'looking', 'for', 'a', 'an', 'the', 'do',
            'you', 'have', 'any', 'please', 'hi', 'hello', 'hey', 'can',
            'get', 'me', 'is', 'there', 'it', 'this', 'that', 'what',
            'how', 'much', 'price', 'cost', 'available', 'stock', 'buy',
            'sir', 'madam', 'thanks', 'thank', 'ok', 'okay', 'yes', 'no',
            'good', 'morning', 'evening', 'afternoon', 'bro', 'dear',
        }
        keywords = [w for w in words if w.lower() not in stop_words and len(w) > 1]

        if not keywords:
            # If no keywords, return some popular/recent products
            return self.env['product.template'].sudo().search([
                ('sale_ok', '=', True),
                ('active', '=', True),
                ('list_price', '>', 0),
            ], order='write_date desc', limit=max_results)

        # Try matching by category name
        categories = self.env['product.category'].sudo().search([
            ('name', 'ilike', keywords[0]),
        ])

        if categories:
            products = self.env['product.template'].sudo().search([
                ('categ_id', 'in', categories.ids),
                ('sale_ok', '=', True),
                ('active', '=', True),
            ], limit=max_results)
            if products:
                return products

        # Try single keyword partial match on product name
        for kw in keywords:
            products = self.env['product.template'].sudo().search([
                ('name', 'ilike', kw),
                ('sale_ok', '=', True),
                ('active', '=', True),
            ], limit=max_results)
            if products:
                return products

        # Fallback: popular products
        return self.env['product.template'].sudo().search([
            ('sale_ok', '=', True),
            ('active', '=', True),
            ('list_price', '>', 0),
        ], order='write_date desc', limit=max_results)