import type { Metadata } from "next";
import "./globals.css";
import { LayoutShell } from "@/components/LayoutShell/LayoutShell";

export const metadata: Metadata = {
  title: "Arion Control Plane",
  description: "Manage networks, agents, tools, and run playback",
  applicationName: "Arion Control Plane"
};

export default function RootLayout({
  children
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <LayoutShell>{children}</LayoutShell>
      </body>
    </html>
  );
}
