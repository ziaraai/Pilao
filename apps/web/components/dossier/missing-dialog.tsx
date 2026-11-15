"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

import { AddItemForm } from "@/components/profile/add-item-form";
import { CompanyIdentity } from "@/components/profile/company-identity";
import { AddReferenceForm } from "@/components/profile/references";
import { Button } from "@/components/ui";
import { KIND_META } from "@/lib/missing";
import {
  CERTIFICATION_COLUMNS,
  EQUIPMENT_COLUMNS,
  HUMAN_RESOURCE_COLUMNS,
} from "@/lib/profile-columns";
import type { MissingKind } from "@/lib/types";

const LISTS = {
  staff: { path: "/profile/human-resources", columns: HUMAN_RESOURCE_COLUMNS },
  equipment: { path: "/profile/equipment", columns: EQUIPMENT_COLUMNS },
  certification: {
    path: "/profile/certifications",
    columns: CERTIFICATION_COLUMNS,
  },
} as const;

/**
 * « Ce qu'il manque » (ADR-048): add a company's datum to the profile without leaving the
 * dossier. A native modal ``<dialog>`` (the focus stays inside, Échap closes it). What is
 * added serves every dossier; ``onSaved`` then completes the sentences that needed it.
 */
export function AddToProfileDialog({
  kind,
  markerText,
  onClose,
  onSaved,
}: {
  kind: MissingKind;
  markerText: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  const meta = KIND_META[kind];
  const list =
    kind === "staff" || kind === "equipment" || kind === "certification"
      ? LISTS[kind]
      : null;

  return (
    <dialog
      ref={ref}
      aria-labelledby="missing-dialog-title"
      onClose={onClose}
      className="w-[min(44rem,calc(100vw-2rem))] rounded-lg p-0 shadow-xl backdrop:bg-slate-900/50"
    >
      <div className="space-y-3 p-5">
        <h2
          id="missing-dialog-title"
          className="text-lg font-bold text-brand-navy"
        >
          {meta.icon} {meta.button ?? "Compléter"}
        </h2>
        <p className="text-sm text-slate-700">
          Il manque : <strong>{markerText}</strong>. Ce que vous ajoutez est
          enregistré dans votre profil et servira à tous vos dossiers ; Pilao
          complète ensuite les phrases concernées.
        </p>
        {list && (
          <AddItemForm
            path={list.path}
            columns={list.columns}
            onSaved={onSaved}
          />
        )}
        {kind === "reference" && <AddReferenceForm onSaved={onSaved} />}
        {kind === "identity" && <CompanyIdentity onSaved={onSaved} />}
        {(kind === "staff" || kind === "equipment") && (
          <p className="text-sm">
            <Link
              href="/profil?onglet=moyens"
              className="font-semibold text-sky-800 underline"
            >
              Importer un fichier Excel
            </Link>
          </p>
        )}
        <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-3">
          <Button variant="secondary" onClick={onSaved}>
            J&apos;ai déjà cette donnée dans mon profil
          </Button>
          <Button variant="ghost" onClick={() => ref.current?.close()}>
            Fermer
          </Button>
        </div>
      </div>
    </dialog>
  );
}
