"use client";
/* ==========================================================================
   369 Mart — Support bot (floating button + chat)
   Button  white rounded square, bottom-right; headset bot face (option 3).
           Idle: gentle bob, eyes blink and glance, mic light pulses.
           Hover: head tilts. Sits above the green cart pill when it's shown.
           After a few seconds (once per visit) a "Need help?" bubble pops out
           and the bot waves; unread dot until the chat is opened.
   Chat    grows from the button (transform + opacity only — no blur, no
           clip-path), messages rise in, typing dots, quick-topic chips,
           action buttons that open the order / wallet / offers, and a
           "Talk to an agent" hand-off with a queue bar.
           Esc / close / backdrop (phones) shrinks it back into the button.
   Brain   the shop's own helpdesk, through support.js. Asking for a person
           opens a real ticket and everything said after that is kept on it.
   ========================================================================== */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon } from "./shared";
import { AGENT_NAME, BOT_NAME, ask, callAgent, greeting, tellAgent } from "./support";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const CHAT_KEY = "369mart.chat";
const HINT_KEY = "369mart.botHint";
const ss = {
  get: (k, f) => { try { return JSON.parse(sessionStorage.getItem(k) || "null") ?? f; } catch (e) { return f; } },
  set: (k, v) => { try { sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};
const clock = (t) => new Date(t).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });

/* option 3 — headset support bot */
export function BotFace({ className = "" }) {
  return (
    <svg className={"sb-face " + className} viewBox="0 0 64 64" aria-hidden="true">
      <path className="sb-band" d="M9 34V28a23 23 0 0 1 46 0v6" />
      <g className="sb-head">
        <rect x="14" y="14" width="36" height="36" rx="13" fill="#0a78ab" />
        <rect x="16" y="15.5" width="32" height="12" rx="6" fill="#fff" opacity=".12" />
        <rect x="19" y="23" width="26" height="15" rx="7.5" fill="#e9f6fc" />
        <g className="sb-eyes">
          <circle cx="26" cy="30.5" r="3.4" fill="#083b59" />
          <circle cx="38" cy="30.5" r="3.4" fill="#083b59" />
        </g>
        <rect className="sb-mouth" x="27" y="42" width="10" height="3" rx="1.5" fill="#e9f6fc" opacity=".85" />
      </g>
      <rect className="sb-cup sb-l" x="5" y="28" width="9" height="15" rx="4.5" fill="#f7931e" />
      <rect className="sb-cup sb-r" x="50" y="28" width="9" height="15" rx="4.5" fill="#f7931e" />
      <path className="sb-boom" d="M54 43c0 8-6 11-14 11" />
      <rect className="sb-mic" x="33" y="50.5" width="9" height="6" rx="3" fill="#f7931e" />
    </svg>
  );
}

function Msg({ m, onChip, onAction, last }) {
  if (m.from === "sys") {
    return (
      <div className={"sb-sys" + (m.queue ? " sb-queue" : "")}>
        {m.queue && <i className="sb-qbar"><em /></i>}
        <span>{m.text}</span>
      </div>
    );
  }
  const mine = m.from === "me";
  return (
    <div className={"sb-msg " + (mine ? "sb-mine" : m.from === "agent" ? "sb-agent" : "sb-bot")}>
      {!mine && <span className="sb-ava">{m.from === "agent" ? AGENT_NAME[0] : <BotFace />}</span>}
      <div className="sb-bubble-col">
        <p>{m.text}</p>
        {!!m.actions?.length && (
          <div className="sb-actions">
            {m.actions.map((a, k) => (
              <button key={a.label} style={{ "--k": k }} onClick={() => onAction(a)}>{a.label}<Icon n="right" size={14} /></button>
            ))}
          </div>
        )}
        <time>{clock(m.at)}</time>
        {last && !!m.chips?.length && (
          <div className="sb-chips">
            {m.chips.map((c, k) => <button key={c} style={{ "--k": k }} onClick={() => onChip(c)}>{c}</button>)}
          </div>
        )}
      </div>
    </div>
  );
}

