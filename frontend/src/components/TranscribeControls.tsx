import { AudioWaveform, Binary, Cpu } from "lucide-react";
import type { AsrStatus, ConfigResponse, TranscribeBuffer } from "@/types/models";
import { ThemeToggle } from "./ThemeToggle";
import { focusRing } from "@/lib/theme";

interface Props {
  theme: "light" | "dark";
  onThemeToggle: () => void;
  config: ConfigResponse | null;
  asr: AsrStatus | null;
  buffer: TranscribeBuffer;
  onChange: (partial: Partial<TranscribeBuffer>) => void;
}

// Left-panel controls for Transcribe mode. Mirrors VoiceLibrary's aside chrome
// (surface / width / header / backend footer).
export function TranscribeControls({
  theme,
  onThemeToggle,
  config,
  asr,
  buffer,
  onChange,
}: Props) {
  const isDark = theme === "dark";
  const surface = isDark ? "bg-zinc-950" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const heading = isDark ? "text-zinc-400" : "text-gray-600";
  const bodyText = isDark ? "text-zinc-300" : "text-gray-700";
  const subtle = isDark ? "text-zinc-400" : "text-gray-600";
  const label = isDark ? "text-zinc-300" : "text-gray-700";
  const inputBg = isDark
    ? "bg-zinc-900 border-zinc-800 text-white"
    : "bg-white border-gray-200 text-gray-900";

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
          <h2 className={`text-xs font-semibold uppercase tracking-wide ${heading}`}>
            Transcription
          </h2>

          <div>
            <label htmlFor="asr-language" className={`block text-sm font-medium mb-1 ${label}`}>
              Language
            </label>
            <select
              id="asr-language"
              value={buffer.language ?? ""}
              onChange={(e) => onChange({ language: e.target.value || null })}
              className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`}
            >
              <option value="">Auto-detect</option>
              {(asr?.languages ?? []).map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
            <p className={`text-xs mt-1 ${subtle}`}>
              Auto-detect is reliable; override it for short or accented clips.
            </p>
          </div>

          <div>
            <label className={`flex items-center gap-2 text-sm font-medium ${label}`}>
              <input
                type="checkbox"
                checked={buffer.timestamps}
                onChange={(e) => onChange({ timestamps: e.target.checked })}
                className={`accent-orange-600 ${focusRing}`}
              />
              Timestamps
            </label>
            <p className={`text-xs mt-1 ${subtle}`}>Required to export .srt / .vtt subtitles.</p>
          </div>
        </section>

        <section>
          <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>Model</h2>
          <div className={`text-xs ${subtle} space-y-1`}>
            <div className={bodyText}>{asr?.model_id ?? "—"}</div>
            <div>
              {asr == null
                ? "status unavailable"
                : !asr.downloaded
                  ? "weights not downloaded"
                  : asr.loaded
                    ? "loaded"
                    : "ready (loads on first use)"}
            </div>
          </div>
        </section>

        <section>
          <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
            Appearance
          </h2>
          <ThemeToggle theme={theme} onToggle={onThemeToggle} />
        </section>

        {config && (
          <section>
            <h2 className={`text-xs font-semibold uppercase tracking-wide mb-2 ${heading}`}>
              Backend
            </h2>
            <div className={`text-xs ${subtle} flex items-center gap-4`}>
              <span className="flex items-center gap-1.5" title="Compute device">
                <Cpu className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>{config.device}</span>
              </span>
              <span className="flex items-center gap-1.5" title="Compute precision (dtype)">
                <Binary className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>{config.dtype}</span>
              </span>
              <span className="flex items-center gap-1.5" title="ASR input sample rate">
                <AudioWaveform className="w-3.5 h-3.5 shrink-0" />
                <span className={bodyText}>16 kHz</span>
              </span>
            </div>
          </section>
        )}
      </div>
    </aside>
  );
}
