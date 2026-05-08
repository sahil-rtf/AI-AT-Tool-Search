import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AT Tool Discovery — Pipeline Dashboard",
  description: "Configure, run, and monitor the AT Tool Discovery pipeline from your browser.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
