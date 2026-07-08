import { useCallback, useEffect, useRef, useState } from "react";
import { getBaseStatus, startBaseDownload, type LmStatus } from "@/lib/api";

// Tracks the ACE-Step 2B base DiT download status; exposes a one-click download
// that polls until done. Used to gate the Extract / Lego / Complete tasks.
export function useBaseStatus() {
  const [status, setStatus] = useState<LmStatus | null>(null);
  const poll = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getBaseStatus());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => {
      if (poll.current) window.clearInterval(poll.current);
    };
  }, [refresh]);

  const download = useCallback(async () => {
    try {
      setStatus(await startBaseDownload());
      if (poll.current) window.clearInterval(poll.current);
      poll.current = window.setInterval(async () => {
        const s = await getBaseStatus();
        setStatus(s);
        if (s.downloaded || s.state === "done" || s.state === "error") {
          if (poll.current) window.clearInterval(poll.current);
        }
      }, 1500);
    } catch {
      /* ignore */
    }
  }, []);

  return { status, refresh, download };
}
