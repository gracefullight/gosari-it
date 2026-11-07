import { CaretLeftIcon, CaretRightIcon } from "@phosphor-icons/react";
import { type ReactNode, useId, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

interface CandidateSlide {
  id: string;
  rank?: number | null;
  content: ReactNode;
}

export function OutingCandidateCarousel({ items }: { items: CandidateSlide[] }) {
  const [selected, setSelected] = useState(0);
  const viewportRef = useRef<HTMLElement>(null);
  const requestedRef = useRef<number | null>(null);
  const viewportId = useId();
  const widthRef = useRef(0);
  const active = Math.min(selected, Math.max(0, items.length - 1));
  const activeId = items[active]?.id;

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const slide = viewport?.children[active];
    if (!viewport || !(slide instanceof HTMLElement) || slide.dataset.candidateId !== activeId)
      return;
    function fitHeight() {
      if (viewport && widthRef.current !== viewport.clientWidth) {
        if (widthRef.current) {
          requestedRef.current = null;
          viewport.scrollTo({ left: active * viewport.clientWidth, behavior: "instant" });
        }
        widthRef.current = viewport.clientWidth;
      }
      const height = (slide as HTMLElement).getBoundingClientRect().height;
      if (height > 0 && viewport) viewport.style.height = `${height}px`;
    }
    fitHeight();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(fitHeight);
    observer.observe(slide);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [active, activeId]);

  function show(index: number) {
    const viewport = viewportRef.current;
    const next = Math.max(0, Math.min(index, items.length - 1));
    setSelected(next);
    if (!viewport) return;
    requestedRef.current = next;
    viewport.scrollTo({
      left: next * viewport.clientWidth,
      behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
  }

  if (!items.length) return null;
  return (
    <section aria-label="나들이 후보" aria-roledescription="캐러셀" className="min-w-0 max-w-full">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p role="status" aria-live="polite" aria-atomic="true" className="text-base tabular-nums">
          <span className="font-semibold text-primary">{items[active].rank ?? active + 1}순위</span>
          <span className="ml-2 text-muted-foreground">
            {active + 1} / {items.length} 후보
          </span>
        </p>
        <div className="flex shrink-0 gap-2">
          <Button
            variant="outline"
            size="icon-lg"
            aria-label="이전 후보"
            aria-controls={viewportId}
            disabled={active === 0}
            onClick={() => show(active - 1)}
          >
            <CaretLeftIcon aria-hidden="true" className="size-5" />
          </Button>
          <Button
            variant="outline"
            size="icon-lg"
            aria-label="다음 후보"
            aria-controls={viewportId}
            disabled={active === items.length - 1}
            onClick={() => show(active + 1)}
          >
            <CaretRightIcon aria-hidden="true" className="size-5" />
          </Button>
        </div>
      </div>
      {/* biome-ignore lint/a11y/noNoninteractiveElementInteractions: This named scroll viewport supports its native pointer scrolling and keyboard arrows. */}
      <section
        id={viewportId}
        ref={viewportRef}
        aria-label="후보 넘겨 보기"
        // biome-ignore lint/a11y/noNoninteractiveTabindex: Keyboard users need focus on this named horizontal scroll region.
        tabIndex={0}
        className="flex min-w-0 snap-x snap-mandatory items-start overflow-x-auto overflow-y-hidden rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring motion-reduce:scroll-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        onPointerDown={() => {
          requestedRef.current = null;
        }}
        onWheel={() => {
          requestedRef.current = null;
        }}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            show(active + (event.key === "ArrowLeft" ? -1 : 1));
          }
        }}
        onScroll={(event) => {
          const viewport = event.currentTarget;
          if (!viewport.clientWidth) return;
          const requested = requestedRef.current;
          if (requested !== null) {
            if (Math.abs(viewport.scrollLeft - requested * viewport.clientWidth) > 1) return;
            requestedRef.current = null;
          }
          setSelected(
            Math.max(
              0,
              Math.min(items.length - 1, Math.round(viewport.scrollLeft / viewport.clientWidth))
            )
          );
        }}
      >
        {items.map((item, index) => (
          <article
            key={item.id}
            data-candidate-id={item.id}
            aria-roledescription="후보"
            aria-label={`${index + 1} / ${items.length} 후보`}
            aria-hidden={index !== active}
            inert={index !== active}
            className="min-w-0 flex-[0_0_100%] snap-start snap-always"
          >
            {item.content}
          </article>
        ))}
      </section>
    </section>
  );
}
