import AccountSidebar from '@/components/account/AccountSidebar'
import Container from '@/components/ui/Container'
import PageHeader from '@/components/ui/PageHeader'

/**
 * Sidebar beside the content at >=1100px, stacked above it below that.
 * The sidebar is not collapsed into a drawer on mobile: it is the only
 * navigation this section has, and hiding it behind a control on the
 * narrowest screen is where account sections usually become unusable.
 */
export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <PageHeader title="My Account" backHref="/" />
      <main>
        <Container className="py-5">
          <div className="lg:flex lg:items-start lg:gap-6">
            <div className="lg:w-64 lg:shrink-0">
              <AccountSidebar />
            </div>
            <div className="mt-5 min-w-0 flex-1 lg:mt-0">{children}</div>
          </div>
        </Container>
      </main>
    </>
  )
}
