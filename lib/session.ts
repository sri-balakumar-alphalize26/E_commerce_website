/**
 * The local account session.
 *
 * There is no authentication in this phase. This stores a profile on the
 * device so the header, the sidebar and the account pages have something
 * truthful to show, and so sign-in and sign-out are real state transitions
 * rather than decorations.
 *
 * The validation rules deliberately match the Odoo `/api/register` contract
 * the real backend will enforce -- a valid-looking email and a six-character
 * minimum -- so swapping a network call in later changes one file and no
 * form.
 *
 * No password is stored. There is nothing to check it against, and keeping
 * one would be theatre with a real downside.
 */

export type Profile = {
  name: string
  email: string
  phone: string
}

const KEY = 'store.session.v1'

export const MIN_PASSWORD = 6

/**
 * The demo account.
 *
 * Deliberately not a real email and deliberately shorter than MIN_PASSWORD,
 * so it cannot be reached by accident: no customer types "abc" into an
 * email field and expects it to work, and the normal rules reject it before
 * it gets anywhere. It is matched as an exact pair, ahead of validation,
 * rather than by loosening the rules for everyone.
 *
 * This exists so the storefront can be demonstrated without inventing an
 * address on the spot, and it is printed on the sign-in page rather than
 * hidden -- a credential that works but is not written down anywhere is one
 * support question away from being useless.
 *
 * It is NOT an authentication bypass, because there is no authentication to
 * bypass in this phase: any valid-looking email and six characters already
 * sign in. When real auth lands this constant goes with it, and the check
 * in app/login/page.tsx is the only thing that has to be removed.
 */
export const DEMO_EMAIL = 'abc'
export const DEMO_PASSWORD = 'abc'

export const DEMO_PROFILE: Profile = {
  name: 'Demo',
  email: DEMO_EMAIL,
  phone: '',
}

export function isDemoLogin(email: string, password: string) {
  return email.trim().toLowerCase() === DEMO_EMAIL && password === DEMO_PASSWORD
}
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

export function isValidEmail(email: string) {
  return EMAIL_RE.test(email.trim())
}

export function initialsOf(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase() ?? '')
      .join('') || 'ME'
  )
}

export function readStoredProfile(): Profile | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(KEY)
    if (!raw) return null
    const p = JSON.parse(raw)
    if (!p || typeof p.name !== 'string' || typeof p.email !== 'string') return null
    return { name: p.name, email: p.email, phone: typeof p.phone === 'string' ? p.phone : '' }
  } catch {
    return null
  }
}

export function writeStoredProfile(p: Profile | null) {
  if (typeof window === 'undefined') return
  try {
    if (p) window.localStorage.setItem(KEY, JSON.stringify(p))
    else window.localStorage.removeItem(KEY)
  } catch {}
}
