"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* Same app shell, opened on the cart view. Cart contents come from localStorage (persistCart). */
export default function CartRoute() {
  const router = useRouter();
  return <Home initialView="cart" syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
