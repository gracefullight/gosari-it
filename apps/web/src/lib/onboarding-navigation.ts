/** NextStep's optional Next.js export is bridged to this app's History routing in Vite. */
export function useRouter() {
  const navigate = (path: string, replace = false) => {
    window.history[replace ? "replaceState" : "pushState"](null, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  };
  return {
    push: (path: string) => navigate(path),
    replace: (path: string) => navigate(path, true),
    prefetch: () => {},
    back: () => window.history.back(),
    forward: () => window.history.forward(),
    refresh: () => window.location.reload(),
  };
}
export const usePathname = () => window.location.pathname;
export const useSearchParams = () => new URLSearchParams(window.location.search);
export const useParams = () => ({});
