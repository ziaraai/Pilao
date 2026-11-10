import type { Metadata } from "next";

// The administration is not for search engines, and no page of the application links to it.
export const metadata: Metadata = {
  title: "Administration — Pilao",
  robots: { index: false, follow: false },
};

export default function AdminRootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
