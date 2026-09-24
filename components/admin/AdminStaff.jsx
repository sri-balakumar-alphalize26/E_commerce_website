"use client";
/* ==========================================================================
   369 Mart admin — Staff & roles (Owner only)

   Who works here and what each person may do. The twin of Odoo's
   369 Mart > Store > Staff & roles: both call the same model methods, which set
   the same groups the user form's Role line sets, so the three can never
   disagree about someone's role.

   Role is one choice (each includes the one before); Accountant and Rider are
   ticks, because one person can hold two jobs.
   ========================================================================== */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useResource } from "@/lib/useFetch";
import { Drawer, Empty, Icon, Search } from "./AdminUI";
import { since } from "./format";

const ROLES = [["user", "User"], ["packer", "Packer"], ["manager", "Manager"], ["owner", "Owner"]];
const TONE = { user: "grey", packer: "orange", manager: "blue", owner: "violet" };
const label = (k) => (ROLES.find(([key]) => key === k) || ROLES[0])[1];

export function StaffSection({ flash }) {
  const [term, setTerm] = useState("");
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState(null);

  useEffect(() => {
    const id = setTimeout(() => setQ(term.trim()), 300);
    return () => clearTimeout(id);
  }, [term]);

  const { data, loading, error, reload } = useResource("/admin/staff" + (q ? `?q=${encodeURIComponent(q)}` : ""), { keepLast: true });
  const rows = data?.rows || [];
  const counts = data?.counts || {};
  const help = data?.help || {};

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        {ROLES.map(([k, l]) => (
          <span key={k}><small>{l}</small><b>{counts[k] ?? 0}</b><i>{help[k] || ""}</i></span>
        ))}
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <div className="ad-toolbar-right">
            <Search value={term} onChange={setTerm} placeholder="Name or email" />
            <button className="ad-btn ad-primary" onClick={() => setEdit({ invite: true, name: "", email: "", role: "packer", accountant: false, rider: false })}>
              <Icon n="plus" size={16} />Invite staff
            </button>
          </div>
        </div>
        <div className="ad-table-wrap">
          {error && !rows.length && <Empty icon="info" title="We could not reach the shop" text={error.message} action="Try again" onAction={reload} />}
          {loading && !rows.length && !error && <Empty icon="users" title="Loading…" text="Fetching staff." />}
          {!!rows.length && (
            <table className="ad-table">
              <thead><tr><th>Name</th><th>Role</th><th>Also</th><th>Shops</th><th>Last sign-in</th><th /></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.id} style={{ "--i": i % 12 }} onClick={(e) => { if (!e.target.closest("button")) setEdit({ ...r, companies: r.companies.map((c) => c.id) }); }}>
                    <td><b>{r.name}{r.me ? " (you)" : ""}</b><br /><small>{r.email}</small></td>
                    <td><span className={"ad-pill ad-t-" + (TONE[r.role] || "grey")}><i />{label(r.role)}</span></td>
                    <td><small>{[r.accountant && "Accountant", r.rider && "Rider"].filter(Boolean).join(", ") || "—"}</small></td>
                    <td><small>{r.companies.map((c) => c.name).join(", ")}</small></td>
                    <td><small>{r.lastSeen ? since(r.lastSeen) : "Not signed in yet"}</small></td>
                    <td className="ad-row-act"><button className="ad-icon-btn" onClick={() => setEdit({ ...r, companies: r.companies.map((c) => c.id) })} aria-label={`Change ${r.name}`}><Icon n="right" size={16} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!error && !loading && !rows.length && <Empty icon="users" title="Nobody matches" text="Try another name or email." />}
        </div>
      </section>

      {edit && <StaffDrawer edit={edit} help={help} companies={data?.companies || []} flash={flash}
        onClose={() => setEdit(null)} onSaved={() => { setEdit(null); api.invalidate("/admin/staff"); reload(); }} />}
    </div>
  );
}

function StaffDrawer({ edit, help, companies, flash, onClose, onSaved }) {
  const [f, setF] = useState(edit);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const toggleCo = (id) => set("companies", f.companies.includes(id) ? f.companies.filter((c) => c !== id) : [...f.companies, id]);

  const save = async () => {
    setBusy(true); setErr("");
    try {
      if (f.invite) {
        await api("/admin/staff/invite", { method: "POST", body: { name: f.name, email: f.email, role: f.role, accountant: f.accountant, rider: f.rider } });
        flash?.(`${f.name} added. An email to set a password is on its way.`);
      } else {
        await api(`/admin/staff/${f.id}`, { method: "POST", body: { role: f.role, accountant: f.accountant, rider: f.rider, companies: f.companies } });
        flash?.(`Saved: ${f.name} is now ${label(f.role)}.`);
      }
      onSaved();
    } catch (e) {
      setErr(e.message || "That did not save.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer title={f.invite ? "Invite staff" : f.name} sub={f.invite ? "They get an email to set a password" : f.email} onClose={onClose}
      foot={(close) => <><button className="ad-btn" onClick={close}>Cancel</button><button className="ad-btn ad-primary" disabled={busy} onClick={save}>{f.invite ? "Send invite" : "Save"}</button></>}>
      <div className="ad-form">
        {f.invite && (
          <>
            <label className="ad-field ad-span2"><span>Name</span><input value={f.name} onChange={(e) => set("name", e.target.value)} placeholder="Full name" /></label>
            <label className="ad-field ad-span2"><span>Email</span><input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} placeholder="They sign in with this" /></label>
          </>
        )}
      </div>
      <section className="ad-dsec">
        <h4>Role — pick one</h4>
        <div className="ad-rows">
          {ROLES.map(([k, l]) => (
            <label key={k} className="ad-row-set" style={{ cursor: "pointer" }}>
              <input type="radio" name="role" checked={f.role === k} onChange={() => set("role", k)} />
              <span className="ad-row-txt"><b>{l}</b><small>{help[k]}</small></span>
            </label>
          ))}
        </div>
      </section>
      <section className="ad-dsec">
        <h4>Also does — tick any</h4>
        <div className="ad-rows">
          <label className="ad-row-set" style={{ cursor: "pointer" }}>
            <input type="checkbox" checked={!!f.accountant} onChange={(e) => set("accountant", e.target.checked)} />
            <span className="ad-row-txt"><b>Accountant</b><small>Payments, wallets, invoices, refunds and reports.</small></span>
          </label>
          <label className="ad-row-set" style={{ cursor: "pointer" }}>
            <input type="checkbox" checked={!!f.rider} onChange={(e) => set("rider", e.target.checked)} />
            <span className="ad-row-txt"><b>Rider</b><small>Delivers orders and closes them with the customer's code.</small></span>
          </label>
        </div>
      </section>
      {!f.invite && companies.length > 1 && (
        <section className="ad-dsec">
          <h4>Works in</h4>
          <div className="ad-rows">
            {companies.map((c) => (
              <label key={c.id} className="ad-row-set" style={{ cursor: "pointer" }}>
                <input type="checkbox" checked={f.companies.includes(c.id)} onChange={() => toggleCo(c.id)} />
                <span className="ad-row-txt"><b>{c.name}</b></span>
              </label>
            ))}
          </div>
        </section>
      )}
      {err && <p className="ad-hint"><Icon n="info" size={14} />{err}</p>}
    </Drawer>
  );
}
