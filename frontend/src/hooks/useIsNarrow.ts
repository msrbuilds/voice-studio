import { useEffect, useState } from "react";

/**
 * Returns true when the viewport is narrower than the `lg` breakpoint (1024px).
 * Used to switch icon-only pills in toolbars at narrow widths.
 */
export function useIsNarrow(): boolean {
  const [narrow, setNarrow] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.innerWidth < 1024;
  });

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const handler = (e: MediaQueryListEvent) => setNarrow(e.matches);
    mq.addEventListener("change", handler);
    // Sync once on mount in case SSR / hydration mismatch.
    setNarrow(mq.matches);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return narrow;
}
