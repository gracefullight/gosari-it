import { useAtomValue } from "jotai";
import { useEffect } from "react";
import { trackPageView } from "@/lib/google-analytics";
import { appPathAtom } from "@/stores/chat.atoms";

export function AppAnalytics() {
  const path = useAtomValue(appPathAtom);
  useEffect(() => {
    trackPageView(path);
  }, [path]);
  return null;
}
