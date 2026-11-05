import Link from "next/link";

import { LegalLinks } from "@/components/legal";
import { Logo } from "@/components/logo";

export default function LegalLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <Link href="/">
            <Logo />
          </Link>
          <Link
            href="/connexion"
            className="text-sm font-semibold text-brand-navy hover:underline"
          >
            Se connecter
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-10">
        <div className="rounded-lg bg-white p-6 shadow-sm ring-1 ring-slate-200 sm:p-10">
          {children}
        </div>
        <LegalLinks className="mt-8" />
      </main>
    </div>
  );
}
