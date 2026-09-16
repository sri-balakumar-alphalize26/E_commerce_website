'use client'

import { ChevronDown, MapPin } from 'lucide-react'
import { useState } from 'react'
import AddressDialog from '@/components/layout/AddressDialog'
import LocationPicker from '@/components/layout/vendor/LocationPicker'
import { CATALOG } from '@/lib/catalog-config'
import { cn } from '@/lib/cn'
import { formatAddress } from '@/lib/prefs'
import { selectAddress } from '@/lib/prefs-store'
import { useAddresses, useSelectedAddress } from '@/lib/use-prefs'

/**
 * The delivery-address chip in the header.
 *
 * This existed once before as a dead control -- a label reading "Select
 * location" that linked to the home page. It is back because the address is
 * now genuinely stored, genuinely selectable, and genuinely reflected here.
 *
 * Below 720px only the label shows. The full line needs about 260px to be
 * readable and there is not that much room beside a logo and a cart on a
 * 390px screen; the picker carries it instead.
 *
 * TWO SURFACES, NOT ONE. Tapping the chip opens the vendored picker: a
 * popover that springs from this button, or a sheet on a phone, for the
 * common case of switching between addresses already saved. Adding a new
 * one still opens AddressDialog, because that is where the form lives and
 * the picker has no form of its own -- its "Add a new address" button ships
 * with no handler at all. Keeping the dialog also means /account/addresses,
 * which mounts the same component, needs no changes.
 */
export default function AddressPill({ className }: { className?: string }) {
  const [picking, setPicking] = useState(false)
  const [adding, setAdding] = useState(false)
  const addresses = useAddresses()
  const address = useSelectedAddress()

  return (
    <>
      <button
        type="button"
        // hm-loc is the anchor the picker measures to decide where to
        // spring from; it carries no styling of its own here.
        className={cn(
          'hm-loc chip-on-brand inline-flex h-9 max-w-[260px] items-center gap-2 rounded-pill px-3 text-left text-white transition-colors',
          className,
        )}
        onClick={() => (addresses.length ? setPicking(true) : setAdding(true))}
        aria-haspopup="dialog"
        aria-expanded={picking || adding}
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

      {/*
        The picker speaks its own shape -- a flat label/line/city -- so the
        saved addresses are mapped on the way in and only the id comes back.
        Nothing inside components/layout/vendor knows what a SavedAddress is.
      */}
      <LocationPicker
        open={picking}
        onClose={() => setPicking(false)}
        anchorSelector=".hm-loc"
        addresses={addresses.map((a) => ({
          id: a.id,
          label: a.label,
          line: [a.line1, a.line2].filter(Boolean).join(', '),
          city: [a.city, a.pincode].filter(Boolean).join(' '),
          icon: a.label.toLowerCase() === 'work' ? 'brief' : 'home',
        }))}
        selected={address ? { id: address.id } : undefined}
        onSelect={(a: { id: string }) => void selectAddress(a.id)}
        onAddNew={() => {
          setPicking(false)
          setAdding(true)
        }}
      />

      <AddressDialog open={adding} onClose={() => setAdding(false)} />
    </>
  )
}
