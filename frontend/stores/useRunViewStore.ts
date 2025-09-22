import { create } from "zustand";
import { persist } from "zustand/middleware";

export type RunViewMode = "timeline" | "graph";

interface RunViewState {
  view: RunViewMode;
  setView: (view: RunViewMode) => void;
}

export const useRunViewStore = create<RunViewState>()(
  persist(
    (set) => ({
      view: "timeline",
      setView: (view) => set({ view })
    }),
    {
      name: "arion.runView"
    }
  )
);
