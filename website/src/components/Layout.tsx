import type { ReactNode } from "react";
import { SiteHeader } from "./SiteHeader";
import { SiteFooter } from "./SiteFooter";
import { AmbientBackdrop } from "./AmbientBackdrop";
import { useRefraction } from "@/lib/useRefraction";

export function Layout({ children }: { children: ReactNode }) {
  useRefraction();

  return (
    <>
      <AmbientBackdrop />
      <SiteHeader />
      <main className="min-h-screen pt-16">{children}</main>
      <SiteFooter />
    </>
  );
}
