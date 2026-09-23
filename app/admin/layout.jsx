import "@/components/admin/admin.css";
import AdminGate from "@/components/admin/AdminGate";

export const metadata = { title: "369 Mart · Admin console" };

/* Every /admin page goes through the gate: staff get the console, everyone
   else is sent to sign in or told the area is not theirs. */
export default function AdminLayout({ children }) {
  return <AdminGate>{children}</AdminGate>;
}
