/**
 * The shell for Help, About and Legal.
 *
 * These are genuinely static content -- no backend needed, so they are real
 * pages rather than stubs. They exist mainly so nothing in the sidebar links
 * to a 404, which is the failure that got the Account link removed the first
 * time round.
 */
export default function StaticPage({
  title,
  intro,
  sections,
}: {
  title: string
  intro: string
  sections: { heading: string; body: string }[]
}) {
  return (
    <section className="border-surface-line bg-surface rounded-card border p-5 md:p-6">
      <h2 className="text-ink font-display text-lg font-extrabold tracking-tight">{title}</h2>
      <p className="text-slate-body mt-2 text-[13px] leading-relaxed">{intro}</p>

      <div className="mt-6 space-y-5">
        {sections.map((s) => (
          <div key={s.heading} className="border-surface-line border-t pt-4">
            <h3 className="text-ink text-sm font-extrabold">{s.heading}</h3>
            <p className="text-slate-body mt-1.5 text-[13px] leading-relaxed">{s.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
