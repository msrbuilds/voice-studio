import { useCallback, useEffect, useState } from "react";
import { getAsrStatus } from "@/lib/api";
import type { AsrStatus } from "@/types/models";

/**
 * Whisper's status. The language list comes back even before the weights load
 * (the backend reads transformers' static table), so the picker is populated
 * on first paint.
 */
export function useAsrStatus() {
  const [status, setStatus] = useState<AsrStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getAsrStatus());
    } catch {
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { status, loading, refresh };
}