export default function SupportBot({ onNav, hidden = false, lift = 0 }) {
  const [phase, setPhase] = useState("closed"); /* closed | open | closing */
  const [msgs, setMsgs] = useState([]);
  const [typing, setTyping] = useState(false);
  const [agent, setAgent] = useState(false);
  const [text, setText] = useState("");
  const [hint, setHint] = useState(false);
  const [unread, setUnread] = useState(false);
  const [wave, setWave] = useState(false);
  const panel = useRef(null);
  const fab = useRef(null);
  const list = useRef(null);
  const input = useRef(null);
  const timers = useRef([]);
  const later = (fn, ms) => { const t = setTimeout(fn, reduced() ? Math.min(ms, 60) : ms); timers.current.push(t); return t; };
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  /* restore this visit's chat; greet hint once per visit */
  useEffect(() => {
    const saved = ss.get(CHAT_KEY, null);
    if (saved?.msgs?.length) { setMsgs(saved.msgs); setAgent(!!saved.agent); }
    if (!ss.get(HINT_KEY, false)) {
      const t1 = setTimeout(() => { setHint(true); setUnread(true); setWave(true); setTimeout(() => setWave(false), 1600); }, 3500);
      const t2 = setTimeout(() => setHint(false), 11000);
      return () => { clearTimeout(t1); clearTimeout(t2); };
    }
  }, []);
  useEffect(() => { if (msgs.length) ss.set(CHAT_KEY, { msgs: msgs.slice(-60), agent }); }, [msgs, agent]);
  useEffect(() => { list.current?.scrollTo({ top: list.current.scrollHeight, behavior: reduced() ? "auto" : "smooth" }); }, [msgs, typing, phase]);

  const push = (m) => setMsgs((l) => [...l, { at: Date.now(), ...m }]);

  /* The shop cannot answer someone it does not know - every support route
     needs an account - so a guest is told that rather than being left with a
     panel that says nothing. */
  const offline = (e) =>
    push({ from: "sys", text: e?.status === 401
      ? "Sign in and I can help with your orders, refunds and payments."
      : "I couldn't reach support just now. Try again in a moment." });

  const open = () => {
    if (phase !== "closed") return;
    setHint(false); setUnread(false); ss.set(HINT_KEY, true);
    setPhase("open");
    if (msgs.length) return;
    setTyping(true);
    greeting()
      .then((g) => {
        setTyping(false);
        /* They asked for a person earlier; the ticket is the transcript. */
        if (g.agent && g.ticket) {
          setAgent(true);
          const said = (g.ticket.messages || []).map((m) => ({ ...m, at: m.at || Date.now() }));
          setMsgs(said.length ? said : [{ at: Date.now(), from: "agent", text: g.text }]);
          return;
        }
        push({ from: "bot", text: g.text, chips: g.chips });
      })
      .catch((e) => { setTyping(false); offline(e); });
  };
  useLayoutEffect(() => {
    if (phase !== "open" || !panel.current) return;
    const el = panel.current;
    void el.offsetWidth; /* commit the start state so the grow transition runs */
    el.classList.add("sb-in");
    const t = setTimeout(() => input.current?.focus({ preventScroll: true }), 260);
    return () => clearTimeout(t);
  }, [phase]);
  const close = (after) => {
    if (phase !== "open") return;
    panel.current?.classList.remove("sb-in");
    setPhase("closing");
    setTimeout(() => { setPhase("closed"); fab.current?.focus({ preventScroll: true }); after?.(); }, reduced() ? 0 : 240);
  };
  useEffect(() => {
    if (phase !== "open") return;
    const k = (e) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }); // eslint-disable-line
  useEffect(() => { if (hidden && phase !== "closed") setPhase("closed"); }, [hidden]); // eslint-disable-line

  /* This is where a ticket is really opened. The queue bar stays, because
     there is now something to wait for. */
  const connectAgent = (about) => {
    push({ from: "sys", text: "Finding an available agent…", queue: true });
    callAgent(about)
      .then((r) => {
        setAgent(true);
        push({ from: "sys", text: `${AGENT_NAME} joined the chat` });
        setTyping(true);
        later(() => { setTyping(false); push({ from: "agent", text: r.reply }); }, 900);
      })
      .catch((e) => offline(e));
  };

  const send = (raw) => {
    const q = (raw ?? text).trim();
    if (!q || typing) return;
    setText("");
    push({ from: "me", text: q });
    setTyping(true);
    const answer = agent ? tellAgent(q) : ask(q);
    answer
      .then((r) => {
        setTyping(false);
        if (agent) { push({ from: "agent", text: r.reply }); return; }
        push({ from: "bot", text: r.text, actions: r.actions, chips: r.chips });
        if (r.agent) later(() => connectAgent(q), 400);
      })
      .catch((e) => { setTyping(false); offline(e); });
  };
  const onAction = (a) => close(() => onNav?.(a.go[0], a.go[1] ?? null));
  const restart = () => {
    timers.current.forEach(clearTimeout); timers.current = [];
    setAgent(false); setTyping(false); ss.set(CHAT_KEY, null);
    setMsgs([]); setTyping(true);
    greeting()
      .then((g) => { setTyping(false); setMsgs([{ at: Date.now(), from: "bot", text: g.text, chips: g.chips }]); })
      .catch((e) => { setTyping(false); setMsgs([]); offline(e); });
  };

  const isOpen = phase !== "closed";
  const lastBot = [...msgs].reverse().find((m) => m.from !== "me" && m.from !== "sys");

  return (
    <div className={"sb" + (hidden ? " sb-hidden" : "")}>
      <div className={"sb-dock sb-lift" + lift + (isOpen ? " sb-under" : "")}>
        {hint && !isOpen && (
          <div className="sb-hint">
            <button className="sb-hint-main" onClick={open}><b>Hi! Need help?</b><span>Ask {BOT_NAME} about orders, refunds or delivery</span></button>
            <button className="sb-hint-x" aria-label="Dismiss" onClick={() => { setHint(false); ss.set(HINT_KEY, true); }}><Icon n="x" size={12} /></button>
          </div>
        )}
        <button ref={fab} className={"sb-fab" + (wave ? " sb-wave" : "")} onClick={open}
          aria-label={unread ? "Chat with support, 1 new message" : "Chat with support"} aria-haspopup="dialog" aria-expanded={isOpen} tabIndex={hidden ? -1 : 0}>
          <span className="sb-bob"><BotFace /></span>
          {unread && <em className="sb-dot">1</em>}
        </button>
      </div>

      {isOpen && (
        <>
          <div className="sb-back" onClick={() => close()} />
          <section ref={panel} className="sb-panel" role="dialog" aria-modal="false" aria-label="369 Mart support chat">
            <header className="sb-head">
              <span className={"sb-head-ava" + (agent ? " sb-is-agent" : "")}>{agent ? AGENT_NAME[0] : <BotFace />}<i /></span>
              <span className="sb-head-txt">
                <b>369 Mart Support</b>
                <small key={agent ? "a" : "b"}>{agent ? `${AGENT_NAME} · Support agent` : `${BOT_NAME} · replies instantly`}</small>
              </span>
              <button className="sb-hbtn" onClick={restart} aria-label="Start a new chat" title="New chat"><Icon n="reorder" size={17} /></button>
              <button className="sb-hbtn" onClick={() => close()} aria-label="Close chat"><Icon n="chev" size={20} /></button>
            </header>
            <div className="sb-list" ref={list} aria-live="polite">
              <p className="sb-day">Today</p>
              {msgs.map((m, i) => <Msg key={`${i}-${m.at}`} m={m} last={m === lastBot && !typing} onChip={send} onAction={onAction} />)}
              {typing && (
                <div className="sb-msg sb-bot sb-typing-row">
                  <span className="sb-ava">{agent ? AGENT_NAME[0] : <BotFace />}</span>
                  <p className="sb-typing" aria-label="Typing"><i /><i /><i /></p>
                </div>
              )}
            </div>
            <form className="sb-send" onSubmit={(e) => { e.preventDefault(); send(); }}>
              <input ref={input} value={text} onChange={(e) => setText(e.target.value)} placeholder={agent ? `Message ${AGENT_NAME}` : "Type your question"} aria-label="Message" maxLength={300} />
              <button type="submit" className={text.trim() ? "sb-ready" : ""} disabled={!text.trim() || typing} aria-label="Send"><Icon n="right" size={18} /></button>
            </form>
            <p className="sb-foot"><Icon n="lock" size={11} />{agent ? "Kept with your support ticket" : "Chats are saved for this visit only"}</p>
          </section>
        </>
      )}
    </div>
  );
}
