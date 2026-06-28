import { useEffect, useState } from "react";
import { PanelRightClose, PanelRightOpen } from "lucide-react";
import type { ConfigResponse, EngineInfo } from "@/types/models";
import { EngineSelector } from "./EngineSelector";
import { CfgScaleBody } from "./CfgScaleControl";
import { ThemeToggle } from "./ThemeToggle";
import { getCfgHints } from "@/lib/engineHints";

const LS_KEY = "vs.controlPanel.open";

interface Props {
  isDark: boolean;
  theme: "light" | "dark";
  onThemeToggle: () => void;
  config: ConfigResponse | null;
  engines: EngineInfo[];
  activeEngine: string | null;
  onSelectEngine: (name: string) => Promise<void>;
  onLoadEngine: (name: string) => Promise<void>;
  onInstallEngine: (name: string) => void;
  onDownloadEngine: (name: string) => void;
  cfgScale: number;
  onCfgScaleChange: (v: number) => void;
  exaggeration: number;
  onExaggerationChange: (v: number) => void;
}

export function ControlPanel({
  isDark,
  theme,
  onThemeToggle,
  config,
  engines,
  activeEngine,
  onSelectEngine,
  onLoadEngine,
  onInstallEngine,
  onDownloadEngine,
  cfgScale,
  onCfgScaleChange,
  exaggeration,
  onExaggerationChange,
}: Props) {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem(LS_KEY);
    if (stored !== null) return stored === "false";
    return typeof window !== "undefined" ? window.innerWidth < 1200 : false;
  });

  useEffect(() => {
    localStorage.setItem(LS_KEY, collapsed ? "false" : "true");
  }, [collapsed]);

  const surface = isDark ? "bg-zinc-950" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const heading = isDark ? "text-zinc-500" : "text-gray-500";
  const subtle = isDark ? "text-zinc-500" : "text-gray-500";
  const bodyText = isDark ? "text-zinc-300" : "text-gray-700";
  const iconBtn = isDark
    ? "text-zinc-400 hover:text-teal-400"
    : "text-gray-400 hover:text-teal-600";

  const cfgHints = getCfgHints(activeEngine);
  const isChatterbox = activeEngine === "chatterbox";

  if (collapsed) {
    return (
      <aside
        className={`w-12 shrink-0 h-screen border-l flex flex-col items-center pt-4 transition-colors ${surface} ${border}`}
      >
        <button
          type="button"
          onClick={() => setCollapsed(false)}
          className={`p-2 rounded-lg transition-colors ${iconBtn}`}
          title="Open control panel"
        >
          <PanelRightOpen className="w-5 h-5" />
        </button>
      </aside>
    );
  }

  return (
    <aside
      className={`w-80 shrink-0 h-screen border-l flex flex-col transition-colors ${surface} ${border}`}
    >
      {/* Header */}
      <div className={`p-4 border-b flex items-center justify-between ${border}`}>
        <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
          Controls
        </h2>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className={`p-1 rounded transition-colors ${iconBtn}`}
          title="Collapse control panel"
        >
          <PanelRightClose className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {/* Engine section */}
        <section>
          <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Engine
          </h3>
          <EngineSelector
            isDark={isDark}
            engines={engines}
            activeName={activeEngine}
            onSelect={onSelectEngine}
            onLoad={onLoadEngine}
            onInstall={onInstallEngine}
            onDownload={onDownloadEngine}
          />
        </section>

        {/* Settings section */}
        <section>
          <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            {isChatterbox ? "CFG weight (voice fidelity)" : "Voice fidelity (CFG)"}
          </h3>
          <CfgScaleBody
            isDark={isDark}
            value={cfgScale}
            onChange={onCfgScaleChange}
            hints={cfgHints}
          />

          {isChatterbox && (
            <>
              <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 mt-4 ${heading}`}>
                Voice expressiveness (Chatterbox)
              </h3>
              <ExaggerationBody
                isDark={isDark}
                value={exaggeration}
                onChange={onExaggerationChange}
              />
            </>
          )}
        </section>

        {/* Appearance section */}
        <section>
          <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Appearance
          </h3>
          <ThemeToggle theme={theme} onToggle={onThemeToggle} />
        </section>

        {/* Backend section */}
        {config && (
          <section>
            <h3 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
              Backend
            </h3>
            <div className={`text-xs space-y-0.5 ${subtle} flex items-center gap-4`}>
              <div>device: <span className={bodyText}>{config.device}</span></div>
              <div>dtype: <span className={bodyText}>{config.dtype}</span></div>
              <div>sr: <span className={bodyText}>{config.sampling_rate} Hz</span></div>
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}

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
