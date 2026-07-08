import { useRef, useState } from "react";
import { Loader2, Music, Download } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { generateMusic, musicClipAudioUrl, musicDownloadUrl, type MusicClip } from "@/lib/api";
import { keyToParam, timeSigToNumerator } from "@/lib/musicOptions";
import type { MusicBuffer } from "@/types/models";

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

  const onGenerate = async () => {
    if (busy || !buffer.caption.trim()) return;
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
            disabled={busy || !engineReady || !buffer.caption.trim()}
            className={`inline-flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-500 disabled:opacity-50 ${focusRing}`}
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Music className="w-4 h-4" />}
            {busy ? `Generating… ${elapsed.toFixed(1)}s` : "Generate music"}
          </button>
          {!engineReady && (
            <span className={`text-xs ${sub}`}>Select Music mode to set up the ACE-Step engine first.</span>
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
