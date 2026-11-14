"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui";
import { acceptsFile, readyText } from "@/lib/upload";

/**
 * A drop zone that cannot be missed (users took the old grey picker for nothing and the
 * disabled « Déposer » for a broken button): a dashed blue area, « Glissez … ici » and a
 * real « Choisir sur mon ordinateur » button. Once a file is chosen, its name shows in green
 * and the action button appears. The real <input type="file"> stays in the page with its
 * ``id`` (keyboard, screen readers, tests), visually hidden.
 */
export function UploadButton({
  id,
  label,
  accept,
  multiple,
  busy,
  onFiles,
  children,
  title,
  hint,
  pickLabel = "Choisir sur mon ordinateur",
  compact = false,
}: {
  id: string;
  label: string;
  accept?: string;
  multiple?: boolean;
  busy?: boolean;
  onFiles: (files: File[]) => void;
  /** Placed next to the action button (e.g. the type of document). */
  children?: React.ReactNode;
  title?: string;
  hint?: string;
  pickLabel?: string;
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [chosen, setChosen] = useState<File[]>([]);
  const [over, setOver] = useState(false);
  const [refused, setRefused] = useState<string[]>([]);

  function choose(files: File[]) {
    const kept = files.filter((f) => acceptsFile(f.name, f.type, accept));
    setRefused(
      files
        .filter((f) => !acceptsFile(f.name, f.type, accept))
        .map((f) => f.name),
    );
    setChosen(multiple ? kept : kept.slice(0, 1));
  }

  function clear() {
    setChosen([]);
    setRefused([]);
    if (input.current) input.current.value = "";
  }

  const heading =
    title ??
    (multiple ? "Glissez vos fichiers ici" : "Glissez votre fichier ici");
  return (
    <div className="space-y-3">
      {/* No ``accept`` on the input: a phone greys out a file a site sent with a wrong type
          (a PDF from AWS saved as « unknown »). Every file can be picked; ``choose`` refuses an
          unsupported name and the server checks the real content. */}
      <input
        id={id}
        ref={input}
        type="file"
        multiple={multiple}
        className="peer sr-only"
        onChange={(e) => choose(Array.from(e.target.files ?? []))}
      />
      <label
        htmlFor={id}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          choose(Array.from(e.dataTransfer.files));
        }}
        className={`block cursor-pointer rounded-lg border-2 border-dashed text-center text-blue-900 transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand-navy ${compact ? "px-4 py-3" : "px-4 py-6"} ${over ? "border-blue-600 bg-blue-100" : "border-blue-400 bg-blue-50 hover:bg-blue-100"}`}
      >
        {!compact && (
          <span
            className="mx-auto mb-2 flex h-11 w-11 items-center justify-center rounded-full bg-blue-100"
            aria-hidden="true"
          >
            <svg
              viewBox="0 0 24 24"
              className="h-6 w-6"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />
            </svg>
          </span>
        )}
        <span className="block text-base font-bold">{heading}</span>
        {hint && <span className="block text-sm text-blue-800">{hint}</span>}
        <span className="mt-2 inline-block rounded-md border-2 border-blue-700 bg-white px-4 py-1.5 text-sm font-bold text-blue-700">
          {pickLabel}
        </span>
      </label>

      {refused.length > 0 && (
        <p className="text-sm text-red-700" role="alert">
          Format non accepté : {refused.join(", ")}
        </p>
      )}

      {chosen.length > 0 && (
        <div
          className="flex items-start gap-2 rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-900 ring-1 ring-inset ring-emerald-300"
          aria-live="polite"
        >
          <svg
            viewBox="0 0 24 24"
            className="mt-0.5 h-4 w-4 shrink-0"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            aria-hidden="true"
          >
            <path d="M5 12l5 5L20 7" />
          </svg>
          <span className="min-w-0 flex-1 break-words font-medium">
            {readyText(chosen.map((f) => f.name))}
          </span>
          <button
            type="button"
            onClick={clear}
            className="shrink-0 font-semibold text-emerald-900 underline"
          >
            Retirer
          </button>
        </div>
      )}

      {(children || chosen.length > 0) && (
        <div className="flex flex-wrap items-center gap-3">
          {children}
          {chosen.length > 0 && (
            <Button
              type="button"
              busy={busy}
              onClick={() => {
                const files = chosen;
                clear();
                onFiles(files);
              }}
            >
              {label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
