"use client";
/* ==========================================================================
   369 Mart — the footer's pages: Terms, Privacy, About, FAQs, Contact,
   Delivery areas... Written in Odoo (369 Mart > Page building > Info pages)
   and drawn here in the shop's own look: the title, the text as it was
   formatted, and what the page type adds - questions to search, the shop's
   phone and email, the pincodes it serves. The other pages of the same footer
   column sit beside it.
   ========================================================================== */
import "./infopage.css";
import { useContext, useEffect, useMemo, useState } from "react";
import { Crumbs } from "./Browse";
import { Icon } from "./shared";
import { NavContext } from "./nav";
import { openChat } from "./support";
import { useResource } from "@/lib/useFetch";
import { toSafeHtml } from "@/lib/safeHtml";

function Rich({ html, className = "ip-rich" }) {
  const [safe, setSafe] = useState(null);
  useEffect(() => setSafe(toSafeHtml(html)), [html]);
  return safe ? <div className={className} dangerouslySetInnerHTML={{ __html: safe }} /> : null;
}

function Faqs({ items }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(0);
  const hits = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? items.filter((f) => (f.q + " " + f.a).toLowerCase().includes(t)) : items;
  }, [items, q]);
  return (
    <section className="ip-faqs">
      <label className="ip-search"><Icon n="search" size={17} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search the questions" aria-label="Search the questions" />
      </label>
      {hits.length ? hits.map((f, i) => (
        <div key={f.q} className={"ip-faq" + (open === i ? " ip-open" : "")}>
          <button onClick={() => setOpen(open === i ? -1 : i)} aria-expanded={open === i}>
            <span>{f.q}</span><Icon n="chev" size={16} />
          </button>
          {open === i && <Rich html={f.a} className="ip-rich ip-answer" />}
        </div>
      )) : <p className="ip-none">No question matches “{q}”. <button className="ip-link" onClick={() => openChat(q)}>Ask us in the chat</button></p>}
    </section>
  );
}

function Contact({ c }) {
  return (
    <section className="ip-contact">
      <button className="ip-card ip-chat" onClick={() => openChat()}>
        <span><Icon n="chat" size={20} /></span><b>Chat with us</b><small>The quickest way - we reply right here</small>
      </button>
      {c.phone && <a className="ip-card" href={`tel:${c.phone.replace(/\s+/g, "")}`}><span><Icon n="phone" size={20} /></span><b>{c.phone}</b><small>Call us</small></a>}
      {c.email && <a className="ip-card" href={`mailto:${c.email}`}><span><Icon n="mail" size={20} /></span><b>{c.email}</b><small>Write to us</small></a>}
      {c.address && <div className="ip-card ip-addr"><span><Icon n="pin" size={20} /></span><b>{c.name}</b><small>{c.address}</small></div>}
    </section>
  );
}

function Areas({ rows }) {
  const [pin, setPin] = useState("");
  const shown = pin.trim() ? rows.filter((r) => pin.trim().startsWith(r.pincode) || r.pincode.startsWith(pin.trim())) : rows;
  if (!rows.length) return null;
  return (
    <section className="ip-areas">
      <label className="ip-search"><Icon n="pin" size={17} />
        <input value={pin} inputMode="numeric" onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="Your pincode" aria-label="Your pincode" />
      </label>
      <table>
        <thead><tr><th>Area</th><th>Pincode</th><th>Delivery</th></tr></thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.pincode}>
              <td>{r.name || "—"}</td>
              <td>{r.pincode}</td>
              <td>{[r.quick && `Quick${r.eta ? " · " + r.eta : ""}`, r.express && "Express"].filter(Boolean).join(" and ") || "—"}</td>
            </tr>
          ))}
          {!shown.length && <tr><td colSpan={3}>We don&apos;t deliver to {pin} yet.</td></tr>}
        </tbody>
      </table>
    </section>
  );
}

export default function InfoPage({ slug }) {
  const nav = useContext(NavContext);
  const { data, loading, error } = useResource(`/pages/${encodeURIComponent(slug || "")}`, { deps: [slug] });
  const p = data && data.ok !== false ? data : null;

  if (!p && loading) return <div className="co-skel" aria-label="Loading"><span /><span /><span /></div>;
  if (!p) {
    return (
      <div className="ls-empty" role="alert">
        <h3>{error?.status === 404 || data?.ok === false ? "This page isn't here" : "We can't reach the store"}</h3>
        <p>{error?.status === 404 || data?.ok === false ? "It may have moved. The footer lists every page." : error?.message}</p>
        <button className="ls-primary" onClick={() => nav("home")}>Back to the shop</button>
      </div>
    );
  }
  return (
    <div className="ip-page">
      <Crumbs items={[["Home", ["home"]], [p.title]]} />
      <div className="ip-grid">
        <article className="ip-main">
          <h1>{p.title}</h1>
          {p.summary && <p className="ip-sum">{p.summary}</p>}
          <Rich html={p.html} />
          {p.kind === "faqs" && <Faqs items={p.faqs || []} />}
          {p.kind === "contact" && p.contact && <Contact c={p.contact} />}
          {p.kind === "areas" && <Areas rows={p.areas || []} />}
          {p.updated && <p className="ip-updated">Last updated {new Date(p.updated).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" })}</p>}
        </article>
        {p.siblings?.length > 1 && (
          <aside className="ip-side" aria-label="More pages">
            {p.siblings.map((s) => (
              <button key={s.slug} className={s.slug === p.slug ? "ip-on" : ""} onClick={() => nav("page", s.slug)}>
                {s.label}<Icon n="right" size={14} />
              </button>
            ))}
          </aside>
        )}
      </div>
    </div>
  );
}
