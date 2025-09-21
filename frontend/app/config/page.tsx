import { Suspense } from "react";
import { ConfigWorkbench } from "@/components/Config/ConfigWorkbench";

export default function ConfigPage() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <Suspense fallback={<div className="p-6 text-sm text-foreground/60">Loading configuration…</div>}>
        <ConfigWorkbench />
      </Suspense>
    </div>
  );
}
