// useEngine — fetches the engine list and the active engine, exposes
// setActive() for switching. Returns a list of `EngineInfo` and a setter
// that calls POST /api/engines/activate.
//
// The list of engines is also exposed via /api/config (so callers that
// already use useConfig get it for free). This hook is a thin wrapper
// over the API for components that only care about engines.

import { useCallback, useEffect, useState } from "react";
import { activateEngine, listEngines, loadEngine } from "@/lib/api";
import type { EngineInfo } from "@/types/models";

export interface UseEngineResult {
  engines: EngineInfo[];
  activeName: string | null;
  loading: boolean;
  error: string | null;
  setActive: (name: string) => Promise<void>;
  ensureLoaded: (name: string) => Promise<void>;
  refresh: () => Promise<void>;
}

export function useEngine(): UseEngineResult {
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [activeName, setActiveName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEngines();
      setEngines(data.engines);
      setActiveName(data.active);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setActive = useCallback(
    async (name: string) => {
      const info = await activateEngine(name);
      setActiveName(info.name);
      // Refresh so we pick up the new `active` flags on every engine.
      await refresh();
    },
    [refresh],
  );

  const ensureLoaded = useCallback(
    async (name: string) => {
      await loadEngine(name);
      await refresh();
    },
    [refresh],
  );

  return { engines, activeName, loading, error, setActive, ensureLoaded, refresh };
}
