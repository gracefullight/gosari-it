import { SideNavigation } from "@gracefullight/krds-tw";
import { useAtom, useSetAtom } from "jotai";
import { useChat } from "../hooks/useChat";
import { activeFeatureAtom, type Feature, messagesAtom } from "../stores/app";

const FEATURES: Feature[] = ["나들이", "지역 탐색", "내 수첩", "나눔", "가격 조사"];

interface LnbProps {
  open: boolean;
  onToggle: () => void;
  onEndSession: () => void;
}

export function Lnb({ open, onToggle, onEndSession }: LnbProps) {
  const [activeFeature, setActiveFeature] = useAtom(activeFeatureAtom);
  const setMessages = useSetAtom(messagesAtom);
  const { openFeature } = useChat();

  const items = FEATURES.map((feature) => ({
    id: feature,
    label: feature,
    active: activeFeature === feature,
    onClick: () => {
      setActiveFeature(feature);
      openFeature(feature);
    },
  }));

  return (
    <nav
      aria-label="주 메뉴"
      className={`flex shrink-0 flex-col border-r border-gray-200 bg-white transition-all ${
        open ? "w-64" : "w-16"
      }`}
    >
      <div className="flex items-center justify-between border-b border-gray-200 p-4">
        {Boolean(open) && <span className="text-lg font-bold text-green-800">고사리잇</span>}
        <button
          type="button"
          onClick={onToggle}
          aria-label={open ? "메뉴 접기" : "메뉴 펼치기"}
          className="rounded p-2 text-gray-600 hover:bg-gray-100"
        >
          {open ? "◀" : "▶"}
        </button>
      </div>
      {open ? (
        <>
          <div className="p-3">
            <button
              type="button"
              className="w-full rounded-lg border border-green-700 px-4 py-2 text-base font-semibold text-green-800 hover:bg-green-50"
              onClick={() => {
                setMessages([]);
                setActiveFeature(null);
              }}
            >
              + 새 대화
            </button>
          </div>
          <SideNavigation items={items} aria-label="다섯 기능" />
          <div className="mt-auto flex flex-col gap-1 border-t border-gray-200 p-3">
            <button
              type="button"
              className="rounded px-4 py-2 text-left text-sm text-gray-600 hover:bg-gray-100"
              onClick={() => {
                setMessages([
                  {
                    id: `help-${Date.now()}`,
                    role: "assistant",
                    kind: "text",
                    text: "한 문장으로 질문하면 필요한 조건은 대화 중에 확인합니다. 개인 기록은 현재 세션에서만 유지되고 외부로 전송되지 않습니다. 지도 타일과 외부 API는 설정에 따라 제한될 수 있습니다.",
                  },
                ]);
              }}
            >
              사용 안내
            </button>
            <button
              type="button"
              className="rounded px-4 py-2 text-left text-sm text-red-700 hover:bg-red-50"
              onClick={onEndSession}
            >
              세션 종료
            </button>
          </div>
        </>
      ) : (
        <div className="flex flex-col items-center gap-2 p-2">
          {FEATURES.map((feature) => (
            <button
              key={feature}
              type="button"
              title={feature}
              aria-label={feature}
              aria-current={activeFeature === feature ? "page" : undefined}
              className={`h-11 w-11 rounded-lg text-xs font-semibold ${
                activeFeature === feature
                  ? "bg-green-100 text-green-900"
                  : "text-gray-600 hover:bg-gray-100"
              }`}
              onClick={() => {
                setActiveFeature(feature);
                openFeature(feature);
              }}
            >
              {feature.slice(0, 2)}
            </button>
          ))}
        </div>
      )}
    </nav>
  );
}
