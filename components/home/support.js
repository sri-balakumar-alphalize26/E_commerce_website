/* ==========================================================================
   369 Mart — the support panel's side of the helpdesk.

   This file used to be the brain: forty regular expressions over what the
   customer typed, answering out of the orders and wallet the browser happened
   to be holding. Its own header said to replace it with a real endpoint and
   keep the return shape, and that is exactly what happened - the shapes below
   are the ones SupportBot.jsx already drew, so the panel did not change.

   The part that matters is "Talk to an agent". The panel used to say
   "Finding an available agent…", then "Anjali joined the chat", then note the
   problem against an order. No agent existed and nothing was noted. Asking
   for a person now opens a real ticket, and everything said afterwards is
   kept on it - so an operator picking it up sees the conversation instead of
   making the customer type it twice, and closing the tab no longer loses it.
   ========================================================================== */
import { api } from "@/lib/api";

/* Names the panel prints in its own chrome. What either of them actually
   says comes from the shop. */
export const BOT_NAME = "Mitra";
export const AGENT_NAME = "Anjali";

/* {text, chips?, agent?, ticket?} - and `agent` means they had already asked
   for a person, so the panel picks that conversation up rather than greeting
   them as if nothing had happened. */
export const greeting = () => api("/support/greeting", { fresh: true });

/* {text, actions?, chips?, agent?} - the four fields the panel copies. */
export const ask = (text) => api("/support/chat", { method: "POST", body: { text } });

/* Opens the ticket. `reply` is a bare string: the person's first line. */
export const callAgent = (text) => api("/support/agent", { method: "POST", body: { text } });

/* A message to whoever is handling it; `reply` is again a bare string. */
export const tellAgent = (text) => api("/support/agent/say", { method: "POST", body: { text } });
