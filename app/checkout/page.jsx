"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /checkout — address, delivery slot, payment (cart is read from localStorage) */
export default function CheckoutRoute() {
  const router = useRouter();
  return <Home initialView="checkout" syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
