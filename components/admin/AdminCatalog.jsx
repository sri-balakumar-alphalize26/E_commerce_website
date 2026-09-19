"use client";
/* ==========================================================================
   369 Mart admin — Products (inventory) · Customers · Riders
   ========================================================================== */
import { useMemo, useState } from "react";
import ProductArt from "../home/art";
import { Avatar, Drawer, Empty, Icon, Pill, Search, Select, Switch, Tabs } from "./AdminUI";
import { CUSTOMERS, RIDERS, byId, clock, dateShort, groupIN, inr, isToday, since } from "./adminData";

const Thumb = ({ p }) => {
  const full = byId[p.id] || p;
  const src = (full.images && full.images[0]) || full.image;
  return <span className="ad-thumb">{src ? <img src={src} alt="" loading="lazy" /> : <ProductArt art={full.art} color={full.color} label={full.label} />}</span>;
};

/* ============================== products =============================== */
function AddProduct({ onClose, onAdd }) {
  const [f, setF] = useState({ name: "", unit: "", price: "", mrp: "", cat: "Fruits & Vegetables", qty: "24", delivery: false });
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const ok = f.name.trim().length > 2 && +f.price > 0 && f.unit.trim();
  return (
    <Drawer title="Add a product" sub="It goes live in the app as soon as it's saved" onClose={onClose}
      foot={(close) => (
        <>
          <button className="ad-btn" onClick={close}>Cancel</button>
          <button className="ad-btn ad-primary" disabled={!ok} onClick={() => { onAdd({ ...f, price: +f.price, mrp: +f.mrp || +f.price, qty: +f.qty || 0 }); close(); }}>Save product</button>
        </>
      )}>
      <div className="ad-form">
        <label className="ad-field ad-span2"><span>Product name</span><input value={f.name} onChange={set("name")} placeholder="e.g. Nendran Banana 1 kg" /></label>
        <label className="ad-field"><span>Pack / unit</span><input value={f.unit} onChange={set("unit")} placeholder="1 kg" /></label>
        <label className="ad-field"><span>Category</span>
          <select value={f.cat} onChange={set("cat")}>{["Fruits & Vegetables", "Atta, Rice & Staples", "Snacks & Beverages", "Personal Care", "Home & Kitchen", "Electronics"].map((c) => <option key={c}>{c}</option>)}</select>
        </label>
        <label className="ad-field"><span>Selling price (₹)</span><input inputMode="numeric" value={f.price} onChange={set("price")} placeholder="99" /></label>
        <label className="ad-field"><span>MRP (₹)</span><input inputMode="numeric" value={f.mrp} onChange={set("mrp")} placeholder="120" /></label>
        <label className="ad-field"><span>Opening stock</span><input inputMode="numeric" value={f.qty} onChange={set("qty")} /></label>
        <label className="ad-field"><span>Delivery</span>
          <select value={f.delivery ? "express" : "quick"} onChange={(e) => setF({ ...f, delivery: e.target.value === "express" })}>
            <option value="quick">Quick · 10–20 min</option><option value="express">Express · 2–5 days</option>
          </select>
        </label>
        <p className="ad-hint ad-span2"><Icon n="info" size={14} />Images, tax and HSN are filled in from the product master when this is wired to your ERP.</p>
      </div>
    </Drawer>
  );
}

