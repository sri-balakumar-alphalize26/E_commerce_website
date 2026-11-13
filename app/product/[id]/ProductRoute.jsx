"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* Product details route: /product/<id>. Same app shell, opened on the product view. */
export default function ProductRoute({ params }) {
  const { id } = use(params);
  const router = useRouter();
  return <Home initialView="product" initialProduct={decodeURIComponent(id)} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
