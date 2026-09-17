"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /category/<slug> and /category/<slug>/<sub> — subcategory tiles, filters, sort, infinite scroll */
export default function CategoryRoute({ params }) {
  const { slug } = use(params);
  const router = useRouter();
  return <Home initialView="category" initialParam={slug.map(decodeURIComponent).join("/")} syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
