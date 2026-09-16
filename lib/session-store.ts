import type { Profile } from '@/lib/session'
import { readStoredProfile, writeStoredProfile } from '@/lib/session'

/**
 * The signed-in profile, behind the same external-store pattern as the cart.
 *
 * `null` means signed out, and that is the server snapshot too -- the server
 * cannot know about a device-local session, so every page renders signed-out
 * first and fills in after hydration. Anything that would look wrong in that
 * frame has to check `ready`.
 */

let profile: Profile | null = null
let loaded = false
const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}

export function subscribe(onStoreChange: () => void) {
  listeners.add(onStoreChange)

  function onStorage(e: StorageEvent) {
    if (e.key !== null && !e.key.startsWith('store.session')) return
    profile = readStoredProfile()
    loaded = true
    emit()
  }
  window.addEventListener('storage', onStorage)

  return () => {
    listeners.delete(onStoreChange)
    window.removeEventListener('storage', onStorage)
  }
}

export function getSnapshot(): Profile | null {
  if (!loaded) {
    profile = readStoredProfile()
    loaded = true
  }
  return profile
}

export function getServerSnapshot(): Profile | null {
  return null
}

export async function signIn(p: Profile) {
  profile = p
  loaded = true
  writeStoredProfile(p)
  emit()
}

export async function updateProfile(patch: Partial<Profile>) {
  if (!profile) return
  profile = { ...profile, ...patch }
  writeStoredProfile(profile)
  emit()
}

/**
 * Clears the profile only. The cart, list and addresses are deliberately
 * left alone: they are device state, not account state, and wiping a
 * customer's basket because they signed out of a local-only profile would
 * be a surprising amount of destruction for a button labelled "Sign out".
 */
export async function signOut() {
  profile = null
  loaded = true
  writeStoredProfile(null)
  emit()
}
