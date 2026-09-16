'use client'

import { ChevronDown, MapPin } from 'lucide-react'
import { useState } from 'react'
import AddressDialog from '@/components/layout/AddressDialog'
import { CATALOG } from '@/lib/catalog-config'
import { cn } from '@/lib/cn'
import { formatAddress } from '@/lib/prefs'
import { useSelectedAddress } from '@/lib/use-prefs'

/**
 * The delivery-address chip in the header.
 *
 * This existed once before as a dead control -- a label reading "Select
 * location" that linked to the home page. It is back because the address is
 * now genuinely stored, genuinely selectable, and genuinely reflected here.
 *
 * Below 720px only the label shows. The full line needs about 260px to be
 * readable and there is not that much room beside a logo and a cart on a
 * 390px screen; the dialog carries it instead.
 */
export default function AddressPill({ className }: { className?: string }) {
  const [open, setOpen] = useState(false)
  const address = useSelectedAddress()

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={cn(
          'chip-on-brand inline-flex h-9 max-w-[260px] items-center gap-2 rounded-pill px-3 text-left text-white transition-colors',
          className,
        )}
      >
        <MapPin className="size-[18px] shrink-0" aria-hidden />
        <span className="min-w-0">
          <span className="flex items-center gap-1">
            <span className="text-[13px] leading-4 font-extrabold">
              {address ? address.label : CATALOG.brand.deliveryLabel}
            </span>
            <ChevronDown className="size-3.5 shrink-0" aria-hidden />
          </span>
          <span className="hidden truncate text-[10px] leading-3 text-white/75 md:block">
            {address ? formatAddress(address) : 'Select a delivery location'}
          </span>
        </span>
      </button>

      <AddressDialog open={open} onClose={() => setOpen(false)} />
    </>
  )
}
