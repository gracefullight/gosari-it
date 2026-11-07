import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { PersonalContact } from "@/lib/gosari.types";

export const RELATIONSHIPS: PersonalContact["relationship"][] = [
  "가족",
  "친척",
  "친구",
  "이웃",
  "동료",
  "기타",
];

export interface ShareContactValues {
  name: string;
  relationship: PersonalContact["relationship"];
  notes: string;
}

interface ShareContactDialogProps {
  mode: "create" | "update";
  contact: PersonalContact | null;
  error: string | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (values: ShareContactValues) => void;
}

export function ShareContactDialog({
  mode,
  contact,
  error,
  busy,
  onCancel,
  onSave,
}: ShareContactDialogProps) {
  const [name, setName] = useState(mode === "update" ? (contact?.name ?? "") : "");
  const [relationship, setRelationship] = useState<PersonalContact["relationship"]>(
    mode === "update" ? (contact?.relationship ?? "가족") : "가족"
  );
  const [notes, setNotes] = useState(mode === "update" ? (contact?.notes ?? "") : "");

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{mode === "create" ? "지인 추가" : "지인 수정"}</DialogTitle>
          <DialogDescription>이름과 나와의 관계를 기록하세요.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="contact-name">이름</Label>
            <Input
              id="contact-name"
              autoFocus
              maxLength={100}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="contact-relationship">관계</Label>
            <select
              id="contact-relationship"
              value={relationship}
              onChange={(event) =>
                setRelationship(event.target.value as PersonalContact["relationship"])
              }
              className="min-h-11 rounded-lg border border-input bg-background px-3 text-base"
            >
              {RELATIONSHIPS.map((relation) => (
                <option key={relation} value={relation}>
                  {relation}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="contact-notes">메모</Label>
            <Textarea
              id="contact-notes"
              rows={3}
              maxLength={2000}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="기억할 내용을 적어 주세요."
            />
          </div>
          {error ? (
            <p role="alert" className="text-base text-destructive">
              {error}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            취소
          </Button>
          <Button
            disabled={busy || !name.trim()}
            onClick={() => onSave({ name, relationship, notes })}
          >
            내용 확인
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
