"use client";

import Link from "next/link";

import { Card } from "@/components/ui";
import { useMe } from "@/lib/auth";
import { hasModule, type ModuleKey } from "@/lib/modules";

/** The pages of a module (lot 3): shown only to a company that has it. Reached by a link or a
 * bookmark without it, a card says so instead; nothing of the module is asked for. */
export function ModuleGate({
  module,
  children,
}: {
  module: ModuleKey;
  children: React.ReactNode;
}) {
  const { me } = useMe();
  if (hasModule(me.modules, module)) return <>{children}</>;
  return (
    <div className="mx-auto max-w-xl" data-module-off={module}>
      <Card title="Module non activé" color="slate">
        <p className="text-sm text-slate-800">
          Ce module n&apos;est pas activé pour votre entreprise. Contactez Pilao
          {me.support_email ? (
            <>
              {" : "}
              <a
                href={`mailto:${me.support_email}`}
                className="font-semibold text-brand-navy underline"
              >
                {me.support_email}
              </a>
            </>
          ) : null}
          .
        </p>
        <Link
          href="/tableau-de-bord"
          className="mt-4 inline-block text-sm font-semibold text-brand-navy underline"
        >
          Retour au tableau de bord
        </Link>
      </Card>
    </div>
  );
}
