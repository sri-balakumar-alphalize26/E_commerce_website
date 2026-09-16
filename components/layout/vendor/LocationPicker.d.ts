/**
 * The type boundary around the vendored location picker.
 *
 * LocationPicker.jsx stays JavaScript so it can be diffed against its
 * archive; declaring its props here means AddressPill is checked against
 * them. The shape below is the design's own -- a flat label/line/city --
 * deliberately NOT SavedAddress, because nothing inside vendor/ should know
 * what this app stores.
 *
 * Keep in step with what LocationPicker actually destructures.
 */

export type PickerAddress = {
  id: string
  label: string
  line: string
  city?: string
  icon?: string
}

export type LocationPickerProps = {
  open: boolean
  onClose: () => void
  /** CSS selector for the control the popover springs from. */
  anchorSelector?: string
  addresses?: PickerAddress[]
  selected?: { id: string }
  onSelect: (address: PickerAddress) => void
  /** Reverse-geocode a fix. Omitted here: there is no geocoder. */
  onLocate?: (coords: { lat: number; lon: number }) => Promise<PickerAddress | null>
  onAddNew?: () => void
}

declare function LocationPicker(props: LocationPickerProps): JSX.Element
export default LocationPicker
