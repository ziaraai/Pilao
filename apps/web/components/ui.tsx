import type {
  ButtonHTMLAttributes,
  ComponentProps,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";

import { Icon, type IconName } from "@/components/icon";
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

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
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
      "bg-white text-brand-navy ring-1 ring-inset ring-slate-400 hover:bg-slate-50",
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

/**
 * One colour per part of the application, light tints with dark text (ADR-038): red what to
 * do and the risks, green the notices, blue the dossiers and what comes from the DCE, amber
 * the attestations, violet scoring, results and exports, Pilao green what Pilao writes and
 * the profile, sky the knowledge base, slate the neutral blocks (filters, settings).
 */
export type Color =
  "red" | "green" | "blue" | "amber" | "brand" | "violet" | "sky" | "slate";

const BAR: Record<Color, string> = {
  red: "border-t-red-500 border-b-red-200 bg-red-100 text-red-900",
  green:
    "border-t-emerald-500 border-b-emerald-200 bg-emerald-100 text-emerald-900",
  blue: "border-t-blue-500 border-b-blue-200 bg-blue-100 text-blue-900",
  amber: "border-t-amber-500 border-b-amber-200 bg-amber-100 text-amber-900",
  brand:
    "border-t-brand-green border-b-emerald-200 bg-[#dcfbf1] text-brand-navy",
  violet:
    "border-t-violet-500 border-b-violet-200 bg-violet-100 text-violet-900",
  sky: "border-t-sky-500 border-b-sky-200 bg-sky-100 text-sky-900",
  slate: "border-t-slate-400 border-b-slate-200 bg-slate-100 text-slate-800",
};

/** A coloured stripe on the left of a card: the state of one item (score, validity). */
const ACCENT: Record<Color, string> = {
  red: "border-l-[6px] border-l-red-500",
  green: "border-l-[6px] border-l-emerald-500",
  blue: "border-l-[6px] border-l-blue-500",
  amber: "border-l-[6px] border-l-amber-500",
  brand: "border-l-[6px] border-l-brand-green",
  violet: "border-l-[6px] border-l-violet-500",
  sky: "border-l-[6px] border-l-sky-500",
  slate: "border-l-[6px] border-l-slate-400",
};

const ICON_BOX: Record<Color, string> = {
  red: "bg-red-100 text-red-700 ring-red-300",
  green: "bg-emerald-100 text-emerald-700 ring-emerald-300",
  blue: "bg-blue-100 text-blue-700 ring-blue-300",
  amber: "bg-amber-100 text-amber-700 ring-amber-300",
  brand: "bg-[#dcfbf1] text-brand-navy ring-emerald-300",
  violet: "bg-violet-100 text-violet-700 ring-violet-300",
  sky: "bg-sky-100 text-sky-700 ring-sky-300",
  slate: "bg-slate-100 text-slate-700 ring-slate-300",
};

/** Column titles of a table (``<thead>`` cells or a header row). */
export const tableHead =
  "border-b border-slate-300 bg-slate-100 text-xs font-semibold uppercase tracking-wide text-slate-600";
/** A table row: a line between rows, every other row greyed. */
export const tableRow =
  "border-b border-slate-200 last:border-b-0 even:bg-slate-50";

/**
 * A block. With a title: a tinted title bar of its colour. ``flush``: no padding around the
 * content (lists and tables going edge to edge). ``accent``: a coloured stripe on the left.
 */
export function Card({
  title,
  actions,
  children,
  id,
  color = "slate",
  icon,
  flush = false,
  accent,
}: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  id?: string;
  color?: Color;
  icon?: IconName;
  flush?: boolean;
  accent?: Color;
}) {
  const titleId = id && title ? `${id}-titre` : undefined;
  return (
    <section
      id={id}
      aria-labelledby={titleId}
      className={`scroll-mt-20 overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm ${accent ? ACCENT[accent] : ""}`}
    >
      {(title || actions) && (
        <div
          className={`flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-t-4 px-5 py-2.5 ${BAR[color]}`}
        >
          {title && (
            <h2
              id={titleId}
              className="flex items-center gap-2 text-base font-bold"
            >
              {icon && <Icon name={icon} />}
              {title}
            </h2>
          )}
          {actions}
        </div>
      )}
      {flush ? children : <div className="p-5">{children}</div>}
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
  icon,
  color = "slate",
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  icon?: IconName;
  color?: Color;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="flex min-w-0 items-start gap-3">
        {icon && (
          <span
            className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ring-1 ring-inset ${ICON_BOX[color]}`}
            aria-hidden="true"
          >
            <Icon name={icon} className="h-6 w-6" />
          </span>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-brand-navy">{title}</h1>
          {subtitle && (
            <p className="mt-1 text-sm text-slate-600">{subtitle}</p>
          )}
        </div>
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
