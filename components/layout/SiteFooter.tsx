import Container from '@/components/ui/Container'
import { CATALOG } from '@/lib/catalog-config'

/**
 * The footer.
 *
 * One muted centred band, matching the reference (`.o_jm_footer`: 30px top
 * margin, 12px, muted) rather than the four-column link farm most storefronts
 * ship. That restraint is not just taste: every column would need real
 * destinations, and About / Careers / Help / Returns pages do not exist. A
 * short honest footer beats eight links that all resolve to the same stub.
 *
 * `CATALOG.brand.tagline` was declared in config and rendered nowhere until
 * the header sub-line and this band.
 */
export default function SiteFooter() {
  return (
    <footer className="border-surface-line mt-8 border-t">
      <Container className="py-6 text-center">
        <p className="text-ink font-display text-sm font-extrabold tracking-tight">
          {CATALOG.brand.name}
        </p>
        <p className="text-slate-muted mt-1 text-xs">{CATALOG.brand.tagline}</p>
        <p className="text-slate-faint mt-3 text-[11px]">
          {CATALOG.shippingNote}
        </p>
      </Container>
    </footer>
  )
}
