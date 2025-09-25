import { create } from "zustand";

interface RunMetadataState {
  networkName?: string;
  setNetworkName: (name?: string) => void;
  clear: () => void;
}

export const useRunMetadataStore = create<RunMetadataState>((set) => ({
  networkName: undefined,
  setNetworkName: (name) => set({ networkName: name }),
  clear: () => set({ networkName: undefined })
}));
