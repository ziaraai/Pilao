import Link from "next/link";

import { Logo } from "@/components/logo";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-slate-50 p-8 text-center">
      <Logo withSlogan />
      <p className="max-w-xl text-lg text-slate-700">
        Trouvez les appels d&apos;offres qui vous correspondent, analysez le DCE
        et préparez un mémoire technique adapté — vous relisez et vous décidez.
      </p>
      <div className="flex flex-wrap justify-center gap-3">
        <Link
          href="/inscription"
          className="rounded-md bg-brand-navy px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#0a2a63]"
        >
          Créer un compte
        </Link>
        <Link
          href="/connexion"
          className="rounded-md px-5 py-2.5 text-sm font-semibold text-brand-navy ring-1 ring-inset ring-slate-300 hover:bg-white"
        >
          Se connecter
        </Link>
      </div>
    </main>
  );
}
