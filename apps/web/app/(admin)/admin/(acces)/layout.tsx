import { Logo } from "@/components/logo";

/** The way into the administration (activation, sign-in): one card, on navy. */
export default function AdminAccessLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center bg-brand-navy px-4 py-10">
      <div className="mb-3 rounded-lg bg-white px-4 py-2">
        <Logo />
      </div>
      <p className="mb-6 text-xs font-bold uppercase tracking-widest text-brand-green">
        Administration
      </p>
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-sm">
        {children}
      </div>
    </main>
  );
}
