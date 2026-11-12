"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/admin/dialogs";
import { Loaded, Pill } from "@/components/admin/ui";
import { Alert, Button, Card } from "@/components/ui";
import { useAdminAction, useAdminApi } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import type { AdminModule } from "@/lib/types";

/** Lot 3, spec §3.1: the company's modules, turned on or off. Nothing is erased. */
export function OrgModules({
  orgId,
  modules,
  onChanged,
}: {
  orgId: string;
  modules: string[];
  onChanged: () => void;
}) {
  const catalog = useAdminApi<AdminModule[]>("/admin/modules");
  const act = useAdminAction();
  const [done, setDone] = useState<string | null>(null);
  const [disabling, setDisabling] = useState<AdminModule | null>(null);
  const [enabling, setEnabling] = useState<string | null>(null); // only its button spins

  async function toggle(m: AdminModule, enabled: boolean) {
    setDone(null);
    await api<{ modules: string[] }>(
      `/admin/organizations/${orgId}/modules/${m.key}`,
      { method: "PUT", json: { enabled } },
    );
    setDone(`« ${m.name} » ${enabled ? "activé" : "désactivé"}.`);
    onChanged();
  }

  return (
    <Card title="Modules" color="sky" flush>
      {(done || act.error) && (
        <div className="px-5 pt-4">
          {act.error ? (
            <Alert tone="danger">{act.error}</Alert>
          ) : (
            <Alert tone="ok">{done}</Alert>
          )}
        </div>
      )}
      <div className="px-5 py-4">
        <Loaded state={catalog}>
          {(list) => (
            <ul className="divide-y divide-slate-200">
              {list.map((m) => {
                const on = modules.includes(m.key);
                return (
                  <li
                    key={m.key}
                    className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 first:pt-0 last:pb-0"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="flex flex-wrap items-center gap-2 font-semibold text-slate-900">
                        {m.name}
                        {on ? (
                          <Pill tone="ok">Activé</Pill>
                        ) : (
                          <Pill tone="neutral">Désactivé</Pill>
                        )}
                      </p>
                      <p className="text-sm text-slate-600">{m.description}</p>
                    </div>
                    {on ? (
                      <Button
                        variant="secondary"
                        aria-label={`Désactiver ${m.name}`}
                        onClick={() => {
                          setDone(null);
                          setDisabling(m);
                        }}
                      >
                        Désactiver
                      </Button>
                    ) : (
                      <Button
                        busy={enabling === m.key}
                        disabled={enabling !== null}
                        aria-label={`Activer ${m.name}`}
                        onClick={async () => {
                          setEnabling(m.key);
                          await act.run(() => toggle(m, true));
                          setEnabling(null);
                        }}
                      >
                        Activer
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </Loaded>
      </div>
      {disabling && (
        <ConfirmDialog
          title={`Désactiver « ${disabling.name} » ?`}
          confirmLabel="Désactiver"
          danger
          onConfirm={() => toggle(disabling, false)}
          onClose={() => setDisabling(null)}
        >
          <p>
            Ses utilisateurs ne verront plus ce module. Rien n&apos;est effacé :
            vous pourrez le réactiver.
          </p>
        </ConfirmDialog>
      )}
    </Card>
  );
}
