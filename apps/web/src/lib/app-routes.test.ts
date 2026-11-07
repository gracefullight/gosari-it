import { describe, expect, it } from "vitest";
import { FEATURE_PATHS, resolveAppRoute } from "@/lib/app-routes";

describe("resolveAppRoute", () => {
  it("resolves the home and every menu URL including trailing slashes", () => {
    expect(resolveAppRoute("/")).toEqual({ feature: null, notebookMode: "list", found: true });
    for (const [feature, path] of Object.entries(FEATURE_PATHS)) {
      expect(resolveAppRoute(path)).toEqual({ feature, notebookMode: "list", found: true });
      expect(resolveAppRoute(`${path}/`).feature).toBe(feature);
    }
  });
  it("separates notebook listing, writing and editing URLs", () => {
    expect(resolveAppRoute("/notebook").notebookMode).toBe("list");
    expect(resolveAppRoute("/notebook/new")).toEqual({
      feature: "내 수첩",
      notebookMode: "write",
      found: true,
    });
    expect(resolveAppRoute("/notebook/record%20one/edit")).toEqual({
      feature: "내 수첩",
      notebookMode: "write",
      recordId: "record one",
      found: true,
    });
  });
  it("rejects unknown routes and extra path segments", () => {
    for (const path of ["/missing", "/prices/unknown", "/notebook/new/unknown"]) {
      expect(resolveAppRoute(path).found).toBe(false);
    }
  });
});
