# WhatsApp Modules — Feature Roadmap

**Comparing our WhatsApp suite (`whatsapp_gateway` + `whatsapp_employee_tracker` + `whatsapp_broadcast` + `whatsapp_easy_integration`) against TeleCRM.**

This document lists what TeleCRM has that we don't, ranks the missing features by ROI, and describes the technical approach for each one in plain language (no code).

---

## Purpose

A team-internal planning document. Anyone reading this should be able to:
- See at a glance which TeleCRM features we already match
- Understand what's missing
- Pick the next feature to build with a clear scope, file list, and effort estimate
- Avoid building features that don't fit our customers' actual workflow

---

## Current state — what we already have

| Capability | Module | Notes |
|---|---|---|
| Send WhatsApp from any sale / purchase / invoice / payment / easy.sales | `whatsapp_gateway` + `whatsapp_easy_integration` | Click "📱 Send via WhatsApp & Email" button on any record |
| Receive WhatsApp + auto-save messages | `whatsapp_gateway` | Every message logged with partner auto-match |
| Multi-session support | `whatsapp_gateway` | Each Odoo DB can have multiple WhatsApp numbers |
| Voice note auto-transcription + auto-translate to English | `whatsapp_gateway` (Phase AG) | Tamil/Malayalam/Hindi → English in the chat list |
| Group chat with friendly names | `whatsapp_gateway` (Phase AC) | Group "Family" instead of "+12036…" |
| Bulk WhatsApp broadcast | `whatsapp_broadcast` | Send to 100s of contacts |
| Lead-finder from Google Maps | `whatsapp_broadcast` | Scrape leads + send intro WhatsApp |
| Employee chat monitoring + tone analysis | `whatsapp_employee_tracker` | Supervisors see all employee chats, tone score, response time |
| Auto-reply rules | `whatsapp_employee_tracker` | Keyword-based auto-responses |
| Credit-approval workflow via WhatsApp + Email | `credit_management_system` | Manager replies `1-ORDER` → auto-approves |
| Payment receipts auto-sent | `whatsapp_gateway` | After payment posted, customer gets receipt |
| Invoice reminders | `whatsapp_gateway` cron | Daily check, reminders at -7/-3/-1/0/+3/+7/+14/+30 days |
| Sales pipeline (new → won/lost) | `alphalize_crm` | Standard CRM stages |
| Followup activities | Odoo `mail.activity` | "Schedule Activity" button on every record |

---

## What TeleCRM has that we don't

### Group A — Small wins (1–3 days each)

#### A1. Click-to-WhatsApp from CRM Lead

**Problem:** A new lead arrives. The salesperson has to copy the phone number, switch to WhatsApp, paste, type a greeting. Today our "📱 Send via WhatsApp" button only appears on Sale Order, Purchase Order, Invoice, etc. — not on `crm.lead`.

**Technical approach:**
- The reusable mixin `whatsapp.email.sendable.mixin` already exists in `whatsapp_gateway/models/easy_orders_send.py`. It powers the button on easy.sales, invoice, payment, etc.
- Extend `crm.lead` with the same mixin. Inherit the model, set the document emoji (📞) and document label ("Lead").
- Add a small view inherit XML that injects the button into the `crm.lead` form header next to the existing "Convert to Opportunity" button.
- Wizard logic, send flow, chatter logging — all unchanged. Just plugging the lead model into the existing infrastructure.

**Files to touch:**
- New file: a small extension model (e.g. `whatsapp_gateway/models/crm_lead.py`)
- New file: form-view inherit (`whatsapp_gateway/views/crm_lead_views.xml`)
- Manifest: register the new view file, bump version

**Effort:** ~½ day
**Dependencies:** the `crm` Odoo core module must be installed (it is, since `alphalize_crm` depends on it)
**Risk:** very low — copying a working pattern

---

#### A2. Quick-reply template library

**Problem:** Salespeople type the same opening message 50 times a day: "Hi, thanks for your interest in our products, I'm Arun from Alphalize, when would be a good time to talk?" Should be a dropdown.

**Technical approach:**
- Create a new model `whatsapp.template` with fields: `name`, `category` (greeting / followup / closing / etc), `body_html`, `language`, `is_active`.
- Each template body supports placeholders like `{{partner_name}}`, `{{user_name}}` — same syntax Odoo's mail templates use. Use the existing `mail.template`'s `_render_template_qweb_view` helper rather than rolling our own renderer.
- Add a `template_id` Many2one field on the existing `whatsapp.send.message.wizard`. When user picks a template, an `onchange` fills the `message` field with the rendered text. User can edit before sending.
- Add a small menu under WhatsApp → Configuration → Message Templates so admins can manage the library.
- Access rights: salespeople can read, managers can create/edit.