export function ProductsSection({ stock, setQty, setPrice, toggleProduct, addProduct, flash }) {
  const [tab, setTab] = useState("all");
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const [sort, setSort] = useState("low");
  const [adding, setAdding] = useState(false);
  const [edit, setEdit] = useState(null);

  const cats = useMemo(() => [...new Set(stock.map((s) => s.cat))].sort(), [stock]);
  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return stock
      .filter((s) => (tab === "all" || (tab === "low" ? s.qty <= s.reorder && s.qty > 0 : tab === "out" ? s.qty === 0 : !s.active))
        && (cat === "all" || s.cat === cat)
        && (!term || s.name.toLowerCase().includes(term)))
      .sort((a, b) => (sort === "low" ? a.qty - b.qty : sort === "sold" ? b.sold7 - a.sold7 : sort === "price" ? b.price - a.price : a.name.localeCompare(b.name)));
  }, [stock, tab, cat, sort, q]);
  const count = (k) => stock.filter((s) => (k === "low" ? s.qty <= s.reorder && s.qty > 0 : k === "out" ? s.qty === 0 : !s.active)).length;
  const value = stock.reduce((s, p) => s + p.qty * p.price, 0);

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Products</small><b>{stock.length}</b></span>
        <span><small>Stock value</small><b>{inr(value)}</b></span>
        <span className="ad-warn"><small>Low stock</small><b>{count("low")}</b></span>
        <span className="ad-bad"><small>Out of stock</small><b>{count("out")}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["all", "All", stock.length], ["low", "Low", count("low")], ["out", "Out of stock", count("out")], ["off", "Hidden", count("off")]]} />
          <div className="ad-toolbar-right">
            <Search value={q} onChange={setQ} placeholder="Search products" />
            <Select value={cat} onChange={setCat} label="Category" options={[["all", "All categories"], ...cats.map((c) => [c, c])]} />
            <Select value={sort} onChange={setSort} label="Sort" options={[["low", "Lowest stock"], ["sold", "Best selling"], ["price", "Highest price"], ["name", "Name A–Z"]]} />
            <button className="ad-btn ad-primary" onClick={() => setAdding(true)}><Icon n="plus" size={16} />Add product</button>
          </div>
        </div>

        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead><tr><th>Product</th><th>Category</th><th>Delivery</th><th className="ad-num">Price</th><th className="ad-num">Sold / 7d</th><th className="ad-num">In stock</th><th>Live</th><th /></tr></thead>
            <tbody>
              {rows.slice(0, 40).map((s, i) => (
                <tr key={s.id} style={{ "--i": i % 12 }} className={s.qty === 0 ? "ad-row-bad" : s.qty <= s.reorder ? "ad-row-warn" : ""}>
                  <td>
                    <span className="ad-cell-person"><Thumb p={s} /><span><b>{s.name}</b><small>{s.unit}</small></span></span>
                  </td>
                  <td><small>{s.cat}</small></td>
                  <td><span className={"ad-tag " + (s.delivery ? "ad-tag-e" : "ad-tag-q")}>{s.delivery ? "Express" : "Quick"}</span></td>
                  <td className="ad-num">
                    <input className="ad-inline-num" value={s.price} inputMode="numeric" aria-label={`Price of ${s.name}`}
                      onChange={(e) => setPrice(s.id, Math.max(0, +e.target.value.replace(/\D/g, "") || 0))} />
                  </td>
                  <td className="ad-num">{s.sold7}</td>
                  <td className="ad-num">
                    <span className="ad-stepper">
                      <button onClick={() => setQty(s.id, s.qty - 1)} aria-label="Decrease">−</button>
                      <b key={s.qty}>{s.qty}</b>
                      <button onClick={() => setQty(s.id, s.qty + 1)} aria-label="Increase">+</button>
                    </span>
                  </td>
                  <td><Switch on={s.active} onChange={() => toggleProduct(s.id)} label={`${s.name} live`} /></td>
                  <td className="ad-row-act">
                    <button className="ad-btn ad-sm" onClick={() => { setQty(s.id, s.qty + 50); flash(`50 units added to ${s.name}`); }}>Restock 50</button>
                    <button className="ad-icon-btn" onClick={() => setEdit(s)} aria-label={`Details for ${s.name}`}><Icon n="right" size={16} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty icon="layers" title="No products match" text="Change the tab, category or search." />}
        </div>
      </section>

      {adding && <AddProduct onClose={() => setAdding(false)} onAdd={addProduct} />}
      {edit && (
        <Drawer title={edit.name} sub={`${edit.unit} · ${edit.cat}`} onClose={() => setEdit(null)}
          foot={(close) => <><button className="ad-btn" onClick={close}>Close</button><button className="ad-btn ad-primary" onClick={() => { setQty(edit.id, edit.qty + 50); flash("Stock updated"); close(); }}>Restock 50</button></>}>
          <div className="ad-prod-hero"><Thumb p={edit} /><div><b>{inr(edit.price)}</b>{edit.mrp > edit.price && <s>{inr(edit.mrp)}</s>}<small>{edit.sold7} sold in the last 7 days</small></div></div>
          <div className="ad-kv">
            <span><small>In stock</small>{edit.qty}</span>
            <span><small>Reorder level</small>{edit.reorder}</span>
            <span><small>Delivery</small>{edit.delivery ? "Express" : "Quick"}</span>
            <span><small>Status</small>{edit.active ? "Live in app" : "Hidden"}</span>
          </div>
          <p className="ad-hint"><Icon n="info" size={14} />Full product editing (images, description, tax, HSN) happens in the product master once this is connected.</p>
        </Drawer>
      )}
    </div>
  );
}

