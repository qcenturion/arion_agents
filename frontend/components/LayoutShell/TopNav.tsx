"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import clsx from "clsx";

const NAV_ITEMS = [
  { href: "/", label: "Runs" },
  { href: "/graphs", label: "Graphs" },
  { href: "/config", label: "Config" }
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-white/5 bg-background/60 backdrop-blur">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-6">
        <Link href="/" className="flex items-center gap-3">
          <Image src="/assets/arion-logo.png" alt="Arion Logo" width={48} height={48} />
          <span className="font-semibold tracking-tight text-xl">
            Arion Control Plane
          </span>
        </Link>
        <nav className="flex items-center gap-6 text-sm font-medium">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href || pathname?.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "transition-colors",
                  active ? "text-primary-foreground" : "text-foreground/70 hover:text-foreground"
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
