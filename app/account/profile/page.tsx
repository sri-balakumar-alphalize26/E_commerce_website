'use client'

import { useState } from 'react'
import Link from 'next/link'
import { isValidEmail } from '@/lib/session'
import { updateProfile } from '@/lib/session-store'
import { useSession } from '@/lib/use-session'
import { cn } from '@/lib/cn'

/**
 * Personal info.
 *
 * Genuinely editable and genuinely persisted, but device-local -- there is
 * no account server yet, and the page says so rather than implying the
 * details are synced anywhere.
 */
export default function ProfilePage() {
  const { profile, signedIn } = useSession()
  const [saved, setSaved] = useState(false)

  if (!signedIn || !profile) return <SignedOut />

  return (
    <section className="border-surface-line bg-surface rounded-card border p-5">
      <h2 className="text-ink mb-1 text-base font-extrabold">Personal Info</h2>
      <p className="text-slate-muted mb-5 text-xs">
        Stored on this device only. It will move to your account when sign-in is connected.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          const data = new FormData(e.currentTarget)
          const name = String(data.get('name') ?? '').trim()
          const email = String(data.get('email') ?? '').trim()
          const phone = String(data.get('phone') ?? '').trim()
          if (!name || !isValidEmail(email)) return
          void updateProfile({ name, email, phone })
          setSaved(true)
        }}
        className="max-w-md space-y-4"
      >
        <Field name="name" label="Full name" defaultValue={profile.name} required />
        <Field name="email" label="Email" type="email" defaultValue={profile.email} required />
        <Field name="phone" label="Phone" type="tel" defaultValue={profile.phone} />

        <div className="flex items-center gap-3 pt-1">
          <button
            type="submit"
            className="bg-brand-600 hover:bg-brand-700 h-11 rounded-pill px-6 text-sm font-bold text-white transition-colors"
          >
            Save changes
          </button>
          {saved ? <span className="text-save text-[13px] font-bold">Saved</span> : null}
        </div>
      </form>
    </section>
  )
}

function Field({
  name,
  label,
  type = 'text',
  defaultValue,
  required,
}: {
  name: string
  label: string
  type?: string
  defaultValue?: string
  required?: boolean
}) {
  return (
    <label className="block">
      <span className="text-slate-muted mb-1 block text-xs font-bold">
        {label}
        {required ? <span className="text-danger"> *</span> : null}
      </span>
      <input
        name={name}
        type={type}
        defaultValue={defaultValue}
        required={required}
        // field-line, not surface-line: a 1.25:1 hairline cannot legally
        // identify a control under WCAG 1.4.11.
        className={cn('border-field-line focus:border-brand-600 text-ink h-11 w-full rounded-lg border px-3 text-sm outline-none')}
      />
    </label>
  )
}

export function SignedOut() {
  return (
    <section className="border-surface-line bg-surface rounded-card border p-10 text-center">
      <h2 className="text-ink text-base font-extrabold">You are not signed in</h2>
      <p className="text-slate-muted mx-auto mt-1.5 max-w-sm text-sm">
        Sign in to keep your details on this device.
      </p>
      <Link
        href="/login"
        className="bg-brand-600 hover:bg-brand-700 mt-5 inline-flex h-11 items-center rounded-pill px-6 text-sm font-bold text-white transition-colors"
      >
        Sign in
      </Link>
    </section>
  )
}
