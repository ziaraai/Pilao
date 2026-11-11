"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { LegalLinks } from "@/components/legal";
import { Sidebar } from "@/components/sidebar";
import { Alert, Button, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { AuthContext } from "@/lib/auth";
import { useAction, useApi } from "@/lib/hooks";
import { formatDate } from "@/lib/format";
import { DEFAULT_MODULES, hasModule } from "@/lib/modules";
import type { Deletion, Me, VaultSummary } from "@/lib/types";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const me = useApi<Me>("/auth/me");
  const unauthenticated = me.status === 401;

  useEffect(() => {
    if (unauthenticated)
      router.replace(`/connexion?suite=${encodeURIComponent(pathname)}`);
  }, [unauthenticated, router, pathname]);

  if (!me.data) {
    if (me.error && !unauthenticated) {
      return (
        <div className="mx-auto max-w-md space-y-3 p-8">
          <Alert tone="danger">{me.error}</Alert>
          <Button onClick={me.reload}>Réessayer</Button>
        </div>
      );
    }
    return (
      <div className="p-8">
        <Loading />
      </div>
    );
  }

  // An API older than the modules (lot 3) omits them: the company then has every module.
  const current: Me = {
    ...me.data,
    modules: me.data.modules ?? DEFAULT_MODULES,
    support_email: me.data.support_email ?? null,
  };

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    // Full reload on purpose: no data of this session may stay in memory (Cache Components
    // keeps hidden routes alive), which a client-side navigation would not guarantee.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/connexion");
  }

  return (
    <AuthContext.Provider value={{ me: current, refresh: me.reload }}>
      <div className="min-h-screen bg-slate-100 lg:flex">
        <Sidebar
          orgName={current.org.name}
          modules={current.modules}
          onLogout={logout}
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <DeletionBanner />
          {hasModule(current.modules, "reponse") && <VaultBanner />}
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 lg:px-8">
            {current.terms_current !== false ? ( // an older API omits it: never block
              children
            ) : (
              <TermsUpdate onAccepted={me.reload} />
            )}
          </main>
          <footer className="mx-auto w-full max-w-6xl px-4 pb-8 lg:px-8">
            <LegalLinks />
          </footer>
        </div>
      </div>
    </AuthContext.Provider>
  );
}

/** US-5.2: attestations to renew, on every page until they are replaced. */
function VaultBanner() {
  const summary = useApi<VaultSummary>("/vault/summary");
  const counts = summary.data?.counts;
  if (!counts) return null;
  const expiring = counts.expiring ?? 0;
  const expired = (counts.expired ?? 0) + (counts.mismatch ?? 0);
  if (!expiring && !expired) return null;
  const parts = [
    expired
      ? `${expired} attestation${expired > 1 ? "s" : ""} expirée${expired > 1 ? "s" : ""} ou au nom d'un autre SIREN (exclue${expired > 1 ? "s" : ""} des exports)`
      : null,
    expiring
      ? `${expiring} attestation${expiring > 1 ? "s" : ""} à renouveler dans les 30 jours`
      : null,
  ].filter(Boolean);
  return (
    <div
      role="status"
      className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-900"
    >
      {parts.join(" · ")}.{" "}
      <Link href="/coffre-fort" className="font-semibold underline">
        Voir le coffre-fort
      </Link>
    </div>
  );
}

/** ADR-026: every member sees that the company's data is about to be erased. */
function DeletionBanner() {
  const deletion = useApi<Deletion>("/organization/deletion");
  const due = deletion.data?.due_at;
  if (!due) return null;
  return (
    <div
      role="alert"
      className="border-b border-red-300 bg-red-50 px-4 py-2 text-center text-sm text-red-900"
    >
      Toutes les données de l&apos;entreprise seront supprimées le{" "}
      {formatDate(due)}.{" "}
      <Link href="/profil?onglet=donnees" className="font-semibold underline">
        Annuler ou exporter
      </Link>
    </div>
  );
}

/** The terms changed since this account accepted them (CGU art. 12): accept to go on. */
function TermsUpdate({ onAccepted }: { onAccepted: () => void }) {
  const accept = useAction();
  return (
    <div className="mx-auto max-w-xl space-y-4 rounded-lg bg-white p-6 shadow-sm ring-1 ring-slate-200">
      <h1 className="text-xl font-bold text-brand-navy">
        Nos conditions ont changé
      </h1>
      <p className="text-sm text-slate-700">
        Pour continuer à utiliser Pilao, prenez connaissance des nouvelles{" "}
        <Link
          href="/conditions-utilisation"
          target="_blank"
          className="font-semibold text-brand-navy underline"
        >
          conditions d&apos;utilisation
        </Link>
        , de l&apos;
        <Link
          href="/accord-de-traitement"
          target="_blank"
          className="font-semibold text-brand-navy underline"
        >
          accord de traitement des données
        </Link>{" "}
        et de la{" "}
        <Link
          href="/confidentialite"
          target="_blank"
          className="font-semibold text-brand-navy underline"
        >
          politique de confidentialité
        </Link>
        . Vos données restent accessibles : un administrateur peut aussi les
        exporter ou les faire supprimer depuis Profil &gt; Vos données.
      </p>
      {accept.error && <Alert tone="danger">{accept.error}</Alert>}
      <Button
        busy={accept.busy}
        onClick={async () => {
          const ok = await accept.run(() =>
            api<Me>("/auth/accept-terms", { method: "POST" }),
          );
          if (ok) onAccepted();
        }}
      >
        J&apos;accepte les nouvelles conditions
      </Button>
    </div>
  );
}