/* ============================== customers ============================== */
export function CustomersSection({ orders, flash }) {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState("all");
  const [open, setOpen] = useState(null);
  const rows = CUSTOMERS.filter((c) => (tab === "all" || c.status.toLowerCase() === tab) && (!q.trim() || (c.name + c.email + c.area).toLowerCase().includes(q.toLowerCase())));
  const count = (k) => CUSTOMERS.filter((c) => c.status.toLowerCase() === k).length;
  const theirOrders = open ? orders.filter((o) => o.customer.name === open.name).slice(0, 6) : [];

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Customers</small><b>{CUSTOMERS.length}</b></span>
        <span><small>Active</small><b>{count("active")}</b></span>
        <span><small>New this week</small><b>{count("new")}</b></span>
        <span className="ad-warn"><small>Dormant</small><b>{count("dormant")}</b></span>
      </section>

      <section className="ad-card">
        <div className="ad-toolbar">
          <Tabs value={tab} onChange={setTab} tabs={[["all", "All", CUSTOMERS.length], ["active", "Active", count("active")], ["new", "New", count("new")], ["dormant", "Dormant", count("dormant")]]} />
          <div className="ad-toolbar-right"><Search value={q} onChange={setQ} placeholder="Name, email or area" /></div>
        </div>
        <div className="ad-table-wrap">
          <table className="ad-table">
            <thead><tr><th>Customer</th><th>Contact</th><th>Area</th><th className="ad-num">Orders</th><th className="ad-num">Spent</th><th className="ad-num">Wallet</th><th>Last order</th><th>Status</th><th /></tr></thead>
            <tbody>
              {rows.map((c, i) => (
                <tr key={c.id} style={{ "--i": i % 12 }} onClick={(e) => { if (!e.target.closest("button")) setOpen(c); }}>
                  <td><span className="ad-cell-person"><Avatar name={c.name} size={32} tone="ad-a-blue" /><span><b>{c.name}</b><small>Joined {dateShort(c.joined)}</small></span></span></td>
                  <td><small>{c.email}<br />{c.phone}</small></td>
                  <td><small>{c.area}</small></td>
                  <td className="ad-num">{c.orders}</td>
                  <td className="ad-num ad-strong">{inr(c.spent)}</td>
                  <td className="ad-num">{inr(c.wallet)}</td>
                  <td><small>{since(c.last)}</small></td>
                  <td><span className={"ad-pill ad-t-" + (c.status === "Active" ? "green" : c.status === "New" ? "blue" : "grey")}><i />{c.status}</span></td>
                  <td className="ad-row-act"><button className="ad-icon-btn" onClick={() => setOpen(c)} aria-label={`Open ${c.name}`}><Icon n="right" size={16} /></button></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <Empty icon="users" title="No customers match" text="Try a different search." />}
        </div>
      </section>

      {open && (
        <Drawer title={open.name} sub={`${open.area} · ${open.status}`} onClose={() => setOpen(null)}
          foot={(close) => <><button className="ad-btn" onClick={() => flash(`Reset link sent to ${open.email}`)}>Send reset link</button><button className="ad-btn ad-primary" onClick={close}>Close</button></>}>
          <div className="ad-person ad-person-lg"><Avatar name={open.name} size={52} tone="ad-a-blue" /><span><b>{open.name}</b><small>{open.email}<br />{open.phone}</small></span></div>
          <div className="ad-mini-stats ad-inline-stats">
            <span><small>Orders</small><b>{open.orders}</b></span>
            <span><small>Spent</small><b>{inr(open.spent)}</b></span>
            <span><small>Wallet</small><b>{inr(open.wallet)}</b></span>
            <span><small>Last order</small><b>{since(open.last)}</b></span>
          </div>
          <section className="ad-dsec">
            <h4>Recent orders</h4>
            <ul className="ad-items">
              {theirOrders.map((o) => (
                <li key={o.id}><span className="ad-qty-chip">{o.items.length}</span><span><b>#{o.id}</b><small>{dateShort(o.at)} · {o.pay}</small></span><b>{inr(o.total)}</b></li>
              ))}
              {!theirOrders.length && <li className="ad-dim">No orders in this period.</li>}
            </ul>
          </section>
        </Drawer>
      )}
    </div>
  );
}

/* ================================ riders =============================== */
export function RidersSection({ orders, assign, flash }) {
  const live = orders.filter((o) => o.status === "out");
  const ready = orders.filter((o) => o.status === "ready");
  const load = (id) => live.filter((o) => o.rider?.id === id);
  const doneToday = (id) => orders.filter((o) => o.rider?.id === id && o.status === "delivered" && isToday(o.at)).length;

  return (
    <div className="ad-stack">
      <section className="ad-mini-stats">
        <span><small>Riders on shift</small><b>{RIDERS.length}</b></span>
        <span><small>On delivery</small><b>{live.length}</b></span>
        <span className="ad-warn"><small>Waiting for a rider</small><b>{ready.length}</b></span>
        <span><small>Delivered today</small><b>{orders.filter((o) => o.status === "delivered" && isToday(o.at)).length}</b></span>
      </section>

      <div className="ad-riders">
        {RIDERS.map((r, i) => {
          const busy = load(r.id);
          return (
            <article key={r.id} className={"ad-card ad-rider" + (busy.length ? " ad-busy" : "")} style={{ "--i": i }}>
              <header>
                <Avatar name={r.name} size={46} tone={busy.length ? "ad-a-orange" : "ad-a-green"} />
                <span><b>{r.name}</b><small>{r.vehicle}</small></span>
                <span className={"ad-pill " + (busy.length ? "ad-t-orange" : "ad-t-green")}><i />{busy.length ? "On delivery" : "Idle"}</span>
              </header>
              <div className="ad-kv">
                <span><small>Shift</small>{r.shift}</span>
                <span><small>Rating</small>{r.rating} ★</span>
                <span><small>Delivered today</small>{doneToday(r.id)}</span>
                <span><small>Lifetime trips</small>{groupIN(r.trips)}</span>
              </div>
              {busy.length > 0 ? (
                <ul className="ad-items ad-rider-jobs">
                  {busy.map((o) => <li key={o.id}><span className="ad-qty-chip">{o.items.length}</span><span><b>#{o.id}</b><small>{o.customer.area} · {clock(o.at)}</small></span><b>{o.eta} min</b></li>)}
                </ul>
              ) : ready.length ? (
                <div className="ad-rider-assign">
                  <p>{ready.length} order{ready.length > 1 ? "s" : ""} packed and waiting.</p>
                  <button className="ad-btn ad-primary ad-sm" onClick={() => { assign(ready[0].id, r.id); flash(`#${ready[0].id} assigned to ${r.name}`); }}>Assign #{ready[0].id}</button>
                </div>
              ) : <p className="ad-dim ad-rider-idle">Nothing waiting — free for the next order.</p>}
              <footer>
                <button className="ad-btn ad-sm" onClick={() => flash(`Calling ${r.name}`)}><Icon n="phone" size={15} />Call</button>
                <button className="ad-btn ad-sm" onClick={() => flash(`Message sent to ${r.name}`)}><Icon n="chat" size={15} />Message</button>
              </footer>
            </article>
          );
        })}
      </div>
    </div>
  );
}
