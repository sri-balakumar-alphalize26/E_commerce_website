"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /search?q=atta — full results with filters, sort and "did you mean" */
export default function SearchRoute({ searchParams }) {
  const { q = "" } = use(searchParams);
  const router = useRouter();
  return <Home initialView="search" initialParam={Array.isArray(q) ? q[0] : q} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
