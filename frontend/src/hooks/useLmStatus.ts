import { useCallback, useEffect, useRef, useState } from "react";
import { getLmStatus, startLmDownload, type LmStatus } from "@/lib/api";

// Tracks the ACE-Step 5Hz LM download status; exposes a one-click download that
// polls until done. Used to gate the Inspiration + Thinking features.
export function useLmStatus() {
  const [status, setStatus] = useState<LmStatus | null>(null);
  const poll = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      setStatus(await getLmStatus());
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
      setStatus(await startLmDownload());
      if (poll.current) window.clearInterval(poll.current);
      poll.current = window.setInterval(async () => {
        const s = await getLmStatus();
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
