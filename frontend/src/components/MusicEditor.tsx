import { useRef, useState } from "react";
import { Loader2, Music, Download, Sparkles, Upload, X } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { generateMusic, inspireMusic, musicClipAudioUrl, musicDownloadUrl, musicSourceUrl, uploadMusicSource, type MusicClip } from "@/lib/api";
import { keyToParam, timeSigToNumerator, normalizeKey, numeratorToTimeSig } from "@/lib/musicOptions";
import { TRACK_OPTIONS } from "@/lib/musicTracks";
import { useLmStatus } from "@/hooks/useLmStatus";
import { useBaseStatus } from "@/hooks/useBaseStatus";
import type { MusicBuffer } from "@/types/models";

const BASE_MODES = ["extract", "lego", "complete"] as const;

interface Props {
  isDark: boolean;
  buffer: MusicBuffer;
  onChange: (partial: Partial<MusicBuffer>) => void;
  engineReady: boolean;
}

export function MusicEditor({ isDark, buffer, onChange, engineReady }: Props) {
  const inputBg = isDark ? "bg-zinc-900 border-zinc-800 text-white" : "bg-white border-gray-200 text-gray-900";
  const sub = isDark ? "text-zinc-400" : "text-gray-600";
  const label = isDark ? "text-zinc-300" : "text-gray-700";

  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [clips, setClips] = useState<MusicClip[]>([]);
  const timer = useRef<number | null>(null);

  const { status: lm, download: downloadLm } = useLmStatus();
  const lmReady = !!lm?.downloaded;
  const { status: base, download: downloadBase } = useBaseStatus();
  const baseReady = !!base?.downloaded;
  const [query, setQuery] = useState("");
  const [inspiring, setInspiring] = useState(false);
  const [uploading, setUploading] = useState(false);

  const onPickSource = async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const up = await uploadMusicSource(file);
      onChange({ srcAudioId: up.id, srcName: up.name, srcDurationSec: up.duration_sec });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onInspire = async () => {
    if (inspiring || !query.trim()) return;
    setInspiring(true);
    setError(null);
    try {
      const bp = await inspireMusic(query.trim(), buffer.instrumental);
      onChange({
        caption: bp.caption, lyrics: bp.lyrics, instrumental: bp.instrumental,
        bpm: bp.bpm, key: normalizeKey(bp.key),
        timeSig: numeratorToTimeSig(bp.time_signature), durationSec: bp.duration_sec,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Inspiration failed");
    } finally {
      setInspiring(false);
    }
  };

  const needsSource = buffer.subMode !== "create";
  const sourceReady = !needsSource || !!buffer.srcAudioId;
  const isBaseMode = (BASE_MODES as readonly string[]).includes(buffer.subMode);
  const baseGateOk = !isBaseMode || baseReady;

  const onGenerate = async () => {
    if (busy || !buffer.caption.trim() || !sourceReady || !baseGateOk) return;
    setBusy(true);
    setError(null);
    setElapsed(0);
    const started = Date.now();
    timer.current = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 200);
    try {
      const result = await generateMusic({
        caption: buffer.caption.trim(),
        lyrics: buffer.instrumental ? "" : buffer.lyrics,
        instrumental: buffer.instrumental,
        duration_sec: buffer.durationSec,
        steps: buffer.steps,
        seed: buffer.seed,
        bpm: buffer.bpm,
        key: keyToParam(buffer.key),
        time_signature: timeSigToNumerator(buffer.timeSig),
        fade_in: buffer.fadeIn,
        fade_out: buffer.fadeOut,
        count: buffer.count,
        // LM (thinking) only applies to Create; only send it when the AI model
        // is downloaded (otherwise the worker can't load it). Cover/Repaint and
        // the base tasks never use it.
        thinking: buffer.subMode === "create" && buffer.thinking && lmReady,
        task_type: buffer.subMode === "create" ? "text2music" : buffer.subMode,
        src_audio_id: buffer.srcAudioId ?? "",
        cover_strength: buffer.coverStrength,
        repaint_start: buffer.repaintStart,
        repaint_end: buffer.repaintEnd,
        track_name: buffer.trackName,
        track_classes: buffer.trackClasses,
      });
      setClips(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      if (timer.current) window.clearInterval(timer.current);
      setBusy(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      <div className="max-w-3xl mx-auto space-y-4">
        <div className="space-y-2">
          <div className={`inline-flex gap-1 p-1 rounded-lg ${isDark ? "bg-zinc-800/40" : "bg-gray-100"}`}>
            {(["create", "cover", "repaint"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => onChange({ subMode: m })}
                className={`px-3 py-1.5 text-xs font-medium rounded-md capitalize ${
                  buffer.subMode === m
                    ? "bg-orange-600 text-white"
                    : isDark
                      ? "text-zinc-400 hover:text-zinc-200"
                      : "text-gray-600 hover:text-gray-800"
                } ${focusRing}`}
              >
                {m}
              </button>
            ))}
          </div>
          <div>
            <div className={`text-[11px] uppercase tracking-wide mb-1 ${sub}`}>Advanced — 2B base model</div>
            <div className={`inline-flex gap-1 p-1 rounded-lg ${isDark ? "bg-zinc-800/40" : "bg-gray-100"}`}>
              {BASE_MODES.map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => onChange({ subMode: m })}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md capitalize ${
                    buffer.subMode === m
                      ? "bg-orange-600 text-white"
                      : isDark
                        ? "text-zinc-400 hover:text-zinc-200"
                        : "text-gray-600 hover:text-gray-800"
                  } ${focusRing}`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        </div>

        {isBaseMode && !baseReady && (
          <div className={`rounded-lg border p-3 ${isDark ? "border-zinc-800 bg-zinc-900" : "border-gray-200 bg-gray-50"}`}>
            <div className="flex items-center gap-2">
              <span className={`text-xs ${sub}`}>
                {base?.state === "downloading"
                  ? `Downloading 2B base model… ${base.percent ?? 0}%`
                  : "Extract / Lego / Complete need the 2B base model (4.5 GB)."}
              </span>
              {base?.state !== "downloading" && (
                <button type="button" onClick={downloadBase}
                  className={`text-xs rounded-lg border px-2 py-1 ${isDark ? "border-zinc-700 text-zinc-200 hover:bg-zinc-800" : "border-gray-300 text-gray-700 hover:bg-gray-100"} ${focusRing}`}>
                  Download 2B base model
                </button>
              )}
            </div>
          </div>
        )}

        {buffer.subMode !== "create" && (
          <div className={`rounded-lg border p-3 ${isDark ? "border-zinc-800 bg-zinc-900" : "border-gray-200 bg-gray-50"}`}>
            <label className={`block text-sm font-medium mb-1 ${label}`}>Source audio</label>
            {buffer.srcAudioId ? (
              <div className="flex items-center gap-3">
                <audio controls src={musicSourceUrl(buffer.srcAudioId)} className="flex-1" />
                <span className={`text-xs whitespace-nowrap ${sub}`}>{buffer.srcName} · {buffer.srcDurationSec.toFixed(1)}s</span>
                <button
                  type="button"
                  onClick={() => onChange({ srcAudioId: null, srcName: "", srcDurationSec: 0 })}
                  className={`p-1 rounded ${isDark ? "hover:bg-zinc-800 text-zinc-400" : "hover:bg-gray-100 text-gray-500"} ${focusRing}`}
                  title="Clear"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <label className={`flex items-center justify-center gap-2 cursor-pointer text-sm rounded-lg border border-dashed px-3 py-4 ${isDark ? "border-zinc-700 text-zinc-300 hover:bg-zinc-800/40" : "border-gray-300 text-gray-700 hover:bg-gray-100"}`}>
                {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                {uploading ? "Uploading…" : "Choose an audio file (WAV / FLAC / OGG)"}
                <input
                  type="file"
                  accept="audio/*,.wav,.flac,.ogg"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void onPickSource(f);
                  }}
                />
              </label>
            )}
            {buffer.subMode === "cover" && (
              <div className="mt-3">
                <label className={`block text-sm font-medium mb-1 ${label}`}>Strength: {buffer.coverStrength.toFixed(2)}</label>
                <input
                  type="range"
                  min={0.1}
                  max={1}
                  step={0.05}
                  value={buffer.coverStrength}
                  onChange={(e) => onChange({ coverStrength: Number(e.target.value) })}
                  className="w-full accent-orange-600"
                />
                <p className={`text-xs mt-1 ${sub}`}>Lower = looser restyle · higher = closer to the source</p>
              </div>
            )}
            {buffer.subMode === "repaint" && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <label className={`block text-sm font-medium mb-1 ${label}`}>Repaint from (s)</label>
                  <input
                    type="number"
                    min={0}
                    max={buffer.srcDurationSec || undefined}
                    step={0.5}
                    value={buffer.repaintStart}
                    onChange={(e) => onChange({ repaintStart: Number(e.target.value) })}
                    className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`}
                  />
                </div>
                <div>
                  <label className={`block text-sm font-medium mb-1 ${label}`}>to (s, -1 = end)</label>
                  <input
                    type="number"
                    min={-1}
                    max={buffer.srcDurationSec || undefined}
                    step={0.5}
                    value={buffer.repaintEnd}
                    onChange={(e) => onChange({ repaintEnd: Number(e.target.value) })}
                    className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`}
                  />
                </div>
              </div>
            )}
            {(buffer.subMode === "extract" || buffer.subMode === "lego") && (
              <div className="mt-3">
                <label className={`block text-sm font-medium mb-1 ${label}`}>
                  {buffer.subMode === "extract" ? "Track to extract" : "Track to generate"}
                </label>
                <select value={buffer.trackName} onChange={(e) => onChange({ trackName: e.target.value })}
                  className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`}>
                  {TRACK_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                </select>
              </div>
            )}
            {buffer.subMode === "complete" && (
              <div className="mt-3">
                <label className={`block text-sm font-medium mb-1 ${label}`}>Add track classes (optional)</label>
                <div className="flex flex-wrap gap-1.5">
                  {TRACK_OPTIONS.map((t) => {
                    const on = buffer.trackClasses.includes(t.value);
                    return (
                      <button key={t.value} type="button"
                        onClick={() => onChange({ trackClasses: on
                          ? buffer.trackClasses.filter((v) => v !== t.value)
                          : [...buffer.trackClasses, t.value] })}
                        className={`px-2 py-1 text-xs rounded-md border ${on
                          ? "bg-orange-600 text-white border-orange-600"
                          : isDark ? "border-zinc-700 text-zinc-300 hover:bg-zinc-800" : "border-gray-300 text-gray-700 hover:bg-gray-100"} ${focusRing}`}>
                        {t.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {buffer.subMode === "create" && (
        <div className={`rounded-lg border p-3 ${isDark ? "border-zinc-800 bg-zinc-900" : "border-gray-200 bg-gray-50"}`}>
          <label className={`block text-sm font-medium mb-1 ${label}`}>Inspiration — describe your song</label>
          {lmReady ? (
            <>
              <div className="flex gap-2">
                <input type="text" value={query} onChange={(e) => setQuery(e.target.value)}
                  placeholder="e.g. a soft Bengali love song for a rainy evening"
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`} />
                <button type="button" disabled={inspiring || !query.trim()} onClick={onInspire}
                  className={`inline-flex items-center gap-1.5 rounded-lg bg-orange-600 px-3 py-2 text-sm font-medium text-white hover:bg-orange-500 disabled:opacity-50 ${focusRing}`}>
                  {inspiring ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />} Inspire
                </button>
              </div>
              <label className="flex items-center gap-2 mt-2 cursor-pointer">
                <input type="checkbox" checked={buffer.thinking}
                  onChange={(e) => onChange({ thinking: e.target.checked })}
                  className="accent-orange-600" />
                <span className={`text-xs ${sub}`}>
                  Enhance with AI — coherent structure &amp; higher quality (slower)
                </span>
              </label>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <span className={`text-xs ${sub}`}>
                {lm?.state === "downloading"
                  ? `Downloading AI model… ${lm.percent ?? 0}%`
                  : "Download the AI model (1.3 GB) for coherent, higher-quality music. Without it, tracks may break up after a few seconds."}
              </span>
              {lm?.state !== "downloading" && (
                <button type="button" onClick={downloadLm}
                  className={`text-xs whitespace-nowrap rounded-lg border px-2 py-1 ${isDark ? "border-zinc-700 text-zinc-200 hover:bg-zinc-800" : "border-gray-300 text-gray-700 hover:bg-gray-100"} ${focusRing}`}>
                  Download AI model
                </button>
              )}
            </div>
          )}
        </div>
        )}

        <div>
          <label className={`block text-sm font-medium mb-1 ${label}`}>Style / caption</label>
          <input
            type="text"
            value={buffer.caption}
            onChange={(e) => onChange({ caption: e.target.value })}
            maxLength={512}
            placeholder="e.g. upbeat lo-fi hip hop, mellow piano, soft drums"
            className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`}
          />
        </div>

        <div className="flex items-center gap-2">
          <input
            id="music-instrumental"
            type="checkbox"
            checked={buffer.instrumental}
            onChange={(e) => onChange({ instrumental: e.target.checked })}
            className="accent-orange-600"
          />
          <label htmlFor="music-instrumental" className={`text-sm ${label}`}>Instrumental (no vocals)</label>
        </div>

        <div>
          <label className={`block text-sm font-medium mb-1 ${label} ${buffer.instrumental ? "opacity-50" : ""}`}>
            Lyrics
          </label>
          <textarea
            value={buffer.lyrics}
            onChange={(e) => onChange({ lyrics: e.target.value })}
            disabled={buffer.instrumental}
            maxLength={4096}
            rows={5}
            placeholder={buffer.instrumental ? "Disabled for instrumental" : "Enter lyrics…"}
            className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing} disabled:opacity-50`}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onGenerate}
            disabled={busy || !engineReady || !buffer.caption.trim() || !sourceReady || !baseGateOk}
            className={`inline-flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500 disabled:opacity-50 ${focusRing}`}
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Music className="w-4 h-4" />}
            {busy ? `Generating… ${elapsed.toFixed(1)}s` : buffer.subMode === "create" ? "Generate music" : `Generate ${buffer.subMode}`}
          </button>
          {!engineReady && (
            <span className={`text-xs ${sub}`}>Select Music mode to set up the ACE-Step engine first.</span>
          )}
          {engineReady && !sourceReady && (
            <span className={`text-xs ${sub}`}>Upload a source clip to {buffer.subMode}.</span>
          )}
          {engineReady && isBaseMode && (
            <span className={`text-xs ${sub}`}>Base model uses ≥25 steps for quality.</span>
          )}
        </div>

        {error && (
          <div className={`text-sm rounded-lg border p-3 ${isDark ? "border-red-900 bg-red-950 text-red-300" : "border-red-200 bg-red-50 text-red-700"}`}>
            {error}
          </div>
        )}

        {clips.length > 0 && (
          <div className="space-y-3">
            {clips.map((c, i) => (
              <div
                key={c.cache_hash}
                className={`rounded-lg border p-3 ${isDark ? "border-zinc-800 bg-zinc-900" : "border-gray-200 bg-gray-50"}`}
              >
                {clips.length > 1 && (
                  <div className={`text-xs mb-1 ${sub}`}>Variation {i + 1} · {c.duration_sec.toFixed(1)}s</div>
                )}
                <audio controls src={musicClipAudioUrl(c.cache_hash)} className="w-full" />
                <div className="flex items-center gap-3 mt-1">
                  <a
                    href={musicDownloadUrl(c.cache_hash, "wav")}
                    download
                    className={`inline-flex items-center gap-1 text-xs ${isDark ? "text-orange-400 hover:text-orange-300" : "text-orange-600 hover:text-orange-700"}`}
                  >
                    <Download className="w-3.5 h-3.5" /> WAV
                  </a>
                  <a
                    href={musicDownloadUrl(c.cache_hash, "flac")}
                    download
                    className={`inline-flex items-center gap-1 text-xs ${isDark ? "text-orange-400 hover:text-orange-300" : "text-orange-600 hover:text-orange-700"}`}
                  >
                    <Download className="w-3.5 h-3.5" /> FLAC
                  </a>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
