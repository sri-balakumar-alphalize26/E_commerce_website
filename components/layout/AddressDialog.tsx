'use client'

import { ArrowLeft, Check, Crosshair, Home, Plus, Search, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/cn'
import { formatAddress, type SavedAddress } from '@/lib/prefs'
import { removeAddress, saveAddress, selectAddress } from '@/lib/prefs-store'
import { useLockBodyScroll } from '@/lib/use-lock-body-scroll'
import { useAddresses } from '@/lib/use-prefs'

/**
 * Choose your delivery address.
 *
 * Every part of this does something: selecting changes the header, adding
 * persists, removing promotes the next address so the header is never left
 * blank. That was the condition for building it at all -- an address picker
 * whose only effect is a label promises serviceability checking that nothing
 * in this build can answer.
 *
 * GEOLOCATION is honest about its limits. The browser gives coordinates;
 * turning those into "15/2 Sivamurugan Colony" needs a geocoding service
 * this build does not have. So the permission is genuinely used -- the
 * coordinates are captured and stored on the address -- and the form then
 * asks for the street and pincode rather than inventing them.
 */

type Mode = { view: 'list' } | { view: 'form'; coords?: { lat: number; lon: number } }

/**
 * The gate is a separate component from the body on purpose.
 *
 * The body holds the form state, and unmounting it when the dialog
 * closes is what resets that state -- so reopening never resumes a
 * half-filled form the customer has forgotten about. Doing the same
 * reset with an effect inside one component means a synchronous
 * setState in an effect body, which costs a render pass and which React
 * 19 flags.
 */
export default function AddressDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null
  return <AddressDialogBody onClose={onClose} />
}

