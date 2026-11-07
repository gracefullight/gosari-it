import { act, cleanup, render } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppAnalytics } from "@/components/app-analytics";
import {
  type ChatAnalyticsAction,
  initializeGoogleAnalytics,
  sanitizeAnalyticsPath,
  trackChatUsage,
  trackPageView,
} from "@/lib/google-analytics";
import { appPathAtom } from "@/stores/chat.atoms";

const FIXED_ID = "G-8K2GSW71C6";
const inserted: HTMLScriptElement[] = [];
type TestWindow = Window & { dataLayer?: unknown[][]; gtag?: unknown; __gosariAnalytics?: unknown };
function browser() {
  return window as TestWindow;
}
function events() {
  return (browser().dataLayer ?? []).filter((entry) => entry[0] === "event");
}
beforeEach(() => {
  inserted.length = 0;
  Reflect.deleteProperty(window, "dataLayer");
  Reflect.deleteProperty(window, "gtag");
  Reflect.deleteProperty(window, "__gosariAnalytics");
  window.history.replaceState(null, "", "/");
  document.title = "PRIVATE_TITLE_CANARY";
  // Keep all test tags detached: no external script or collection request is made.
  vi.spyOn(document.head, "append").mockImplementation((...nodes) => {
    for (const node of nodes) if (node instanceof HTMLScriptElement) inserted.push(node);
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  Reflect.deleteProperty(window, "dataLayer");
  Reflect.deleteProperty(window, "gtag");
  Reflect.deleteProperty(window, "__gosariAnalytics");
});

describe("GA4 public usage boundary", () => {
  it.each(["", "G-OTHER123456", "G-<script>PRIVATE</script>"])(
    "keeps the fixed stream instead of a runtime override: %s",
    (id) => {
      vi.stubEnv("VITE_GA_MEASUREMENT_ID", id);
      expect(initializeGoogleAnalytics()).toBe(true);
      expect(trackPageView("/share?contact=PRIVATE_QUERY_CANARY")).toBe(true);
      expect(trackChatUsage("send")).toBe(true);
      expect(inserted).toHaveLength(1);
      expect(inserted[0].src).toBe(`https://www.googletagmanager.com/gtag/js?id=${FIXED_ID}`);
      expect(browser().dataLayer?.find((entry) => entry[0] === "config")?.[1]).toBe(FIXED_ID);
    }
  );

  it.each([
    ["/", "/"],
    ["/prices?settlement_date=2026-05-12#PRIVATE", "/prices"],
    ["/notebook/PRIVATE_RECORD_CANARY/edit?location=33.3,126.4", "/notebook/edit"],
    ["/notebook/new?evidence=PRIVATE_EVIDENCE_CANARY", "/notebook/new"],
    ["/share?contact=PRIVATE_CONTACT_CANARY", "/share"],
    ["/regions/", "/regions"],
    ["/private/PRIVATE_RECORD_CANARY", "/not-found"],
  ])("maps %s to the fixed public route %s", (path, expected) => {
    expect(sanitizeAnalyticsPath(path)).toBe(expected);
  });

  it("inserts one async origin-referrer tag and disables automatic initial pageviews and ad signals", () => {
    expect(
      initializeGoogleAnalytics("/notebook/PRIVATE_RECORD_CANARY/edit?q=PRIVATE_QUERY_CANARY")
    ).toBe(true);
    expect(initializeGoogleAnalytics("/prices")).toBe(true);
    expect(inserted).toHaveLength(1);
    expect(inserted[0].src).toBe(`https://www.googletagmanager.com/gtag/js?id=${FIXED_ID}`);
    expect(inserted[0].async).toBe(true);
    expect(inserted[0].referrerPolicy).toBe("origin");
    const config = browser().dataLayer?.find((entry) => entry[0] === "config");
    expect(config?.[1]).toBe(FIXED_ID);
    expect(config?.[2]).toMatchObject({
      send_page_view: false,
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      page_location: `${window.location.origin}/notebook/edit`,
      page_title: "고사리잇 · 수첩 수정",
      page_referrer: "",
    });
    expect(events()).toHaveLength(0);
    expect(JSON.stringify(browser().dataLayer)).not.toContain("PRIVATE_");
  });

  it("tracks only coarse SPA navigation once under StrictMode and ignores private query changes", () => {
    const store = createStore();
    window.history.replaceState(
      null,
      "",
      "/notebook/PRIVATE_RECORD_CANARY/edit?q=PRIVATE_QUERY_CANARY"
    );
    store.set(appPathAtom, window.location.pathname + window.location.search);
    render(
      <StrictMode>
        <Provider store={store}>
          <AppAnalytics />
        </Provider>
      </StrictMode>
    );
    expect(events()).toHaveLength(1);
    act(() =>
      store.set(appPathAtom, "/notebook/ANOTHER_PRIVATE_CANARY/edit?q=DIFFERENT_PRIVATE_CANARY")
    );
    expect(events()).toHaveLength(1);
    act(() => store.set(appPathAtom, "/share?contact=PRIVATE_CONTACT_CANARY#PRIVATE_HASH_CANARY"));
    expect(events()).toHaveLength(2);
    expect(events()[1][2]).toMatchObject({
      page_location: `${window.location.origin}/share`,
      page_referrer: `${window.location.origin}/notebook/edit`,
      page_title: "고사리잇 · 나눔",
    });
    const configs = (browser().dataLayer ?? []).filter((entry) => entry[0] === "config");
    expect(configs.at(-1)?.[2]).toMatchObject({
      page_location: `${window.location.origin}/share`,
      page_referrer: `${window.location.origin}/notebook/edit`,
      send_page_view: false,
      allow_google_signals: false,
    });
    act(() => store.set(appPathAtom, "/notebook/PRIVATE_RECORD_CANARY/edit"));
    expect(events()).toHaveLength(3);
    expect(inserted).toHaveLength(1);
    expect(JSON.stringify(browser().dataLayer)).not.toContain("PRIVATE_");
  });

  it("accepts only chat action/input enums and never accepts arbitrary metadata", () => {
    trackPageView("/share?contact=PRIVATE_CONTACT_CANARY");
    expect(trackChatUsage("send", "voice")).toBe(true);
    expect(trackChatUsage("complete")).toBe(true);
    expect(trackChatUsage("stop")).toBe(true);
    expect(trackChatUsage("PRIVATE_MESSAGE_CANARY" as ChatAnalyticsAction)).toBe(false);
    expect(trackChatUsage("send", "PRIVATE_COORDINATES_CANARY" as "text")).toBe(false);
    const chat = events().filter((entry) => String(entry[1]).startsWith("chat_"));
    expect(chat.map((entry) => entry[1])).toEqual(["chat_send", "chat_complete", "chat_stop"]);
    expect(chat[0][2]).toMatchObject({
      input_method: "voice",
      app_page: "share",
      page_location: `${window.location.origin}/share`,
    });
    expect(JSON.stringify(browser().dataLayer)).not.toContain("PRIVATE_");
  });
});
