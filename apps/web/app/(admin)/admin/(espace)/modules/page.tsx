"use client";

import { AdminTitle, Loaded } from "@/components/admin/ui";
import { Card } from "@/components/ui";
import { useAdminApi } from "@/lib/admin-auth";
import type { AdminModule } from "@/lib/types";

/** Lot 3, US-6.10: the modules of Pilao, what each holds and how many companies have it.
 * Read-only: a module is turned on or off on a company's page. */
export default function AdminModulesPage() {
  const catalog = useAdminApi<AdminModule[]>("/admin/modules");
  return (
    <div className="space-y-6">
      <AdminTitle
        title="Modules"
        subtitle="Les blocs de Pilao qu'une entreprise a ou non. Ils s'activent depuis la fiche de chaque entreprise."
      />
      <Loaded state={catalog}>
        {(list) => (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            {list.map((m) => (
              <Card
                key={m.key}
                title={m.name}
                color="sky"
                actions={
                  <span className="text-sm font-semibold">
                    {m.organizations}{" "}
                    {m.organizations > 1 ? "entreprises" : "entreprise"}
                  </span>
                }
              >
                <p className="text-sm text-slate-700">{m.description}</p>
                <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Contient
                </h3>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-slate-800">
                  {m.contents.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
                <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Dans le menu de l&apos;entreprise
                </h3>
                <p className="mt-1 text-sm text-slate-800">
                  {m.nav.join(" · ")}
                </p>
              </Card>
            ))}
          </div>
        )}
      </Loaded>
    </div>
  );
}