function AddressDialogBody({ onClose }: { onClose: () => void }) {
  const addresses = useAddresses()
  const [mode, setMode] = useState<Mode>({ view: 'list' })
  const [filter, setFilter] = useState('')
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreRef = useRef<HTMLElement | null>(null)

  useLockBodyScroll(true)

  useEffect(() => {
    restoreRef.current = document.activeElement as HTMLElement | null
    panelRef.current?.focus()

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      restoreRef.current?.focus?.()
    }
  }, [onClose])


  if (typeof document === 'undefined') return null

  const q = filter.trim().toLowerCase()
  const shown = q
    ? addresses.filter((a) => (a.label + ' ' + formatAddress(a)).toLowerCase().includes(q))
    : addresses

  return createPortal(
    <div className="fixed inset-0 z-[75] flex items-end justify-center md:items-start md:pt-16">
      <button
        type="button"
        aria-label="Close"
        onClick={onClose}
        className="absolute inset-0 cursor-default"
        style={{ background: 'var(--scrim)' }}
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Choose your delivery address"
        tabIndex={-1}
        className="bg-surface-alt rounded-panel relative max-h-[88dvh] w-full max-w-[640px] overflow-hidden shadow-[0_-12px_28px_-12px_rgb(4_56_79/0.28)] outline-none md:max-h-[80dvh] md:shadow-[0_24px_56px_-24px_rgb(4_56_79/0.34)]"
      >
        <header className="bg-surface flex items-center gap-3 px-5 py-4">
          <button
            type="button"
            onClick={() => (mode.view === 'form' ? setMode({ view: 'list' }) : onClose())}
            aria-label={mode.view === 'form' ? 'Back to saved addresses' : 'Close'}
            className="text-brand-600 hover:bg-brand-50 -ml-2 inline-flex size-9 items-center justify-center rounded-full transition-colors"
          >
            <ArrowLeft className="size-5" aria-hidden />
          </button>
          <h2 className="text-ink text-base font-extrabold">
            {mode.view === 'form' ? 'Add a delivery address' : 'Choose your delivery address'}
          </h2>
        </header>

        <div className="max-h-[70dvh] overflow-y-auto px-4 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          {mode.view === 'form' ? (
            <AddressForm
              coords={mode.coords}
              onCancel={() => setMode({ view: 'list' })}
              onSaved={onClose}
            />
          ) : (
            <>
              <div className="bg-surface rounded-card p-4">
                <label className="bg-surface-alt flex h-11 items-center gap-2.5 rounded-pill px-4">
                  <Search className="text-slate-muted size-[18px] shrink-0" aria-hidden />
                  <input
                    value={filter}
                    onChange={(e) => setFilter(e.target.value)}
                    placeholder="Search saved addresses"
                    className="text-ink placeholder:text-slate-muted h-full min-w-0 flex-1 bg-transparent text-sm outline-none"
                  />
                </label>

                <UseCurrentLocation onCoords={(coords) => setMode({ view: 'form', coords })} />

                <button
                  type="button"
                  onClick={() => setMode({ view: 'form' })}
                  className="border-surface-line text-brand-600 hover:bg-brand-50 mt-1 flex w-full items-center gap-3 rounded-lg border-t px-1 py-3.5 text-left transition-colors"
                >
                  <Plus className="size-5 shrink-0" aria-hidden />
                  <span className="text-[15px] font-bold">Add new address</span>
                </button>
              </div>

              <h3 className="text-slate-muted mt-5 mb-2 px-1 text-[13px] font-bold">
                Saved addresses
              </h3>

              {shown.length ? (
                <ul className="space-y-2">
                  {shown.map((a) => (
                    <AddressRow key={a.id} address={a} onChoose={onClose} />
                  ))}
                </ul>
              ) : (
                <p className="bg-surface rounded-card text-slate-muted px-4 py-6 text-center text-sm">
                  {addresses.length
                    ? 'No saved address matches that search.'
                    : 'No saved addresses yet. Add one to see delivery options.'}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}

function UseCurrentLocation({
  onCoords,
}: {
  onCoords: (c: { lat: number; lon: number }) => void
}) {
  const [state, setState] = useState<'idle' | 'asking' | 'denied' | 'unsupported'>('idle')

  function request() {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setState('unsupported')
      return
    }
    setState('asking')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setState('idle')
        onCoords({ lat: pos.coords.latitude, lon: pos.coords.longitude })
      },
      // A denial is a normal outcome, not an error state to recover from --
      // the customer can still type the address, so the dialog stays usable
      // and simply says what happened.
      () => setState('denied'),
      { timeout: 10000 },
    )
  }

  return (
    <div className="border-surface-line mt-1 border-t pt-1">
      <button
        type="button"
        onClick={request}
        disabled={state === 'asking'}
        className="text-brand-600 hover:bg-brand-50 flex w-full items-center gap-3 rounded-lg px-1 py-3.5 text-left transition-colors disabled:opacity-60"
      >
        <Crosshair className="size-5 shrink-0" aria-hidden />
        <span className="min-w-0">
          <span className="block text-[15px] font-bold">
            {state === 'asking' ? 'Locating…' : 'Use current location'}
          </span>
          <span className="text-slate-muted block text-xs font-normal">
            {state === 'denied'
              ? 'Location permission was declined — enter the address below'
              : state === 'unsupported'
                ? 'This browser does not support location'
                : 'We capture the coordinates; you fill in the street'}
          </span>
        </span>
      </button>
    </div>
  )
}

function AddressRow({ address, onChoose }: { address: SavedAddress; onChoose: () => void }) {
  return (
    <li
      className={cn(
        'bg-surface rounded-card flex gap-3 border p-4',
        address.selected ? 'border-brand-600' : 'border-surface-line',
      )}
    >
      <span className="bg-brand-50 text-brand-600 inline-flex size-10 shrink-0 items-center justify-center rounded-lg">
        <Home className="size-5" aria-hidden />
      </span>

      <button
        type="button"
        onClick={() => {
          void selectAddress(address.id)
          onChoose()
        }}
        className="min-w-0 flex-1 text-left"
      >
        <span className="flex items-center gap-2">
          <span className="text-ink text-sm font-extrabold">{address.label}</span>
          {address.selected ? (
            <span className="text-save inline-flex items-center gap-1 text-[11px] font-bold">
              <Check className="size-3" aria-hidden />
              Selected
            </span>
          ) : null}
        </span>
        <span className="text-slate-muted mt-1 block text-xs leading-relaxed">
          {formatAddress(address)}
        </span>
        {address.coords ? (
          <span className="text-slate-faint mt-1 block text-[11px] tabular-nums">
            {address.coords.lat.toFixed(4)}, {address.coords.lon.toFixed(4)}
          </span>
        ) : null}
      </button>

      <button
        type="button"
        onClick={() => void removeAddress(address.id)}
        aria-label={`Remove ${address.label}`}
        className="text-slate-faint hover:text-danger inline-flex size-9 shrink-0 items-center justify-center rounded-lg transition-colors"
      >
        <Trash2 className="size-4" aria-hidden />
      </button>
    </li>
  )
}

