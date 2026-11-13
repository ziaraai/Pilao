"use client";

import { useState } from "react";

import { Alert, Button, Card, Field, Input, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { RetrievalSettings } from "@/lib/types";

type ModeChoice = "identified" | "anonymous" | "ask";

/** « Récupération des DCE » (spec § 4.4): how Pilao retrieves a DCE on PLACE and the Atexo
 * platforms, and the contact it gives the buyers on the company's behalf. */
export function DceRetrievalSettings() {
  const settings = useApi<RetrievalSettings>("/profile/dce-retrieval");
  if (!settings.data)
    return (
      <Card title="Récupération des DCE" color="blue">
        {settings.error ? (
          <Alert tone="danger">{settings.error}</Alert>
        ) : (
          <Loading />
        )}
      </Card>
    );
  return <SettingsForm saved={settings.data} onSaved={settings.setData} />;
}

function SettingsForm({
  saved: initial,
  onSaved,
}: {
  saved: RetrievalSettings;
  onSaved: (s: RetrievalSettings) => void;
}) {
  const save = useAction();
  const [saved, setSaved] = useState(false);
  const [mode, setMode] = useState<ModeChoice>(initial.mode ?? "ask");
  const [contact, setContact] = useState({
    first_name: initial.contact.first_name ?? "",
    last_name: initial.contact.last_name ?? "",
    email: initial.contact.email ?? "",
  });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaved(false);
    const done = await save.run(() =>
      api<RetrievalSettings>("/profile/dce-retrieval", {
        method: "PUT",
        json: { mode: mode === "ask" ? null : mode, contact },
      }),
    );
    if (done) {
      onSaved(done);
      setSaved(true);
    }
  }

  const choices: [ModeChoice, string][] = [
    ["identified", "Au nom de l'entreprise (recommandé)"],
    ["anonymous", "Anonymement"],
    ["ask", "Me demander à chaque fois"],
  ];
  return (
    <Card title="Récupération des DCE" color="blue">
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <p className="text-sm text-slate-600">
          Sur PLACE et les plateformes Atexo, Pilao peut récupérer le DCE pour
          vous. Au nom de l&apos;entreprise, l&apos;acheteur vous préviendra des
          modifications.
        </p>
        <fieldset className="space-y-2">
          <legend className="text-sm font-medium text-slate-800">Mode</legend>
          {choices.map(([value, label]) => (
            <label key={value} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="dce-retrieval-mode"
                checked={mode === value}
                onChange={() => setMode(value)}
              />
              {label}
            </label>
          ))}
        </fieldset>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Prénom du contact" htmlFor="buyer-first">
            <Input
              id="buyer-first"
              value={contact.first_name}
              onChange={(e) =>
                setContact({ ...contact, first_name: e.target.value })
              }
            />
          </Field>
          <Field label="Nom du contact" htmlFor="buyer-last">
            <Input
              id="buyer-last"
              value={contact.last_name}
              onChange={(e) =>
                setContact({ ...contact, last_name: e.target.value })
              }
            />
          </Field>
          <Field label="E-mail du contact" htmlFor="buyer-email">
            <Input
              id="buyer-email"
              type="email"
              value={contact.email}
              onChange={(e) =>
                setContact({ ...contact, email: e.target.value })
              }
            />
          </Field>
        </div>
        {save.error && <Alert tone="danger">{save.error}</Alert>}
        {saved && <Alert tone="ok">Enregistré.</Alert>}
        <Button type="submit" busy={save.busy}>
          Enregistrer
        </Button>
      </form>
    </Card>
  );
}
