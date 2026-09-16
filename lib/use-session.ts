'use client'

import { useSyncExternalStore } from 'react'
import { getServerSnapshot, getSnapshot, subscribe } from '@/lib/session-store'

export function useSession() {
  const profile = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  return { profile, signedIn: profile !== null }
}
