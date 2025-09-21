import { create } from "zustand";
import type { RunEnvelope } from "@/lib/api/types";

export type PlaybackStatus = "idle" | "playing" | "paused" | "live";

export interface PlaybackState {
  steps: RunEnvelope[];
  cursorSeq: number | null;
  status: PlaybackStatus;
  playbackSpeed: 0.5 | 1 | 1.5 | 2;
  lastSeq: number;
  setInitialSteps: (steps: RunEnvelope[]) => void;
  appendStep: (step: RunEnvelope) => void;
  setStatus: (status: PlaybackStatus) => void;
  seekTo: (seq: number) => void;
  setPlaybackSpeed: (speed: PlaybackState["playbackSpeed"]) => void;
  reset: () => void;
}

export const usePlaybackStore = create<PlaybackState>((set, get) => ({
  steps: [],
  cursorSeq: null,
  status: "idle",
  playbackSpeed: 1,
  lastSeq: 0,
  setInitialSteps: (steps) => {
    const sorted = [...steps].sort((a, b) => a.seq - b.seq);
    set({
      steps: sorted,
      cursorSeq: sorted.length ? sorted[sorted.length - 1].seq : null,
      lastSeq: sorted.length ? sorted[sorted.length - 1].seq : 0,
      status: sorted.length ? "paused" : "idle"
    });
  },
  appendStep: (step) => {
    const { steps, lastSeq } = get();
    if (steps.some((existing) => existing.seq === step.seq)) {
      return;
    }
    const insertIndex = findInsertIndex(steps, step.seq);
    const nextSteps = [...steps.slice(0, insertIndex), step, ...steps.slice(insertIndex)];
    set({
      steps: nextSteps,
      lastSeq: Math.max(lastSeq, step.seq),
      status: "live",
      cursorSeq: step.seq
    });
  },
  setStatus: (status) => set({ status }),
  seekTo: (seq) => {
    const { steps } = get();
    if (!steps.some((step) => step.seq === seq)) {
      return;
    }
    set({ cursorSeq: seq, status: "paused" });
  },
  setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),
  reset: () => set({ steps: [], cursorSeq: null, status: "idle", lastSeq: 0 })
}));

function findInsertIndex(steps: RunEnvelope[], seq: number): number {
  let low = 0;
  let high = steps.length;
  while (low < high) {
    const mid = Math.floor((low + high) / 2);
    if (steps[mid].seq < seq) {
      low = mid + 1;
    } else {
      high = mid;
    }
  }
  return low;
}

export function useCurrentStep(): RunEnvelope | null {
  return usePlaybackStore((state) => {
    if (state.cursorSeq == null) {
      return null;
    }
    return state.steps.find((step) => step.seq === state.cursorSeq) ?? null;
  });
}
