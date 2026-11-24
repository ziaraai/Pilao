"use client";

import { useState } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { useAdminAction } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { mailboxSummary, originLabel } from "@/lib/settings";
import type { AdminDceMail, AdminDceMailTest } from "@/lib/types";

type Run = (fn: () => Promise<unknown>) => Promise<boolean>;

/** The DCE mailbox (ADR-055): each company gets dce+CODE@ this address. Its password is tried
 * on the mailbox, then kept encrypted; never shown again, not even in part. */
export function DceMailCard({
  box,
  run,
  onSaved,
}: {
  box: AdminDceMail;
  run: Run;
  onSaved: () => void;
}) {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [result, setResult] = useState<AdminDceMailTest | null>(null);
  const save = useAdminAction();
  const probe = useAdminAction();
  const [local, domain] = box.address.split("@");
  const passwordLine = {
    admin: "Mot de passe enregistré ici",
    server: "Mot de passe du serveur",
    none: "Aucun mot de passe enregistré",
  }[box.password_source];

  return (
    <Card title="Adresse e-mail des DCE" color="sky" id="boite-dce">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <p className="text-sm font-semibold text-brand-navy">
              {mailboxSummary(box)}{" "}
              <span className="text-xs font-normal text-slate-500">
                ({originLabel(box.origin)})
              </span>
            </p>
            <p className="text-xs text-slate-600">
              Boîte <span className="font-mono">{box.address}</span> : chaque
              client reçoit{" "}
              <span className="font-mono">
                {local}+code@{domain}
              </span>
              . Relue toutes les 2 minutes.
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-4 w-4"
              checked={box.enabled}
              aria-label="Adresse e-mail des DCE active"
              onChange={(e) =>
                run(() =>
                  api("/admin/settings/dce-mail", {
                    method: "PUT",
                    json: { enabled: e.target.checked },
                  }),
                )
              }
            />
            Active
          </label>
        </div>
        <p className="text-sm text-slate-700">{passwordLine}</p>
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            const done = await save.run(() =>
              api("/admin/settings/dce-mail/password", {
                method: "PUT",
                json: { password, code },
              }),
            );
            if (done) {
              setPassword("");
              setCode("");
              onSaved();
            }
          }}
        >
          <div className="min-w-0 flex-1">
            <Field
              label="Mot de passe de la boîte"
              htmlFor="dce-mail-password"
              hint="Celui choisi dans Plesk pour cette adresse. Pilao l'essaie avant de le garder."
            >
              <Input
                id="dce-mail-password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
          </div>
          <div className="w-full sm:w-56">
            <Field
              label="Code à 6 chiffres de votre application"
              htmlFor="dce-mail-code"
              hint="Demandé à nouveau : la boîte reçoit les DCE de tous les clients."
            >
              <Input
                id="dce-mail-code"
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
            disabled={!password || !code.trim()}
          >
            Essayer la boîte et enregistrer
          </Button>
        </form>
        {save.error && <Alert tone="danger">{save.error}</Alert>}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            busy={probe.busy}
            onClick={async () => {
              setResult(null);
              const r = await probe.run(() =>
                api<AdminDceMailTest>("/admin/settings/dce-mail/test", {
                  method: "POST",
                }),
              );
              if (r) setResult(r);
            }}
          >
            Tester la connexion
          </Button>
          {box.password_source === "admin" && (
            <Button
              variant="ghost"
              className="px-2 py-1 text-xs"
              onClick={() =>
                run(() =>
                  api("/admin/settings/dce-mail/password", {
                    method: "DELETE",
                  }),
                )
              }
            >
              Retirer le mot de passe enregistré ici
            </Button>
          )}
        </div>
        {probe.error && <Alert tone="danger">{probe.error}</Alert>}
        {result &&
          (result.ok ? (
            <Alert tone="ok">
              Connexion réussie : {result.waiting} e-mail(s) en attente de
              lecture
              {result.flagged > 0
                ? `, ${result.flagged} que Pilao n'a pas pu lire (marqués d'un drapeau dans la boîte)`
                : ""}
              .
            </Alert>
          ) : (
            <Alert tone="danger">{result.error}</Alert>
          ))}
      </div>
    </Card>
  );
}
