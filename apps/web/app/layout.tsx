import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Document Resurrection AI",
  description: "Bad photo in, source-quality document out.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
