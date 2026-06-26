import { useEffect, useRef, useState } from "react";
import { Settings, X } from "lucide-react";
import { CfgScaleBody } from "./CfgScaleControl";
import { CacheBody, useCacheData } from "./CachePanel";
import { useIsNarrow } from "@/hooks/useIsNarrow";
import { getCfgHints } from "@/lib/engineHints";

interface Props {
  isDark: boolean;
  cfgScale: number;
  onCfgScaleChange: (v: number) => void;
  // Chatterbox Multilingual V3 only. When the active engine is
  // Chatterbox, an additional "Voice expressiveness" slider is shown
  // in the popover.
  activeEngine?: string | null;
  exaggeration?: number;
  onExaggerationChange?: (v: number) => void;
}

/**
 * Voice expressiveness / exaggeration slider body — only relevant for
 * the Chatterbox Multilingual V3 engine. Embedded inside SettingsMenu
 * so the same popover surfaces CFG + Exaggeration + Cache controls.
 */
function ExaggerationBody({
  isDark,
  value,
  onChange,
}: {
  isDark: boolean;
  value: number;
  onChange: (v: number) => void;
}) {
  const set = (n: number) => {
    // Clamp to a safe range so a runaway slider doesn't crash generation.
    onChange(Math.max(0.0, Math.min(2.0, n)));
  };
  const summary = value.toFixed(2);
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <span
          className={`text-xs font-medium ${
            isDark ? "text-zinc-400" : "text-gray-600"
          }`}
        >
          Value
        </span>
        <span className="text-sm font-mono text-teal-400">{summary}</span>
      </div>
      <input
        type="range"
        min={0.0}
        max={1.5}
        step={0.05}
        value={value}
        onChange={(e) => set(Number(e.target.value))}
        className="w-full accent-teal-500"
      />
      <div
        className={`flex justify-between text-[10px] ${
          isDark ? "text-zinc-600" : "text-gray-400"
        }`}
      >
        <span>neutral</span>
        <span>expressive</span>
        <span>very dramatic</span>
      </div>

      <div className="flex items-center gap-2 pt-1">
        {[0.0, 0.3, 0.5, 0.7, 1.0].map((preset) => (
          <button
            key={preset}
            type="button"
            onClick={() => set(preset)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors border ${
              Math.abs(value - preset) < 0.025
                ? "bg-teal-600 text-white border-teal-500"
                : isDark
                  ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border-zinc-700"
                  : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
            }`}
          >
            {preset.toFixed(1)}
          </button>
        ))}
      </div>

      <p className={`text-xs ${isDark ? "text-zinc-500" : "text-gray-500"}`}>
        Chatterbox-only. Higher values make the speaker sound more
        dramatic; lower values are calmer. Pairs with the
        <span className="text-teal-400"> CFG weight</span> slider above.
      </p>
    </div>
  );
}

/**
 * Single popover housing per-engine tuning knobs (CFG weight + voice
 * expressiveness) and Synthesis cache controls. Replaces the three
 * separate buttons that used to live in the action bar.
 */
export function SettingsMenu({
  isDark,
  cfgScale,
  onCfgScaleChange,
  activeEngine,
  exaggeration = 0.5,
  onExaggerationChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const narrow = useIsNarrow();
  const ref = useRef<HTMLDivElement>(null);

  // Single shared cache data source. Even when the popover is closed the
  // hook still polls every 15 s so the cache count stays accurate.
  const { data, busy, refresh, onClear, onDelete } = useCacheData();

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const isChatterbox = activeEngine === "chatterbox";

  // Per-engine slider hints: min/max/step/presets/labels. Resolved here
  // once so the same hints flow into the slider, the preset buttons,
  // and the header text. Falls back to VibeVoice defaults when the
  // engine id is unknown or missing.
  const cfgHints = getCfgHints(activeEngine);

  const cfgHeaderLabel = isChatterbox
    ? "CFG weight (voice fidelity)"
    : "Voice fidelity (CFG)";

  const triggerLabel = narrow ? (
    <Settings className="w-4 h-4" />
  ) : (
    <>
      <Settings className="w-4 h-4" />
      Settings
    </>
  );

  const subText = isChatterbox
    ? "CFG weight · Voice expressiveness · Cache"
    : "Voice fidelity · Synthesis cache";

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-2 px-4 py-2.5 rounded-lg font-medium transition-colors border ${
          isDark
            ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white border-zinc-700"
            : "bg-gray-100 hover:bg-gray-200 text-gray-700 hover:text-gray-900 border-gray-300"
        }`}
        title={`Settings${data ? ` · cache ${data.entry_count}/${data.max_entries}` : ""}`}
      >
        {triggerLabel}
        {data && (
          <span
            className={`text-xs ${isDark ? "text-zinc-500" : "text-gray-500"}`}
          >
            {data.entry_count}/{data.max_entries}
          </span>
        )}
      </button>

      {open && (
        <div
          className={`absolute right-0 top-full mt-2 w-96 rounded-lg shadow-xl border z-30 overflow-hidden ${
            isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200"
          }`}
        >
          <div
            className={`px-4 py-3 border-b flex items-center justify-between ${
              isDark ? "border-zinc-800" : "border-gray-200"
            }`}
          >
            <div>
              <div
                className={`text-sm font-semibold ${
                  isDark ? "text-white" : "text-gray-900"
                }`}
              >
                Settings
              </div>
              <div
                className={`text-xs mt-0.5 ${
                  isDark ? "text-zinc-500" : "text-gray-500"
                }`}
              >
                {subText}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className={`p-1 rounded ${
                isDark
                  ? "text-zinc-500 hover:text-zinc-300"
                  : "text-gray-400 hover:text-gray-600"
              }`}
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* CFG section */}
          <div
            className={`border-b ${
              isDark ? "border-zinc-800" : "border-gray-200"
            }`}
          >
            <div
              className={`px-4 pt-3 pb-1 text-xs uppercase tracking-wider font-semibold ${
                isDark ? "text-zinc-500" : "text-gray-500"
              }`}
            >
              {cfgHeaderLabel}
            </div>
            <CfgScaleBody
              isDark={isDark}
              value={cfgScale}
              onChange={onCfgScaleChange}
              hints={cfgHints}
            />
          </div>

          {/* Chatterbox-only: voice expressiveness / exaggeration */}
          {isChatterbox && onExaggerationChange && (
            <div
              className={`border-b ${
                isDark ? "border-zinc-800" : "border-gray-200"
              }`}
            >
              <div
                className={`px-4 pt-3 pb-1 text-xs uppercase tracking-wider font-semibold ${
                  isDark ? "text-zinc-500" : "text-gray-500"
                }`}
              >
                Voice expressiveness (Chatterbox)
              </div>
              <ExaggerationBody
                isDark={isDark}
                value={exaggeration}
                onChange={onExaggerationChange}
              />
            </div>
          )}

          {/* Cache section */}
          <CacheBody
            isDark={isDark}
            data={data}
            busy={busy}
            onClear={onClear}
            onDelete={onDelete}
          />

          {/* Refresh on demand */}
          <div
            className={`px-4 py-2 border-t ${
              isDark ? "border-zinc-800" : "border-gray-200"
            }`}
          >
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={busy}
              className={`w-full text-xs font-medium py-1 rounded ${
                isDark
                  ? "text-zinc-400 hover:text-zinc-200"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Refresh cache list
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
