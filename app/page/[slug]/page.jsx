"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /page/<slug>: a footer page written in Odoo (369 Mart > Info pages). */
export default function InfoRoute({ params }) {
  const { slug } = use(params);
  const router = useRouter();
  return <Home initialView="page" initialParam={decodeURIComponent(slug)} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
