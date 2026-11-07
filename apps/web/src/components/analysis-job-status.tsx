import { useAtomValue } from "jotai";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { cancelAnalysisJob } from "@/lib/analysis-jobs";
import { activeFeatureAtom, analysisJobsAtom } from "@/stores/chat.atoms";

export function AnalysisJobStatus() {
  const feature = useAtomValue(activeFeatureAtom);
  const jobs = useAtomValue(analysisJobsAtom);
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const visible = Object.entries(jobs).filter(([, job]) => job.feature === feature);
  if (!visible.length) return null;
  return (
    <div className="space-y-2">
      {visible.map(([id, job]) => (
        <div
          key={id}
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-muted px-4 py-2"
        >
          <p role="status" className="text-base">
            {job.message}
          </p>
          <Button
            variant="ghost"
            disabled={cancelling === id}
            onClick={async () => {
              setCancelling(id);
              setError(null);
              try {
                await cancelAnalysisJob(id);
              } catch {
                setError("조회를 취소하지 못했습니다. 다시 시도해 주세요.");
              } finally {
                setCancelling(null);
              }
            }}
          >
            조회 취소
          </Button>
        </div>
      ))}
      {error ? (
        <p role="alert" className="text-base text-destructive">
          {error}
        </p>
      ) : null}
    </div>
  );
}
