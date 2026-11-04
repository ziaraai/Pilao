"use client";

import { createContext, useContext, useEffect, useState } from "react";

import { Alert, Button, Loading } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { DcePage, Source } from "@/lib/types";

const SourceContext = createContext<(s: Source) => void>(() => undefined);

/** Wraps the analysis: any <SourceLink> opens the cited page in a side panel. */
export function SourceViewer({ children }: { children: React.ReactNode }) {
  const [source, setSource] = useState<Source | null>(null);
  return (
    <SourceContext.Provider value={setSource}>
      {children}
      {source && (
        <SourcePanel source={source} onClose={() => setSource(null)} />
      )}
    </SourceContext.Provider>
  );
}

export function SourceLink({ source }: { source: Source | null | undefined }) {
  const open = useContext(SourceContext);
  if (!source) return null;
  const name = source.file.split("/").pop();
  return (
    <button
      type="button"
      onClick={() => open(source)}
      className="ml-1 whitespace-nowrap text-xs font-medium text-sky-700 underline hover:text-sky-900"
      title={`Voir la source : ${source.file}${source.page ? `, page ${source.page}` : ""}`}
    >
      [{name}
      {source.page ? ` p. ${source.page}` : ""}]
    </button>
  );
}

function SourcePanel({
  source,
  onClose,
}: {
  source: Source;
  onClose: () => void;
}) {
  const page = useApi<DcePage[]>(
    `/dce-files/${source.dce_file_id}/pages?from=${source.page ?? 1}&count=1`,
  );
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose(); // standard dialog key
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Source"
      className="fixed inset-0 z-50 flex justify-end bg-black/30"
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-xl overflow-y-auto bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-brand-navy">
              {source.file}
            </p>
            <p className="text-xs text-slate-500">
              {source.page ? `Page ${source.page}` : "Document non paginé"}
            </p>
          </div>
          <Button variant="ghost" onClick={onClose} autoFocus>
            Fermer
          </Button>
        </div>
        {page.error && <Alert tone="danger">{page.error}</Alert>}
        {!page.data ? (
          <Loading />
        ) : (
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-800">
            {page.data[0]?.text || "(page sans texte)"}
          </pre>
        )}
        {page.data?.[0]?.ocr_used && (
          <p className="mt-3 text-xs text-slate-500">
            Texte reconnu par OCR : vérifiez sur le document original.
          </p>
        )}
      </div>
    </div>
  );
}
