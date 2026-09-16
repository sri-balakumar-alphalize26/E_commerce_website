'use client'

import { useState } from 'react'
import { Home, MapPin, Plus, Trash2 } from 'lucide-react'
import AddressDialog from '@/components/layout/AddressDialog'
import { formatAddress } from '@/lib/prefs'
import { removeAddress, selectAddress } from '@/lib/prefs-store'
import { cn } from '@/lib/cn'
import { useAddresses, usePrefsReady } from '@/lib/use-prefs'

/**
 * The address book, full-page.
 *
 * Shares the dialog with the header rather than duplicating the form, so
 * the two can never validate differently.
 */
export default function AddressesPage() {
  const addresses = useAddresses()
  const ready = usePrefsReady()
  const [open, setOpen] = useState(false)

  return (
    <section>
      <div className="mb-4 flex items-center justify-between gap-4">
        <h2 className="text-ink font-display text-lg font-extrabold tracking-tight">
          Delivery Address
        </h2>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="bg-brand-600 hover:bg-brand-700 inline-flex h-10 items-center gap-1.5 rounded-pill px-4 text-[13px] font-bold text-white transition-colors"
        >
          <Plus className="size-4" aria-hidden />
          Add address
        </button>
      </div>

      {!ready ? (
        <p className="text-slate-muted text-sm">Loading addresses…</p>
      ) : addresses.length ? (
        <ul className="space-y-3">
          {addresses.map((a) => (
            <li
              key={a.id}
              className={cn(
                'bg-surface rounded-card flex gap-3 border p-4',
                a.selected ? 'border-brand-600' : 'border-surface-line',
              )}
            >
              <span className="bg-brand-50 text-brand-600 inline-flex size-10 shrink-0 items-center justify-center rounded-lg">
                <Home className="size-5" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2">
                  <span className="text-ink text-sm font-extrabold">{a.label}</span>
                  {a.selected ? (
                    <span className="bg-save-soft text-save rounded-tag px-1.5 py-0.5 text-[11px] font-bold">
                      Delivering here
                    </span>
                  ) : null}
                </p>
                <p className="text-slate-muted mt-1 text-xs leading-relaxed">{formatAddress(a)}</p>
                {!a.selected ? (
                  <button
                    type="button"
                    onClick={() => void selectAddress(a.id)}
                    className="text-brand-600 hover:text-brand-700 mt-2 text-xs font-bold"
                  >
                    Deliver to this address
                  </button>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => void removeAddress(a.id)}
                aria-label={`Remove ${a.label}`}
                className="text-slate-faint hover:text-danger inline-flex size-9 shrink-0 items-center justify-center rounded-lg transition-colors"
              >
                <Trash2 className="size-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="border-surface-line bg-surface rounded-card border p-10 text-center">
          <span className="bg-brand-50 text-brand-600 mx-auto inline-flex size-14 items-center justify-center rounded-2xl">
            <MapPin className="size-6" aria-hidden />
          </span>
          <h3 className="text-ink mt-4 text-base font-extrabold">No addresses saved</h3>
          <p className="text-slate-muted mx-auto mt-1.5 max-w-sm text-sm">
            Add one so the header can show where your order is going.
          </p>
        </div>
      )}

      <AddressDialog open={open} onClose={() => setOpen(false)} />
    </section>
  )
}
