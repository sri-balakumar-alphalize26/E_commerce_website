"use client";
import { useRouter } from "next/navigation";
import Home from "@/components/home/Home";

/* /categories — every category and its sub-categories (footer "All categories") */
export default function CategoriesRoute() {
  const router = useRouter();
  return <Home initialView="categories" syncUrl persistCart onSignOut={() => router.push("/login")} />;
}