**Files to touch:**
- New file: `whatsapp_gateway/models/whatsapp_template.py` (the model)
- New file: `whatsapp_gateway/views/whatsapp_template_views.xml` (list + form + menu)
- New row: `whatsapp_gateway/security/ir.model.access.csv` (2 lines: user-read, manager-write)
- Modify: `whatsapp_gateway/wizards/send_message_wizard.py` (add template_id field + onchange)
- Modify: `whatsapp_gateway/wizards/send_message_wizard_views.xml` (add template dropdown above the message field)
- Manifest: register view + version bump

**Effort:** ~1 day
**Dependencies:** none beyond what's already installed
**Risk:** low. Optional gotcha: WhatsApp Business API "templates" are different (Meta-approved, billable). Our templates are just text snippets — not subject to Meta approval because we're using the WhatsApp Web protocol via neonize.

---

#### A3. Auto-create CRM Lead from new incoming WhatsApp

**Problem:** A new phone number messages us asking "is this product available?" — today nobody acts on it because there's no record in CRM. The salesperson sees it only in the WA Tracker chat list and may miss it. With this feature, every NEW phone (no matching `res.partner` and no existing `wa.conversation`) auto-creates a `crm.lead` so it appears in the sales pipeline.

**Technical approach:**
- In `whatsapp_gateway/models/whatsapp_session.py`, both `_on_message` handlers already detect when sender is unknown. Today they save the `whatsapp.message` row but don't create anything in CRM.
- After saving the message, check: does any `res.partner` match this phone (last 10 digits)? If yes → done, attach to that partner. If no → check whether we've seen this phone in the last N days. If new → create a `crm.lead` with:
  - `name` = "WhatsApp Lead — <push_name or phone>"
  - `phone` = the cleaned phone number
  - `source_id` = a new `utm.source` named "WhatsApp" (created in module data so it's reusable)
  - `description` = the first incoming message body (gives sales rep context)
  - `team_id` = optionally configurable per session (so leads from different WhatsApp numbers route to different sales teams)
- Add a feature flag on `whatsapp.config`: "Auto-create CRM Lead from new chats" (Boolean, default OFF). When OFF, we keep today's behavior. When ON, the create runs.
- Optional: a cooldown — don't create a duplicate lead if one was already created for this phone in last 30 days.

**Files to touch:**
- Modify: `whatsapp_gateway/models/whatsapp_session.py` (the two `_on_message` handlers — add lead-creation block)
- Modify: `whatsapp_gateway/models/whatsapp_config.py` (add the Boolean flag)
- Modify: `whatsapp_gateway/views/whatsapp_config_views.xml` (UI toggle)
- New file: `whatsapp_gateway/data/utm_source_whatsapp.xml` (creates the utm.source record once)
- Manifest: register data file + bump version

**Effort:** ~1 day
**Dependencies:** Odoo core `crm` + `utm` modules (both already installed)
**Risk:** medium — if customer-service WhatsApp messages flood in, CRM could fill up with junk leads. The feature flag mitigates this; cooldown helps further. Recommend keeping default OFF and turning ON per customer.

---

### Group B — Medium wins (1 week each, do after Group A is shipping)

#### B1. Agent performance dashboard

**Problem:** Supervisors today see individual chats in `whatsapp_employee_tracker` but no rolled-up stats. They can't answer "who responded fastest this week?" or "whose chats convert into sales?"

**Technical approach:**
- Build a new model `wa.agent.daily.stats` (one row per employee per day). Fields:
  - `employee_id`, `date`
  - `chats_handled`, `messages_sent`, `messages_received`
  - `avg_response_time_minutes` (avg gap between an incoming message and the rep's reply)
  - `conversions_count` (sale.order records where `partner_id` matches a customer this rep chatted with, in the same day)
  - `tone_score_avg` (already computed by employee_tracker — pull it through)
- Build a daily cron that aggregates from `wa.communication.log` + `sale.order` and inserts/updates one row per agent per day.
- Build a pivot view (employee × date × metric) and a graph view (bar chart by employee).
- Add menu: WhatsApp & Email → Reporting → Agent Performance.
- Add filters: this week / this month / by team / by department.

**Files to touch:**
- New file: `whatsapp_employee_tracker/models/agent_stats.py`
- New file: `whatsapp_employee_tracker/data/ir_cron_agent_stats.xml`
- New file: `whatsapp_employee_tracker/views/agent_stats_views.xml`
- Modify: `whatsapp_employee_tracker/__manifest__.py` (register + version bump)

**Effort:** ~1 week (1 day model, 2 days aggregation logic + cron, 1 day views/charts, 1 day testing)
**Dependencies:** `hr` (employee) already required by tracker
**Risk:** low — pure read aggregation, no destructive writes. The aggregation must be efficient — paginate by employee to avoid loading 100k logs in one transaction.

---

#### B2. Auto-assign incoming chats to agents

**Problem:** All incoming WhatsApp messages today go to whoever pairs the session. A team of 5 sales reps can't share the inbox — they each see the same chats and either duplicate effort or ignore "someone else's" chat.

**Technical approach:**
- Add `wa.agent.queue` model — a configurable list of which employees handle which session, with optional working hours.
- When a new conversation gets created (in `_get_or_create` of `wa.conversation`), pick an assignee using one of these strategies (admin chooses on `whatsapp.config`):
  - **Round-robin** — keep a counter, pick the next employee
  - **Least-busy** — count open (active-today) conversations per employee, assign to the one with fewest
  - **Working hours** — only assign to employees whose working hours include "now"
  - **By keyword** — sales keywords → sales rep, support keywords → support rep (advanced, may skip for v1)
- Show the assigned agent on the WA Tracker chat list (column "Assigned To").
- Show a notification dot in the agent's top-right when a new chat is assigned to them.

**Files to touch:**
- New file: `whatsapp_employee_tracker/models/agent_queue.py`
- New file: `whatsapp_employee_tracker/views/agent_queue_views.xml`
- Modify: `whatsapp_employee_tracker/models/conversation.py` (`_get_or_create` — add assignment logic)
- Modify: `whatsapp_employee_tracker/views/conversation_views.xml` (show Assigned To column)

**Effort:** ~1 week
**Dependencies:** none new
**Risk:** medium — wrong assignments will be visible to customers ("Hi, this is Mary — wait no, John handles this account"). Mitigation: re-assignment button so a manager can manually re-route a conversation.

---

#### B3. Smart followup reminders from chat content

**Problem:** A salesperson types "I'll send you the quote on Tuesday" — but forgets to set a reminder. The deal goes cold.

**Technical approach:**
- After every OUTGOING WhatsApp message, run the message text through a tiny LLM (Groq or Gemini, free tier) with a prompt like: "Does this message contain a future commitment (a date/time the sender is promising)? If yes, output ISO datetime. If no, output NONE."
- If the LLM returns a datetime, create a `mail.activity` on the `wa.conversation` record (or on the linked `res.partner`/`crm.lead`) with type "Follow-up" and deadline = the extracted datetime.
- The activity shows up in the agent's "My Activities" view at the right time.
- Add a feature flag on `whatsapp.config`: "Smart followup reminders" (default OFF — calls LLM API per outgoing message → adds cost).
- Throttle: only run on messages > 20 chars to avoid spending API tokens on "OK".

**Files to touch:**
- New file: `whatsapp_gateway/models/smart_followup.py` (the extractor + activity creator)
- Modify: `whatsapp_gateway/models/whatsapp_session.py` (call the extractor after saving an outgoing message)
- Modify: `whatsapp_gateway/models/whatsapp_config.py` (add the feature flag + threshold field)
- New file: `whatsapp_gateway/views/whatsapp_config_views.xml` (add toggle + threshold to existing config form)

**Effort:** ~1 week (3 days prompt engineering + testing for date extraction accuracy across English/Hinglish/Arabic; 2 days integration)
**Dependencies:** Groq API key already configured (Phase AG)
**Risk:** medium — LLM may extract wrong dates (e.g. "I called you Tuesday" → past tense, no reminder needed). Mitigation: classifier is a Boolean "is this a future commitment?" before date extraction. False positives create harmless reminders the agent can dismiss.

---

### Group C — Big projects (2–3 weeks each, skip unless customer-funded)

#### C1. Phone calling integration

**Problem:** TeleCRM's main feature is in-app voice calls. We have zero.

**Technical approach (sketch — would be its own multi-page document if pursued):**
- Pick a cloud-telephony provider:
  - **Exotel** (India-focused, cheap, well-documented)
  - **Twilio** (global, more expensive, best docs)
  - **Plivo** (between the two)
  - **MyOperator** (India)
- For Oman/UAE: check provider geographical coverage — Twilio has presence; Exotel does not.
- Build a `phone.call` model that records every outbound call: agent, customer, duration, recording URL.
- Build a click-to-call widget — small button on every contact/lead/sale-order/etc. Clicking triggers the provider's API to:
  1. Ring the agent's mobile number
  2. When agent answers, ring the customer's mobile
  3. Bridge the two
  4. Record the conversation
  5. Webhook back to Odoo with call status + recording URL
- Build a webhook controller to receive call status events.
- Build a list view of all calls (today / this week / per agent).
- Optional: Whisper transcription of the recording (we already have Whisper integration via Phase AG).

**Effort:** ~3 weeks for v1 (basic click-to-call + recording log); +1 week for auto-dialer; +1 week for transcription
**Recurring cost:** telephony provider — typical $0.005–0.015 per minute of call + monthly number rental ~$1–5
**Risk:** high — this is the riskiest project. Telephony has many edge cases (one-way audio, call drops, regulatory compliance in Oman/UAE which restrict VoIP). Recommend a 1-day spike with one provider before committing.

**Recommendation:** Only build if a paying customer commits to use this feature. Don't speculatively build.

---

#### C2. Auto-dialer

**Problem:** After one call ends, dial the next lead automatically. Sales reps doing cold-calling want this.

**Technical approach:** Depends entirely on C1 being built first. Once we have outbound calling via a provider's API, auto-dialer is a queue: pick next lead with status=new from a campaign, trigger click-to-call, wait for call-ended webhook, repeat.

**Effort:** ~1 week on top of C1.

---

#### C3. Mobile-first agent app

**Problem:** The Odoo web UI works on phones but is clunky. TeleCRM's mobile app is dedicated to chat-first workflow.

**Technical approach:** Build a PWA mirroring the WA Tracker split-view, optimized for portrait phone screens. Reuse the offline_sync PWA infrastructure already in this codebase (`offline_sync/static/pwa/`). The PWA talks to Odoo via the existing controllers in `whatsapp_employee_tracker/controllers/` plus possibly new endpoints for chat send.

**Effort:** ~3 weeks for v1 (chat list + chat view + send text + send media); +1 week for voice-note recording; +1 week for offline send queue.

**Recommendation:** Defer. Odoo's web is good enough for 80% of cases. Build only if a customer specifically asks.

---

## What we will NOT build

- **WhatsApp Business API (Meta)** — we use the unofficial Web protocol via neonize. Going to the Business API means: monthly cost, message-template pre-approval, per-message billing, business verification. The trade-off is officially supported messaging vs. free. We've chosen free.
- **WhatsApp video calls / voice calls** — neonize doesn't support these. WhatsApp itself doesn't expose them in the Web protocol.
- **WeChat** — see Phase AG predecessor discussion. Not viable for Oman/UAE/India unless customer is targeting China specifically.
- **SMS** — Odoo has core `sms` module. If a customer asks, point them at it. We're not maintaining a parallel SMS module.

---

## Recommended sequence

1. **Now / This week:** ship Group A (A1 + A2 + A3) — total ~2.5 days work, immediate user-visible improvements
2. **Next month:** ship Group B (B1 + B2 + B3) one at a time — total ~3 weeks. Most ROI per week of work.
3. **Quarterly review:** revisit Group C. If a customer has committed budget for phone calling → start C1. Otherwise hold.

---

## Open questions for product owner

Before starting Group A, confirm:

1. **Which customers / DBs get auto-create-lead enabled?** (Default OFF in code; turn ON per customer.)
2. **Template library — who owns the content?** Salespeople write their own, or someone in marketing produces them centrally?
3. **For auto-assigned chats (B2) — what's the team size?** If 5+ agents, round-robin makes sense. If 1–2, skip.
4. **For phone calling (C1) — is this real customer demand or a speculative feature?** Don't start without a name attached.

---

## Document maintenance

- Update this file each time a feature ships (move from "missing" to "Current state" table at top).
- Add new rows to the comparison table if TeleCRM (or a competitor) ships a feature that's relevant to our customers.
- Keep effort estimates honest. If something takes longer than estimated, update the next similar estimate.

---

*Last updated: 2026-05-27.*
*Based on TeleCRM (telecrm.in) feature list as of 2026, our module versions: `whatsapp_gateway 19.0.2.3.4`, `whatsapp_employee_tracker 19.0.1.1.0`.*
