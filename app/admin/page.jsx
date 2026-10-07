"use client";
import { useRouter } from "next/navigation";
import AdminApp from "@/components/admin/AdminApp";
import { consolePath } from "@/lib/consolePath";

export default function AdminRoute() {
  const router = useRouter();
  return <AdminApp section="dashboard" onSection={(k) => history.replaceState(null, "", k === "dashboard" ? consolePath() : consolePath(`/${k}`))} onExit={() => router.push("/")} />;
}
