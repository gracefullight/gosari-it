type AnalyticsPath =
  | "/"
  | "/outing"
  | "/regions"
  | "/notebook"
  | "/notebook/new"
  | "/notebook/edit"
  | "/share"
  | "/prices"
  | "/not-found";
const PAGES: Record<AnalyticsPath, { name: string; title: string }> = {
  "/": { name: "chat", title: "대화" },
  "/outing": { name: "outing", title: "나들이" },
  "/regions": { name: "regions", title: "관심 지역" },
  "/notebook": { name: "notebook", title: "내 수첩" },
  "/notebook/new": { name: "notebook_create", title: "수첩 작성" },
  "/notebook/edit": { name: "notebook_edit", title: "수첩 수정" },
  "/share": { name: "share", title: "나눔" },
  "/prices": { name: "prices", title: "가격 조사" },
  "/not-found": { name: "not_found", title: "페이지 없음" },
};
const NOTEBOOK_EDIT = /^\/notebook\/[^/]+\/edit\/?$/;
const URL_SUFFIX = /[?#]/;
const TRAILING_SLASHES = /\/+$/;
const SCRIPT_ID = "gosari-google-analytics";
const CHAT_ACTIONS = ["send", "complete", "stop"] as const;
const PRIVACY_CONFIG = {
  allow_google_signals: false,
  allow_ad_personalization_signals: false,
  send_page_view: false,
  ignore_referrer: true,
  campaign_id: "",
  campaign_name: "",
  campaign_source: "",
  campaign_medium: "",
  campaign_term: "",
  campaign_content: "",
};
export const GOSARI_GA_MEASUREMENT_ID = "G-8K2GSW71C6";
export type ChatAnalyticsAction = (typeof CHAT_ACTIONS)[number];
interface AnalyticsState {
  measurementId: string;
  lastPath: AnalyticsPath | null;
  currentLocation: string;
  currentTitle: string;
  referrer: string;
  pageName: string;
}
type AnalyticsWindow = Window & {
  dataLayer?: unknown[];
  gtag?: (...args: unknown[]) => void;
  __gosariAnalytics?: AnalyticsState;
};

export function sanitizeAnalyticsPath(path: string): AnalyticsPath {
  const pathname = path.split(URL_SUFFIX, 1)[0] || "/";
  if (NOTEBOOK_EDIT.test(pathname)) return "/notebook/edit";
  const normalized = pathname.replace(TRAILING_SLASHES, "") || "/";
  return Object.hasOwn(PAGES, normalized) ? (normalized as AnalyticsPath) : "/not-found";
}

function safePage(path: string) {
  const safePath = sanitizeAnalyticsPath(path);
  const page = PAGES[safePath];
  return { path: safePath, name: page.name, title: `고사리잇 · ${page.title}` };
}
/** Configure the fixed stream with Enhanced measurement OFF. */
export function initializeGoogleAnalytics(path = "/"): boolean {
  const id = GOSARI_GA_MEASUREMENT_ID;
  if (typeof window === "undefined" || typeof document === "undefined") return false;
  const browser = window as AnalyticsWindow;
  if (browser.__gosariAnalytics?.measurementId === id) return true;
  const page = safePage(path);
  const location = `${window.location.origin}${page.path}`;
  browser.dataLayer ??= [];
  browser.gtag ??= (...args: unknown[]) => {
    browser.dataLayer?.push(args);
  };
  const privacy = {
    ...PRIVACY_CONFIG,
    page_location: location,
    page_referrer: "",
    page_title: page.title,
  };
  browser.gtag("set", privacy);
  browser.gtag("js", new Date());
  browser.gtag("config", id, privacy);
  browser.__gosariAnalytics = {
    measurementId: id,
    lastPath: null,
    currentLocation: location,
    currentTitle: page.title,
    referrer: "",
    pageName: page.name,
  };
  if (!document.getElementById(SCRIPT_ID)) {
    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.async = true;
    script.referrerPolicy = "origin";
    script.src = `https://www.googletagmanager.com/gtag/js?id=${id}`;
    document.head.append(script);
  }
  return true;
}

export function trackPageView(path: string): boolean {
  if (!initializeGoogleAnalytics(path)) return false;
  const browser = window as AnalyticsWindow;
  const state = browser.__gosariAnalytics;
  const page = safePage(path);
  if (!state || !browser.gtag || state.lastPath === page.path) return false;
  const location = `${window.location.origin}${page.path}`;
  const referrer = state.lastPath ? state.currentLocation : "";
  const safeContext = { page_location: location, page_referrer: referrer, page_title: page.title };
  // Global defaults also cover GA's automatically collected engagement context.
  browser.gtag("set", safeContext);
  // Config has higher precedence than global set, so keep both scopes current.
  if (state.lastPath)
    browser.gtag("config", state.measurementId, { ...PRIVACY_CONFIG, ...safeContext });
  browser.gtag("event", "page_view", {
    ...safeContext,
    send_to: state.measurementId,
    app_page: page.name,
  });
  Object.assign(state, {
    lastPath: page.path,
    currentLocation: location,
    currentTitle: page.title,
    referrer,
    pageName: page.name,
  });
  return true;
}

/** Enum-only API: never accepts message text, record IDs, URLs or query conditions. */
export function trackChatUsage(
  action: ChatAnalyticsAction,
  inputMethod?: "text" | "voice"
): boolean {
  if (
    !CHAT_ACTIONS.includes(action) ||
    (inputMethod !== undefined && inputMethod !== "text" && inputMethod !== "voice")
  )
    return false;
  if (!initializeGoogleAnalytics("/")) return false;
  const browser = window as AnalyticsWindow;
  const state = browser.__gosariAnalytics;
  if (!state || !browser.gtag) return false;
  browser.gtag("event", `chat_${action}`, {
    send_to: state.measurementId,
    page_location: state.currentLocation,
    page_referrer: state.referrer,
    page_title: state.currentTitle,
    app_page: state.pageName,
    ...(inputMethod ? { input_method: inputMethod } : {}),
  });
  return true;
}
