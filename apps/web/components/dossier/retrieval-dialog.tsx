"use client";

import { useEffect, useRef, useState } from "react";

import { Alert, Button, Field, Input } from "@/components/ui";
import { useMe } from "@/lib/auth";
import type { BuyerContact, RetrievalMode } from "@/lib/types";

export type RetrievalChoice = {
  mode: RetrievalMode;
  remember: boolean;
  contact: BuyerContact | null;
};

/** The first click's window (spec « Récupération des DCE », § 4.2): on the company's behalf
 * (recommended) or anonymously, the contact given to the buyer, and « Retenir ce choix ». */
export function RetrievalDialog({
  site,
  termsUrl,
  contact,
  busy,
  error,
  onConfirm,
  onClose,
}: {
  site: string;
  termsUrl: string | null;
  contact: BuyerContact;
  busy: boolean;
  error: string | null;
  onConfirm: (choice: RetrievalChoice) => void;
  onClose: () => void;
}) {
  const { me } = useMe();
  const ref = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<RetrievalMode>("identified");
  const [remember, setRemember] = useState(true);
  const [first, last] = (me.full_name ?? "").split(/\s+(.*)/);
  const [form, setForm] = useState({
    first_name: contact.first_name ?? first ?? "",
    last_name: contact.last_name ?? last ?? "",
    email: contact.email ?? me.email,
  });

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  const complete =
    mode === "anonymous" ||
    (form.first_name.trim() !== "" &&
      form.last_name.trim() !== "" &&
      form.email.trim() !== "");

  return (
    <dialog
      ref={ref}
      aria-label="Comment récupérer le DCE ?"
      onClose={onClose}
      className="w-[min(34rem,calc(100vw-2rem))] rounded-lg p-0 shadow-xl backdrop:bg-slate-900/50"
    >
      <form
        className="space-y-4 p-5"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm({
            mode,
            remember,
            contact: mode === "identified" ? form : null,
          });
        }}
      >
        <h2 className="text-lg font-bold text-brand-navy">
          Comment récupérer le DCE ?
        </h2>
        <fieldset className="space-y-3">
          <legend className="sr-only">Mode de récupération</legend>
          <label className="flex gap-3 rounded-md border border-slate-300 p-3 text-sm">
            <input
              type="radio"
              name="retrieval-mode"
              checked={mode === "identified"}
              onChange={() => setMode("identified")}
            />
            <span>
              <span className="font-semibold">Au nom de {me.org.name}</span>{" "}
              (recommandé) — l&apos;acheteur saura que vous avez retiré le
              dossier et vous préviendra des modifications
            </span>
          </label>
          <label className="flex gap-3 rounded-md border border-slate-300 p-3 text-sm">
            <input
              type="radio"
              name="retrieval-mode"
              checked={mode === "anonymous"}
              onChange={() => setMode("anonymous")}
            />
            <span>
              <span className="font-semibold">Anonymement</span> —
              l&apos;acheteur ne vous préviendra pas ; Pilao vérifiera chaque
              jour si le dossier change
            </span>
          </label>
        </fieldset>
        {mode === "identified" && (
          <div className="space-y-3 rounded-md bg-slate-50 p-3 text-sm">
            <p>
              Transmis à {site} : <strong>{me.org.name}</strong>, SIRET{" "}
              {me.org.siret}, et le contact ci-dessous.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Prénom" htmlFor="retrieval-first">
                <Input
                  id="retrieval-first"
                  value={form.first_name}
                  onChange={(e) =>
                    setForm({ ...form, first_name: e.target.value })
                  }
                />
              </Field>
              <Field label="Nom" htmlFor="retrieval-last">
                <Input
                  id="retrieval-last"
                  value={form.last_name}
                  onChange={(e) =>
                    setForm({ ...form, last_name: e.target.value })
                  }
                />
              </Field>
            </div>
            <Field label="E-mail du contact" htmlFor="retrieval-email">
              <Input
                id="retrieval-email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </Field>
          </div>
        )}
        <p className="text-xs text-slate-600">
          En validant, Pilao accepte en votre nom les{" "}
          {termsUrl ? (
            <a
              href={termsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
            >
              conditions d&apos;utilisation de la plateforme de l&apos;acheteur
            </a>
          ) : (
            "conditions d'utilisation de la plateforme de l'acheteur"
          )}
          .
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
          />
          Retenir ce choix pour les prochains dossiers
        </label>
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" busy={busy} disabled={!complete}>
            Récupérer le DCE
          </Button>
        </div>
      </form>
    </dialog>
  );
}
