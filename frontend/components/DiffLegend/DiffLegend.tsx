"use client";

export function DiffLegend() {
  return (
    <div className="border-t border-white/5 bg-surface/60 px-4 py-3 text-xs text-foreground/60">
      <div className="flex items-center gap-4">
        <LegendSwatch className="bg-foreground/20" label="Match" />
        <LegendSwatch className="bg-warning/40" label="Mismatch" />
        <LegendSwatch className="bg-primary/30" label="Primary only" />
        <LegendSwatch className="bg-secondary/30" label="Secondary only" />
      </div>
    </div>
  );
}

function LegendSwatch({ className, label }: { className: string; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-3 w-3 rounded ${className}`} />
      <span>{label}</span>
    </div>
  );
}
