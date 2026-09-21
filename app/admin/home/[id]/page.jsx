"use client";
import { use } from "react";
import PageEditor from "@/components/admin/PageEditor";

/* /admin/home/<id> — the phone editor for one saved home page.
   `[section]` above only matches one segment, so this and /admin/home coexist. */
export default function AdminPageEditorRoute({ params }) {
  const { id } = use(params);
  return <PageEditor pageId={id} />;
}
