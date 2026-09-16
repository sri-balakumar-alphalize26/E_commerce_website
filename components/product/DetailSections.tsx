import type { Attribute } from '@/lib/catalog'

/**
 * The tables and prose below the buy panel.
 *
 * Each section returns null when it has nothing, rather than rendering a
 * heading over an empty table -- a product without specifications should
 * look like a product without specifications, not like a broken page.
 *
 * All of it is vertical-agnostic: the rows arrive as Attribute[] and this
 * file has no idea whether it is describing a biscuit or a keyboard.
 */

export function KeyFeatures({ items }: { items: string[] }) {
  if (!items.length) return null
  return (
    <Section title="Key Features">
      <ul className="text-slate-body space-y-1.5 text-[13px]">
        {items.map((f) => (
          <li key={f} className="flex gap-2">
            <span className="bg-brand-600 mt-[7px] size-1.5 shrink-0 rounded-full" aria-hidden />
            <span>{f}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

export function AttributeTable({ title, rows }: { title: string; rows: Attribute[] }) {
  if (!rows.length) return null
  return (
    <Section title={title}>
      {/* A definition list, not a table: these are name/value pairs, and a
          <table> would promise column semantics that do not exist. */}
      <dl className="divide-surface-line divide-y text-[13px]">
        {rows.map((r) => (
          <div key={r.key} className="grid grid-cols-[minmax(110px,34%)_1fr] gap-4 py-2.5">
            <dt className="text-slate-muted">{r.label}</dt>
            <dd className="text-ink font-semibold break-words">
              {r.values?.length ? r.values.join(', ') : r.value}
            </dd>
          </div>
        ))}
      </dl>
    </Section>
  )
}

export function Showcase({ title, body }: { title: string; body: string }) {
  if (!body) return null
  return (
    <Section title="Product showcase">
      <p className="text-ink mb-2 text-[13px] font-bold">{title}</p>
      <p className="text-slate-body text-[13px] leading-relaxed">{body}</p>
    </Section>
  )
}

export function Disclaimer({ text }: { text: string }) {
  return (
    <Section title="Disclaimer">
      <p className="text-slate-muted text-xs leading-relaxed">{text}</p>
    </Section>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-surface-line border-t pt-5">
      <h2 className="text-ink mb-3 text-sm font-extrabold">{title}</h2>
      {children}
    </section>
  )
}
