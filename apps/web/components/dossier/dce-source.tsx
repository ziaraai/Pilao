"use client";

import { useState } from "react";

import {
  type RetrievalChoice,
  RetrievalDialog,
} from "@/components/dossier/retrieval-dialog";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { sourceCase, watchLine } from "@/lib/dce-source";
import { useAction } from "@/lib/hooks";
import type { DceSource } from "@/lib/types";

const fetching = (s: DceSource | undefined) =>
  s?.last_fetch?.status === "pending" || s?.last_fetch?.status === "running";

export { fetching as retrievalRunning };

/**
 * Where the DCE is and how to get it (spec « Récupération des DCE », § 4.1): Pilao's robot on
 * PLACE and the Atexo platforms, a guided retrieval elsewhere, or a field for the link.
 */
export function DceSourcePanel({
  bidId,
  source,
  hasVersions,
  onChanged,
}: {
  bidId: string;
  source: DceSource;
  hasVersions: boolean;
  onChanged: () => void;
}) {
  const [dialog, setDialog] = useState(false);
  const [editing, setEditing] = useState(false);
  const [link, setLink] = useState("");
  const retrieve = useAction();
  const save = useAction();
  const site = source.site ?? "la plateforme";
  const which = sourceCase(source);
  const last = source.last_fetch;
  const failed = last?.status === "error" ? last : null;
  const watch = watchLine(source.watch, new Date());

  async function start(body: object) {
    const done = await retrieve.run(() =>
      api(`/bids/${bidId}/dce/retrieve`, { json: body }),
    );
    if (done) {
      setDialog(false);
      onChanged();
    }
  }

  function onRetrieve() {
    if (source.mode === null) setDialog(true);
    else void start({});
  }

  async function onSaveLink(e: React.FormEvent) {
    e.preventDefault();
    if (
      await save.run(() =>
        api(`/bids/${bidId}/dce/source`, {
          method: "PUT",
          json: { url: link },
        }),
      )
    ) {
      setLink("");
      setEditing(false);
      onChanged();
    }
  }

  const guided = source.url && (
    <div className="space-y-2">
      <a
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center rounded-md bg-white px-3.5 py-2 text-sm font-semibold text-brand-navy ring-1 ring-inset ring-slate-400 hover:bg-slate-50"
      >
        Ouvrir la page du DCE
      </a>
      {source.guide.length > 0 && (
        <ol
          className="space-y-1 text-sm text-slate-700"
          aria-label="Aide-mémoire"
        >
          {source.guide.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ol>
      )}
    </div>
  );

  if (hasVersions)
    return (
      <div className="mb-4 space-y-1 text-sm text-slate-600">
        {source.url && (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            Page du DCE sur {site}
          </a>
        )}
        {watch && <p>{watch}</p>}
        {failed && last?.kind === "update" && (
          <Alert tone="warning">{failed.message}</Alert>
        )}
      </div>
    );

  return (
    <div className="mb-4 space-y-3">
      {which === "robot" && !failed && (
        <div className="space-y-1">
          <Button busy={retrieve.busy || fetching(source)} onClick={onRetrieve}>
            Récupérer le DCE
          </Button>
          <p className="text-xs text-slate-500">sur {site}</p>
        </div>
      )}
      {fetching(source) && (
        <Alert tone="info">
          Pilao récupère le DCE sur {site}… (environ 1 minute)
        </Alert>
      )}
      {failed && (
        <div className="space-y-2">
          <Alert tone="danger">{failed.message}</Alert>
          {failed.outcome === "refused_identity" && (
            <Button
              variant="secondary"
              busy={retrieve.busy}
              onClick={() => void start({ mode: "anonymous" })}
            >
              Récupérer anonymement pour ce dossier
            </Button>
          )}
          {failed.outcome === "unavailable" && which === "robot" && (
            <Button
              variant="secondary"
              busy={retrieve.busy}
              onClick={onRetrieve}
            >
              Réessayer
            </Button>
          )}
        </div>
      )}
      {(which === "guided" || failed) && guided}
      {which !== "link" && !editing && (
        <Button
          variant="ghost"
          className="px-2 py-1 text-xs"
          onClick={() => setEditing(true)}
        >
          Modifier le lien
        </Button>
      )}
      {(which === "link" || editing) && (
        <form onSubmit={onSaveLink} className="space-y-2" noValidate>
          <Field
            label="Collez le lien de la consultation"
            htmlFor="dce-link"
            hint={
              source.home_only
                ? `L'annonce ne donne que l'accueil de ${site} : ouvrez la consultation et copiez son adresse.`
                : "L'adresse de la page de la consultation sur le site de l'acheteur."
            }
            error={save.error}
          >
            <Input
              id="dce-link"
              type="url"
              value={link}
              placeholder="https://"
              onChange={(e) => setLink(e.target.value)}
            />
          </Field>
          <Button
            type="submit"
            variant="secondary"
            busy={save.busy}
            disabled={link.trim() === ""}
          >
            Enregistrer
          </Button>
        </form>
      )}
      {retrieve.error && !dialog && (
        <Alert tone="danger">{retrieve.error}</Alert>
      )}
      {dialog && (
        <RetrievalDialog
          site={site}
          termsUrl={source.terms_url}
          contact={source.contact}
          busy={retrieve.busy}
          error={retrieve.error}
          onConfirm={(choice: RetrievalChoice) => void start(choice)}
          onClose={() => setDialog(false)}
        />
      )}
    </div>
  );
}
