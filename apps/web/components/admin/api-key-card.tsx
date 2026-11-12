"use client";

import { useState } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { useAdminAction } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { dollars } from "@/lib/settings";
import type { AdminApiKey } from "@/lib/types";

/** Lot 5: the OpenRouter key — checked, stored encrypted, never shown again. */
export function ApiKeyCard({
  apiKey,
  onSaved,
}: {
  apiKey: AdminApiKey;
  onSaved: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [code, setCode] = useState("");
  const save = useAdminAction();
  const k = apiKey;
  const setHere = k.source === "admin" || k.unreadable;
  const which =
    k.source === "admin"
      ? `•••• ${k.last4} — réglée ici le ${formatDate(k.updated_at)}`
      : k.source === "server"
        ? `•••• ${k.last4} — clé du serveur`
        : "Aucune clé";

  return (
    <Card title="Clé OpenRouter" color="violet">
      <div className="space-y-4">
        {k.unreadable && (
          <Alert tone="danger">
            La clé enregistrée est illisible : la clé du serveur est utilisée.
            Remplacez-la.
          </Alert>
        )}
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="font-mono text-sm text-slate-900">{which}</p>
          {k.source !== "none" && (
            <p className="text-sm text-slate-700">
              {k.credit
                ? `${dollars(k.credit.total_usd - k.credit.used_usd)} restants sur ${dollars(k.credit.total_usd)}`
                : "Crédit indisponible"}
            </p>
          )}
        </div>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            const done = await save.run(() =>
              api("/admin/settings/api-key", {
                method: "PUT",
                json: { key: typed, code },
              }),
            );
            if (done) {
              setTyped("");
              setCode("");
              onSaved();
            }
          }}
        >
          <div className="min-w-0 flex-1">
            <Field label="Remplacer la clé" htmlFor="openrouter-key">
              <Input
                id="openrouter-key"
                type="password"
                autoComplete="off"
                placeholder="sk-or-v1-…"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
              />
            </Field>
          </div>
          <div className="w-full sm:w-56">
            <Field
              label="Code de l'application d'authentification"
              htmlFor="openrouter-key-code"
              hint="Demandé à nouveau : la clé voit tous les textes envoyés à l'IA."
            >
              <Input
                id="openrouter-key-code"
                autoComplete="one-time-code"
                autoCapitalize="none"
                spellCheck={false}
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </Field>
          </div>
          <Button
            type="submit"
            busy={save.busy}
            disabled={!typed.trim() || !code.trim()}
          >
            Vérifier et enregistrer
          </Button>
        </form>
        {save.error && <Alert tone="danger">{save.error}</Alert>}
        <Button
          variant="secondary"
          disabled={!setHere || !k.server_key}
          busy={save.busy}
          onClick={async () => {
            const done = await save.run(
              async () => (
                await api("/admin/settings/api-key", { method: "DELETE" }),
                true
              ),
            );
            if (done) onSaved();
          }}
        >
          Revenir à la clé du serveur
        </Button>
      </div>
    </Card>
  );
}
