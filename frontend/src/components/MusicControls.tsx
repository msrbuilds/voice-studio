import { useState } from "react";
import { AudioWaveform, Binary, ChevronDown, ChevronUp, Cpu } from "lucide-react";
import type { ConfigResponse, MusicBuffer } from "@/types/models";
import { ThemeToggle } from "./ThemeToggle";
import { KEY_OPTIONS, TIMESIG_OPTIONS } from "@/lib/musicOptions";
import { focusRing } from "@/lib/theme";

interface Props {
  theme: "light" | "dark";
  onThemeToggle: () => void;
  config: ConfigResponse | null;
  buffer: MusicBuffer;
  onChange: (partial: Partial<MusicBuffer>) => void;
}

// Left-panel generation controls for Music mode. Mirrors VoiceLibrary's aside
// chrome (surface / width / header / backend footer) but drops the collapse
// toggle + version/update button (VoiceLibrary-specific). The sliders write the
// shared `pm.music` buffer, which MusicEditor reads at generate time.
export function MusicControls({ theme, onThemeToggle, config, buffer, onChange }: Props) {
  const isDark = theme === "dark";
  const [advOpen, setAdvOpen] = useState<boolean>(() => {
    try { return localStorage.getItem("vs.music.advanced") === "true"; } catch { return false; }
  });
  const toggleAdv = () =>
    setAdvOpen((v) => {
      const n = !v;
      try { localStorage.setItem("vs.music.advanced", String(n)); } catch { /* ignore */ }
      return n;
    });
  const surface = isDark ? "bg-zinc-950" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const heading = isDark ? "text-zinc-400" : "text-gray-600";
  const bodyText = isDark ? "text-zinc-300" : "text-gray-700";
  const subtle = isDark ? "text-zinc-400" : "text-gray-600";
  const label = isDark ? "text-zinc-300" : "text-gray-700";
  const inputBg = isDark ? "bg-zinc-900 border-zinc-800 text-white" : "bg-white border-gray-200 text-gray-900";

  return (
    <aside className={`w-64 shrink-0 z-10 border-r flex flex-col transition-colors ${surface} ${border}`}>
      <div className={`p-3 xxl:p-4 border-b flex items-center gap-3 ${border}`}>
        <img
          src={isDark ? "/logo-dark-sm.png" : "/logo-light-sm.png"}
          alt="Voice Studio logo"
          width={36}
          height={36}
          className="w-9 h-9 rounded-lg shrink-0"
        />
        <h1 className={`font-semibold text-sm truncate ${isDark ? "text-white" : "text-gray-900"}`}>
          Voice Studio by MSR
        </h1>
      </div>

      <div className="flex-1 overflow-y-auto p-2.5 space-y-4">
        <section className="p-3 dark:bg-zinc-900 dark:border-zinc-800 bg-gray-100/80 border border-gray-200 rounded-lg space-y-4">
          <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>Generation</h2>
          <div>
            <label className={`block text-sm font-medium mb-1 ${label}`}>Duration: {buffer.durationSec}s</label>
            <input type="range" min={5} max={30} step={1} value={buffer.durationSec}
              onChange={(e) => onChange({ durationSec: Number(e.target.value) })}
              className="w-full accent-orange-600" />
          </div>
          <div>
            <label className={`block text-sm font-medium mb-1 ${label}`}>Guidance scale: {buffer.guidanceScale.toFixed(1)}</label>
            <input type="range" min={1} max={10} step={0.5} value={buffer.guidanceScale}
              onChange={(e) => onChange({ guidanceScale: Number(e.target.value) })}
              className="w-full accent-orange-600" />
          </div>
          <div>
            <label className={`block text-sm font-medium mb-1 ${label}`}>Seed</label>
            <input type="number" value={buffer.seed}
              onChange={(e) => onChange({ seed: Number(e.target.value) })}
              className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`} />
            <p className={`text-xs mt-1 ${subtle}`}>-1 = random</p>
          </div>

          <button type="button" onClick={toggleAdv}
            className={`flex items-center gap-1 text-xs font-semibold uppercase tracking-wide ${heading} ${focusRing}`}>
            {advOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />} Advanced
          </button>
          {advOpen && (
            <div className="space-y-4">
              <div>
                <label className={`block text-sm font-medium mb-1 ${label}`}>Variations: {buffer.count}</label>
                <input type="range" min={1} max={4} step={1} value={buffer.count}
                  onChange={(e) => onChange({ count: Number(e.target.value) })}
                  className="w-full accent-orange-600" />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${label}`}>BPM</label>
                <input type="number" min={30} max={300} value={buffer.bpm ?? ""} placeholder="Auto"
                  onChange={(e) => onChange({ bpm: e.target.value === "" ? null : Number(e.target.value) })}
                  className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`} />
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${label}`}>Key</label>
                <select value={buffer.key} onChange={(e) => onChange({ key: e.target.value })}
                  className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`}>
                  {KEY_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
              <div>
                <label className={`block text-sm font-medium mb-1 ${label}`}>Time signature</label>
                <select value={buffer.timeSig} onChange={(e) => onChange({ timeSig: e.target.value })}
                  className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`}>
                  {TIMESIG_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${label}`}>Fade in</label>
                  <input type="number" min={0} max={30} step={0.5} value={buffer.fadeIn}
                    onChange={(e) => onChange({ fadeIn: Number(e.target.value) })}
                    className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`} />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${label}`}>Fade out</label>
                  <input type="number" min={0} max={30} step={0.5} value={buffer.fadeOut}
                    onChange={(e) => onChange({ fadeOut: Number(e.target.value) })}
                    className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`} />
                </div>
              </div>
            </div>
          )}
        </section>

        <section>
          <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>Appearance</h2>
          <ThemeToggle theme={theme} onToggle={onThemeToggle} />
        </section>

        {config && (
          <section>
            <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>Backend</h2>
            <div className={`text-xs ${subtle} flex items-center gap-4`}>
              <span className="flex items-center gap-1.5" title="Compute device">
                <Cpu className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>{config.device}</span>
              </span>
              <span className="flex items-center gap-1.5" title="Compute precision (dtype)">
                <Binary className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>{config.dtype}</span>
              </span>
              <span className="flex items-center gap-1.5" title="Output sample rate">
                <AudioWaveform className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>
                  {config.sampling_rate > 0
                    ? `${(config.sampling_rate / 1000).toFixed(config.sampling_rate % 1000 === 0 ? 0 : 1)} kHz`
                    : "—"}
                </span>
              </span>
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}
