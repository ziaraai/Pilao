"use client";

import { useRef, useState } from "react";

import { Button } from "@/components/ui";

/**
 * File picker in French (the browser's own button follows its language: "Choose Files"),
 * plus the action button. The real <input type="file"> stays in the page, keyboard-focusable.
 */
export function UploadButton({
  id,
  label,
  accept,
  multiple,
  busy,
  onFiles,
  children,
}: {
  id: string;
  label: string;
  accept?: string;
  multiple?: boolean;
  busy?: boolean;
  onFiles: (files: File[]) => void;
  children?: React.ReactNode;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [names, setNames] = useState<string[]>([]);
  return (
    <div className="flex flex-wrap items-center gap-3">
      <input
        id={id}
        ref={input}
        type="file"
        accept={accept}
        multiple={multiple}
        className="peer sr-only"
        onChange={(e) =>
          setNames(Array.from(e.target.files ?? []).map((f) => f.name))
        }
      />
      <label
        htmlFor={id}
        className="cursor-pointer rounded-md bg-slate-100 px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-200 peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-brand-navy"
      >
        {multiple
          ? "Choisir les fichiers à déposer"
          : "Choisir le fichier à déposer"}
      </label>
      <span
        className="max-w-64 truncate text-sm text-slate-600"
        aria-live="polite"
      >
        {names.length === 0
          ? "Aucun fichier choisi"
          : names.length === 1
            ? names[0]
            : `${names.length} fichiers choisis`}
      </span>
      {children}
      <Button
        type="button"
        busy={busy}
        disabled={names.length === 0}
        onClick={() => {
          const files = Array.from(input.current?.files ?? []);
          if (files.length) onFiles(files);
          if (input.current) input.current.value = "";
          setNames([]);
        }}
      >
        {label}
      </Button>
    </div>
  );
}
