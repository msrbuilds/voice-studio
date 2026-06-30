import { useEffect, useRef, useState } from "react";
import { ExternalLink, Loader2, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { getUpdateRunStatus, startUpdate } from "@/lib/api";
import type { UpdateInfo, UpdateRunStatus } from "@/types/models";

interface Props {
  isDark: boolean;
  info: UpdateInfo;
  onClose: () => void;
}

export function UpdateDialog({ isDark, info, onClose }: Props) {
  const [status, setStatus] = useState<UpdateRunStatus>({
    state: "idle",
    log: [],
    returncode: null,
    error: null,
  });
  const logRef = useRef<HTMLPreElement>(null);
  const timerRef = useRef<number | null>(null);

  const poll = async () => {
    try {
      const s = await getUpdateRunStatus();
      setStatus(s);
      if (s.state === "running") {
        timerRef.current = window.setTimeout(() => void poll(), 1000);
      }
    } catch (err) {
      setStatus((prev) => ({
        ...prev,
        state: "error",
        log: [...prev.log, err instanceof Error ? err.message : String(err)],
      }));
    }
  };

  const begin = async () => {
    setStatus({ state: "running", log: [], returncode: null, error: null });
    try {
      await startUpdate();
    } catch (err) {
      setStatus({
        state: "error",
        log: [err instanceof Error ? err.message : String(err)],
        returncode: -1,
        error: "failed to start update",
      });
      return;
    }
    void poll();
  };

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status.log]);

  const running = status.state === "running";
  const done = status.state === "done";
  const failed = status.state === "error";
  const idle = status.state === "idle";

  const panel = isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200";
  const muted = isDark ? "text-zinc-400" : "text-gray-600";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className={`w-full max-w-2xl rounded-xl border shadow-xl ${panel}`}>
        <div
          className={`flex items-center justify-between px-5 py-3 border-b ${
            isDark ? "border-zinc-800" : "border-gray-200"
          }`}
        >
          <div className="flex items-center gap-2">
            {running && <Loader2 className="w-4 h-4 animate-spin text-orange-400" />}
            <span className={`font-semibold ${isDark ? "text-white" : "text-gray-900"}`}>
              {running
                ? "Updating Voice Studio…"
                : done
                  ? "Update complete"
                  : failed
                    ? "Update failed"
                    : `Update to v${info.latest ?? "?"}`}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={running}
            className={`p-1 rounded ${
              running
                ? "opacity-40 cursor-not-allowed"
                : isDark
                  ? "hover:bg-zinc-800 text-zinc-400"
                  : "hover:bg-gray-100 text-gray-600"
            } ${focusRing}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-3">
          {idle && (
            <>
              <p className={`text-sm ${muted}`}>
                A new release is available. "Update now" runs
                {" "}<span className="font-mono text-xs">git pull</span>, reinstalls
                dependencies, and rebuilds the UI. You'll restart Voice Studio when it
                finishes.
              </p>
              {info.body && (
                <pre
                  className={`max-h-40 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed whitespace-pre-wrap ${
                    isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
                  }`}
                >
                  {info.body}
                </pre>
              )}
            </>
          )}

          {!idle && (
            <>
              <p className={`text-sm ${muted}`}>
                {running
                  ? "Pulling the release, syncing dependencies, and rebuilding. This takes a few minutes."
                  : done
                    ? "Done. Restart Voice Studio (close this terminal/app and run it again) to load the new version."
                    : "The update failed. Review the log, then retry or update manually."}
              </p>
              <pre
                ref={logRef}
                className={`h-64 overflow-auto rounded-lg p-3 text-[11px] leading-relaxed font-mono whitespace-pre-wrap ${
                  isDark ? "bg-black/40 text-zinc-300" : "bg-gray-50 text-gray-700"
                }`}
              >
                {status.log.length ? status.log.join("\n") : "Starting…"}
              </pre>
            </>
          )}

          <div className="flex items-center justify-between gap-2">
            {info.html_url ? (
              <a
                href={info.html_url}
                target="_blank"
                rel="noopener noreferrer"
                className={`inline-flex items-center gap-1 text-xs underline decoration-dotted underline-offset-2 ${
                  isDark ? "text-zinc-400 hover:text-orange-400" : "text-gray-500 hover:text-orange-600"
                } ${focusRing}`}
              >
                Release notes on GitHub <ExternalLink className="w-3 h-3" />
              </a>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              {idle && (
                <button
                  type="button"
                  onClick={() => void begin()}
                  className={`px-4 py-2 rounded-lg text-sm font-medium bg-orange-600 hover:bg-orange-500 text-white ${focusRing}`}
                >
                  Update now
                </button>
              )}
              {failed && (
                <button
                  type="button"
                  onClick={() => void begin()}
                  className={`px-4 py-2 rounded-lg text-sm font-medium bg-orange-600 hover:bg-orange-500 text-white ${focusRing}`}
                >
                  Retry
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                disabled={running}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${
                  running
                    ? "opacity-40 cursor-not-allowed bg-zinc-700 text-zinc-300"
                    : isDark
                      ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
                      : "bg-gray-100 hover:bg-gray-200 text-gray-700"
                } ${focusRing}`}
              >
                {done ? "Done" : "Close"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
