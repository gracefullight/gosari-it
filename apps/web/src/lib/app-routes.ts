export type Feature = "나들이" | "지역 탐색" | "내 수첩" | "나눔" | "가격 조사";

export const FEATURE_PATHS: Record<Feature, string> = {
  나들이: "/outing",
  "지역 탐색": "/regions",
  "내 수첩": "/notebook",
  나눔: "/share",
  "가격 조사": "/prices",
};

const TRAILING_SLASH = /\/$/;
const NOTEBOOK_EDIT_PATH = /^\/notebook\/([^/]+)\/edit$/;

export function resolveAppRoute(path: string): {
  feature: Feature | null;
  notebookMode: "list" | "write";
  recordId?: string;
  found: boolean;
} {
  const pathname = path.split("?")[0].replace(TRAILING_SLASH, "") || "/";
  if (pathname === "/") return { feature: null, notebookMode: "list", found: true };
  const edit = pathname.match(NOTEBOOK_EDIT_PATH);
  if (edit)
    return {
      feature: "내 수첩",
      notebookMode: "write",
      recordId: decodeURIComponent(edit[1]),
      found: true,
    };
  if (pathname === "/notebook/new")
    return { feature: "내 수첩", notebookMode: "write", found: true };
  const feature = (Object.keys(FEATURE_PATHS) as Feature[]).find(
    (key) => FEATURE_PATHS[key] === pathname
  );
  return { feature: feature ?? null, notebookMode: "list", found: Boolean(feature) };
}
