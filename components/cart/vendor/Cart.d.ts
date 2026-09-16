/**
 * The type boundary around the vendored cart design.
 *
 * Cart.jsx stays JavaScript, as Home.jsx and SignIn.jsx do, so that it can
 * be diffed against its archive. Declaring the props here means the bridge
 * in CartScreen.tsx is checked: a renamed field or a wrong callback shape
 * becomes a compile error instead of an empty cart at runtime.
 *
 * Keep in step with what CartPage actually destructures.
 */
import type { HomeItem } from '@/lib/home-adapter'

/** The design groups on `delivery`; falsy means the Quick group. */
export type CartVendorItem = HomeItem & { delivery?: boolean }

export type CartVendorProps = {
  /** productId -> quantity. */
  cart: Record<number, number>
  byId: Record<number, CartVendorItem>
  setQty: (id: number, qty: number) => void
  recommended?: HomeItem[]
  alsoLike?: HomeItem[]
  onBack?: () => void
}

declare function CartPage(props: CartVendorProps): JSX.Element
export default CartPage
