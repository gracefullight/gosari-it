import { XIcon } from "@phosphor-icons/react";
import { type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export function AgentResultDetailDialog({
  children,
  open,
  onOpenChange,
}: {
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const [localOpen, setLocalOpen] = useState(false);
  const changeOpen = onOpenChange ?? setLocalOpen;
  return (
    <>
      <section
        aria-label="조회 결과"
        className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2 text-base"
      >
        <Button variant="outline" className="min-h-11 text-base" onClick={() => changeOpen(true)}>
          상세 보기
        </Button>
      </section>
      <Dialog open={open ?? localOpen} onOpenChange={changeOpen}>
        <DialogContent
          showCloseButton={false}
          className="grid max-h-[85dvh] grid-rows-[auto_minmax(0,1fr)] overflow-hidden text-base sm:max-w-6xl"
        >
          <DialogHeader className="flex-row items-center justify-between gap-4">
            <DialogTitle className="text-xl">조회 결과</DialogTitle>
            <DialogClose
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  className="min-h-11 min-w-11"
                  aria-label="상세 보기 닫기"
                />
              }
            >
              <XIcon aria-hidden="true" />
            </DialogClose>
          </DialogHeader>
          <div className="min-h-0 min-w-0 overflow-y-auto overscroll-contain space-y-4">
            {children}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
