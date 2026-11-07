import { atom } from "jotai";
import type { SelectedLocation } from "@/components/location-picker-dialog";

export interface NotebookDraft {
  date: string;
  text: string;
  aliases: string;
  amount: string;
  unit: string;
  location: SelectedLocation | null;
  evidenceIds: string[];
  privateRegionId: string | null;
  previewId?: string;
}

export const notebookDraftsAtom = atom<Record<string, NotebookDraft>>({});
export const clearCommittedNotebookDraftAtom = atom(null, (get, set, previewId: string) => {
  set(
    notebookDraftsAtom,
    Object.fromEntries(
      Object.entries(get(notebookDraftsAtom)).filter(([, draft]) => draft.previewId !== previewId)
    )
  );
});
