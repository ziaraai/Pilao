import { Suspense } from "react";

import { AdminShell } from "@/components/admin/shell";
import { Loading } from "@/components/ui";

// The shell reads the URL (active entry, redirect after sign-in): it renders under Suspense
// with Cache Components, like the company space.
export default function AdminSpaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Suspense
      fallback={
        <div className="p-8">
          <Loading />
        </div>
      }
    >
      <AdminShell>{children}</AdminShell>
    </Suspense>
  );
}
