import { create } from "zustand";

export interface SelectionState {
  selectedNodeId: string | null;
  selectedEdgeKey: string | null;
  selectedEvidenceId: string | null;
  pinEvidencePanel: boolean;
  selectNode: (nodeId: string | null) => void;
  selectEdge: (edgeKey: string | null) => void;
  selectEvidence: (evidenceId: string | null) => void;
  togglePinEvidence: () => void;
  clear: () => void;
}

export const useSelectionStore = create<SelectionState>((set) => ({
  selectedNodeId: null,
  selectedEdgeKey: null,
  selectedEvidenceId: null,
  pinEvidencePanel: false,
  selectNode: (selectedNodeId) =>
    set((state) => ({
      selectedNodeId,
      selectedEdgeKey: selectedNodeId ? state.selectedEdgeKey : null
    })),
  selectEdge: (selectedEdgeKey) =>
    set((state) => ({
      selectedEdgeKey,
      selectedNodeId: selectedEdgeKey ? state.selectedNodeId : null
    })),
  selectEvidence: (selectedEvidenceId) => set({ selectedEvidenceId }),
  togglePinEvidence: () => set((state) => ({ pinEvidencePanel: !state.pinEvidencePanel })),
  clear: () => set({ selectedEdgeKey: null, selectedNodeId: null, selectedEvidenceId: null })
}));
