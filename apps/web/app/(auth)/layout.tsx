import Link from "next/link";

import { Logo } from "@/components/logo";

export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <main className="flex min-h-screen flex-col items-center bg-slate-50 px-4 py-10">
      <Link href="/" className="mb-8">
        <Logo />
      </Link>
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-sm ring-1 ring-slate-200">
        {children}
      </div>
    </main>
  );
}
