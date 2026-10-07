"use client";
import { use } from "react";
import { useRouter } from "next/navigation";
import AdminApp from "@/components/admin/AdminApp";
import { consolePath } from "@/lib/consolePath";

/* /admin/orders · /admin/products · /admin/customers · /admin/riders · /admin/offers · /admin/reviews · /admin/settings */
export default function AdminSectionRoute({ params }) {
  const { section } = use(params);
  const router = useRouter();
  return <AdminApp section={decodeURIComponent(section)} onSection={(k) => history.replaceState(null, "", k === "dashboard" ? consolePath() : consolePath(`/${k}`))} onExit={() => router.push("/")} />;
}
