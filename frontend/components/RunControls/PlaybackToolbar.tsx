"use client";

import { useEffect } from "react";
import clsx from "clsx";
import { usePlaybackStore } from "@/stores/usePlaybackStore";

interface PlaybackToolbarProps {
  traceId: string;
  onSeek?: (seq: number) => void;
}

const SPEED_OPTIONS: Array<{ label: string; value: 0.5 | 1 | 1.5 | 2 }> = [
  { label: "0.5×", value: 0.5 },
  { label: "1×", value: 1 },
  { label: "1.5×", value: 1.5 },
  { label: "2×", value: 2 }
];

export function PlaybackToolbar({ traceId, onSeek }: PlaybackToolbarProps) {
  const status = usePlaybackStore((state) => state.status);
  const steps = usePlaybackStore((state) => state.steps);
  const cursorSeq = usePlaybackStore((state) => state.cursorSeq);
  const setStatus = usePlaybackStore((state) => state.setStatus);
  const seekTo = usePlaybackStore((state) => state.seekTo);
  const speed = usePlaybackStore((state) => state.playbackSpeed);
  const setSpeed = usePlaybackStore((state) => state.setPlaybackSpeed);

  useEffect(() => {
    if (status !== "playing") {
      return;
    }
    const handle = window.setInterval(() => {
      const currentIndex = steps.findIndex((step) => step.seq === cursorSeq);
      if (currentIndex >= 0 && currentIndex < steps.length - 1) {
        const nextSeq = steps[currentIndex + 1].seq;
        seekTo(nextSeq);
        onSeek?.(nextSeq);
      } else {
        setStatus("paused");
      }
    }, (1_000 / speed) * 1.2);
    return () => window.clearInterval(handle);
  }, [status, steps, cursorSeq, seekTo, setStatus, speed, onSeek]);

  const hasNext = steps.some((step) => step.seq > (cursorSeq ?? -Infinity));
  const hasPrev = steps.some((step) => step.seq < (cursorSeq ?? Infinity));

  const queueSeek = (direction: "next" | "prev") => {
    if (!steps.length) return;
    const ordered = [...steps].sort((a, b) => a.seq - b.seq);
    if (direction === "next") {
      const target = ordered.find((step) => step.seq > (cursorSeq ?? -Infinity));
      if (target) {
        seekTo(target.seq);
        onSeek?.(target.seq);
      }
    } else {
      const reversed = [...ordered].reverse();
      const target = reversed.find((step) => step.seq < (cursorSeq ?? Infinity));
      if (target) {
        seekTo(target.seq);
        onSeek?.(target.seq);
      }
    }
  };

  return (
    <div className="flex items-center justify-between border-b border-white/5 bg-surface/80 px-4 py-3">
      <div>
        <p className="text-xs uppercase tracking-wide text-foreground/50">Trace</p>
        <p className="font-mono text-sm text-foreground">{traceId}</p>
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded border border-white/10 px-2 py-1 text-xs text-foreground/70 hover:border-white/30"
          onClick={() => queueSeek("prev")}
          disabled={!hasPrev}
        >
          Prev
        </button>
        <button
          type="button"
          className={clsx(
            "rounded px-3 py-1 text-sm font-semibold text-primary-foreground transition-colors",
            status === "playing" ? "bg-danger" : "bg-primary",
            !steps.length && "cursor-not-allowed opacity-50"
          )}
          onClick={() => setStatus(status === "playing" ? "paused" : "playing")}
          disabled={!steps.length}
        >
          {status === "playing" ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          className="rounded border border-white/10 px-2 py-1 text-xs text-foreground/70 hover:border-white/30"
          onClick={() => queueSeek("next")}
          disabled={!hasNext}
        >
          Next
        </button>
        <div className="flex items-center gap-1 pl-3">
          {SPEED_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={clsx(
                "rounded px-2 py-1 text-xs",
                speed === option.value
                  ? "bg-primary/20 text-primary"
                  : "border border-white/10 text-foreground/60 hover:border-white/20"
              )}
              onClick={() => setSpeed(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
