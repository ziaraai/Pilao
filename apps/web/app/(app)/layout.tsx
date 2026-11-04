import { Suspense } from "react";

import { AppShell } from "@/components/app-shell";
import { Loading } from "@/components/ui";

// The shell reads the URL (active tab, redirect after login): it must render under Suspense
// with Cache Components (prerendered static shell, dynamic parts streamed in).
export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <Suspense
      fallback={
        <div className="p-8">
          <Loading />
        </div>
      }
    >
      <AppShell>{children}</AppShell>
    </Suspense>
  );
}
