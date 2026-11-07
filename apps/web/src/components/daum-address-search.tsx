import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";

interface PostcodeResult {
  address: string;
  roadAddress: string;
  jibunAddress: string;
}
interface PostcodeConstructor {
  new (options: {
    oncomplete: (data: PostcodeResult) => void;
    width: string;
    height: string;
  }): { embed(element: HTMLElement): void };
}
type PostcodeWindow = Window & {
  kakao?: { Postcode?: PostcodeConstructor };
  daum?: { Postcode?: PostcodeConstructor };
};
let sdkPromise: Promise<PostcodeConstructor> | null = null;

export function loadPostcode(): Promise<PostcodeConstructor> {
  const sdk =
    (window as PostcodeWindow).kakao?.Postcode ?? (window as PostcodeWindow).daum?.Postcode;
  if (sdk) return Promise.resolve(sdk);
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise<PostcodeConstructor>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://t1.kakaocdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js";
    script.async = true;
    const timeout = window.setTimeout(() => {
      script.remove();
      reject(new Error("주소 검색을 불러오지 못했습니다."));
    }, 12000);
    script.onload = () => {
      window.clearTimeout(timeout);
      const loaded =
        (window as PostcodeWindow).kakao?.Postcode ?? (window as PostcodeWindow).daum?.Postcode;
      if (loaded) resolve(loaded);
      else reject(new Error("주소 검색을 불러오지 못했습니다."));
    };
    script.onerror = () => {
      window.clearTimeout(timeout);
      script.remove();
      reject(new Error("주소 검색을 불러오지 못했습니다."));
    };
    document.head.appendChild(script);
  }).catch((error: unknown) => {
    sdkPromise = null;
    throw error;
  });
  return sdkPromise;
}

export function DaumAddressSearch({ onSelect }: { onSelect: (address: string) => void }) {
  const container = useRef<HTMLElement>(null);
  const callback = useRef(onSelect);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    callback.current = onSelect;
  }, [onSelect]);
  // biome-ignore lint/correctness/useExhaustiveDependencies: The retry token deliberately reloads a failed external SDK.
  useEffect(() => {
    let active = true;
    setError(null);
    loadPostcode()
      .then((Postcode) => {
        if (!active || !container.current) return;
        new Postcode({
          width: "100%",
          height: "100%",
          oncomplete: (data) =>
            callback.current(data.roadAddress || data.jibunAddress || data.address),
        }).embed(container.current);
      })
      .catch((err: unknown) => {
        if (active)
          setError(err instanceof Error ? err.message : "주소 검색을 불러오지 못했습니다.");
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  return (
    <div className="rounded-xl border border-border bg-card">
      {error ? (
        <div className="p-4">
          <p role="alert" className="mb-2 text-base text-destructive">
            {error}
          </p>
          <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
            다시 시도
          </Button>
        </div>
      ) : null}
      <section
        ref={container}
        className={error ? "hidden" : "h-80 w-full"}
        aria-label="다음 주소 검색"
      />
    </div>
  );
}
