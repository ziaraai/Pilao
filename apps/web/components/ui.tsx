import type {
  ButtonHTMLAttributes,
  ComponentProps,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

import type { Tone } from "@/lib/labels";

const toneClasses: Record<Tone, string> = {
  ok: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  warning: "bg-amber-50 text-amber-900 ring-amber-200",
  danger: "bg-red-50 text-red-800 ring-red-200",
  info: "bg-sky-50 text-sky-800 ring-sky-200",
  neutral: "bg-slate-100 text-slate-700 ring-slate-200",
};

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  busy?: boolean;
};

export function Button({
  variant = "primary",
  busy,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonProps) {
  const styles = {
    primary:
      "bg-brand-navy text-white hover:bg-[#0a2a63] focus-visible:outline-brand-navy",
    secondary:
      "bg-white text-brand-navy ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
    danger:
      "bg-white text-red-700 ring-1 ring-inset ring-red-300 hover:bg-red-50",
    ghost: "text-brand-navy hover:bg-slate-100",
  }[variant];
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner() {
  return (
    <span
      className="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent"
      aria-hidden="true"
    />
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
  htmlFor: string;
}) {
  return (
    <div className="space-y-1">
      <label
        htmlFor={htmlFor}
        className="block text-sm font-medium text-slate-800"
      >
        {label}
      </label>
      {children}
      {hint && !error && <p className="text-xs text-slate-500">{hint}</p>}
      {error && (
        <p className="text-xs text-red-700" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

const controlBase =
  "block rounded-md border-0 px-3 py-2 text-sm text-slate-900 ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-brand-navy disabled:bg-slate-50";

/** Full width unless the caller sets a width (Tailwind cannot let a later class win). */
export function controlClass(extra = ""): string {
  const sized = /(^|\s)(w-|flex-1|max-w-|min-w-)/.test(extra);
  return `${controlBase} ${sized ? "" : "w-full"} ${extra}`.trim();
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={controlClass(props.className)} />;
}

export function Textarea(props: ComponentProps<"textarea">) {
  return <textarea {...props} className={controlClass(props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={controlClass(props.className)} />;
}

export function Card({
  title,
  actions,
  children,
  id,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  id?: string;
}) {
  return (
    <section
      id={id}
      className="rounded-lg bg-white p-5 shadow-sm ring-1 ring-slate-200"
    >
      {(title || actions) && (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && (
            <h2 className="text-base font-semibold text-brand-navy">{title}</h2>
          )}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Alert({
  tone = "info",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <div
      role={tone === "danger" ? "alert" : "status"}
      className={`rounded-md px-4 py-3 text-sm ring-1 ring-inset ${toneClasses[tone]}`}
    >
      {children}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-md border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-500">
      {children}
    </p>
  );
}

export function PageTitle({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

export function Loading() {
  return (
    <div
      className="flex items-center gap-2 py-8 text-sm text-slate-500"
      role="status"
    >
      <Spinner /> Chargement…
    </div>
  );
}