const LABELS = ['Home', 'Work', 'Other']

function AddressForm({
  coords,
  onCancel,
  onSaved,
}: {
  coords?: { lat: number; lon: number }
  onCancel: () => void
  onSaved: () => void
}) {
  const [label, setLabel] = useState('Home')
  const [line1, setLine1] = useState('')
  const [line2, setLine2] = useState('')
  const [city, setCity] = useState('')
  const [state, setState] = useState('')
  const [pincode, setPincode] = useState('')
  const [touched, setTouched] = useState(false)

  const pinOk = /^\d{6}$/.test(pincode.trim())
  const valid = line1.trim().length > 2 && city.trim().length > 1 && pinOk

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!valid) return
    void saveAddress({
      label,
      line1: line1.trim(),
      line2: line2.trim(),
      city: city.trim(),
      state: state.trim(),
      pincode: pincode.trim(),
      coords,
    })
    onSaved()
  }

  return (
    <form onSubmit={submit} className="bg-surface rounded-card space-y-4 p-4">
      {coords ? (
        <p className="bg-brand-50 text-brand-700 rounded-lg px-3 py-2 text-xs font-semibold">
          Location captured at {coords.lat.toFixed(4)}, {coords.lon.toFixed(4)}. Add the street
          and pincode to finish.
        </p>
      ) : null}

      <fieldset>
        <legend className="text-slate-muted mb-2 text-xs font-bold">Save as</legend>
        <div className="flex gap-2">
          {LABELS.map((l) => (
            <button
              key={l}
              type="button"
              onClick={() => setLabel(l)}
              aria-pressed={label === l}
              className={cn(
                'h-9 rounded-pill px-4 text-[13px] font-bold transition-colors',
                label === l
                  ? 'bg-brand-600 text-white'
                  : 'border-field-line text-slate-body border',
              )}
            >
              {l}
            </button>
          ))}
        </div>
      </fieldset>

      <Field label="Flat, house no., building" value={line1} onChange={setLine1} required
        error={touched && line1.trim().length <= 2 ? 'Please enter the building or house number' : undefined} />
      <Field label="Area, street, landmark" value={line2} onChange={setLine2} />
      <div className="grid grid-cols-2 gap-3">
        <Field label="City" value={city} onChange={setCity} required
          error={touched && city.trim().length <= 1 ? 'Required' : undefined} />
        <Field label="State" value={state} onChange={setState} />
      </div>
      <Field label="Pincode" value={pincode} onChange={setPincode} required inputMode="numeric"
        error={touched && !pinOk ? 'Enter a 6-digit pincode' : undefined} />

      <div className="flex gap-3 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="border-field-line text-ink h-11 flex-1 rounded-pill border text-sm font-bold"
        >
          Cancel
        </button>
        <button
          type="submit"
          className="bg-brand-600 hover:bg-brand-700 h-11 flex-1 rounded-pill text-sm font-bold text-white transition-colors"
        >
          Save address
        </button>
      </div>
    </form>
  )
}

function Field({
  label,
  value,
  onChange,
  required,
  error,
  inputMode,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  required?: boolean
  error?: string
  inputMode?: 'numeric'
}) {
  return (
    <label className="block">
      <span className="text-slate-muted mb-1 block text-xs font-bold">
        {label}
        {required ? <span className="text-danger"> *</span> : null}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        inputMode={inputMode}
        aria-invalid={error ? true : undefined}
        // field-line, not surface-line: a 1.25:1 hairline cannot legally
        // identify a control under WCAG 1.4.11.
        className={cn(
          'text-ink h-11 w-full rounded-lg border px-3 text-sm outline-none',
          error ? 'border-danger' : 'border-field-line focus:border-brand-600',
        )}
      />
      {error ? <span className="text-danger mt-1 block text-[11px] font-bold">{error}</span> : null}
    </label>
  )
}
