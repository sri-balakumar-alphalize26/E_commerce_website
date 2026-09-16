'use client'

import { useSyncExternalStore } from 'react'
import {
  getAddresses,
  getMode,
  getServerAddresses,
  getServerMode,
  getSelectedAddress,
  subscribe,
} from '@/lib/prefs-store'

export function useDeliveryMode() {
  return useSyncExternalStore(subscribe, getMode, getServerMode)
}

export function useAddresses() {
  return useSyncExternalStore(subscribe, getAddresses, getServerAddresses)
}

/**
 * The address the header shows. Keyed off the list so the subscription
 * fires when the selection changes, and resolved through the store rather
 * than re-scanning here.
 */
export function useSelectedAddress() {
  useAddresses()
  return getSelectedAddress()
}

/**
 * False during the server render and the first client paint. The server
 * snapshot is a single shared empty array, so identity against it is the
 * signal that stored preferences have been read.
 */
export function usePrefsReady() {
  return useSyncExternalStore(
    subscribe,
    () => getAddresses() !== getServerAddresses(),
    () => false,
  )
}
