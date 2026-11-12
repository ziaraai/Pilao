/** The line icons of the application (24×24, stroke = current text colour). */
export type IconName =
  | "dashboard"
  | "tenders"
  | "bids"
  | "vault"
  | "documents"
  | "profile"
  | "logout"
  | "menu"
  | "close"
  | "todo"
  | "start"
  | "results"
  | "settings";

const PATHS: Record<IconName, React.ReactNode> = {
  dashboard: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
  tenders: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </>
  ),
  bids: (
    <path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-10Z" />
  ),
  vault: (
    <>
      <path d="M12 3.5 5 6.2v5.3c0 4.3 3 7.6 7 9 4-1.4 7-4.7 7-9V6.2L12 3.5Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  documents: (
    <>
      <path d="M7 3.5h7l5 5v10.5a1.5 1.5 0 0 1-1.5 1.5h-10.5a1.5 1.5 0 0 1-1.5-1.5v-14a1.5 1.5 0 0 1 1.5-1.5Z" />
      <path d="M14 3.5v5h5M9 13h6M9 16.5h6" />
    </>
  ),
  profile: (
    <>
      <path d="M4.5 20.5v-15a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v15" />
      <path d="M15.5 9.5h2a2 2 0 0 1 2 2v9M3 20.5h18M8.5 7.5h3M8.5 11h3M8.5 14.5h3" />
    </>
  ),
  logout: (
    <>
      <path d="M14.5 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="m10 16.5-4.5-4.5L10 7.5M5.5 12h10" />
    </>
  ),
  menu: <path d="M4 6.5h16M4 12h16M4 17.5h16" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  todo: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" />
      <path d="m8 12 3 3 5-6" />
    </>
  ),
  start: (
    <>
      <path d="M5.5 21V4" />
      <path d="M5.5 4.5h11l-2.5 4 2.5 4h-11" />
    </>
  ),
  results: <path d="M4 20.5h16M7 17v-5M12 17V7M17 17v-8" />,
  settings: (
    <>
      <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
      <circle cx="15" cy="7" r="2" />
      <circle cx="9" cy="17" r="2" />
    </>
  ),
};

export function Icon({
  name,
  className = "h-5 w-5",
}: {
  name: IconName;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={`shrink-0 ${className}`}
    >
      {PATHS[name]}
    </svg>
  );
}
