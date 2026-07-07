import { useEffect, useRef, useState } from "react";
import { Loader2, Music, Download } from "lucide-react";
import { focusRing } from "@/lib/theme";
import { generateMusic } from "@/lib/api";
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
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  // Revoke the previous object URL when it changes / on unmount.
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const onGenerate = async () => {
    if (busy || !buffer.caption.trim()) return;
    setBusy(true);
    setError(null);
    setElapsed(0);
    const started = Date.now();
    timer.current = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 200);
    try {
      const blob = await generateMusic({
        caption: buffer.caption.trim(),
        lyrics: buffer.instrumental ? "" : buffer.lyrics,
        instrumental: buffer.instrumental,
        duration_sec: buffer.durationSec,
        steps: buffer.steps,
        seed: buffer.seed,
      });
      setAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
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

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className={`block text-sm font-medium mb-1 ${label}`}>Duration: {buffer.durationSec}s</label>
            <input
              type="range" min={10} max={240} step={5}
              value={buffer.durationSec}
              onChange={(e) => onChange({ durationSec: Number(e.target.value) })}
              className="w-full accent-orange-600"
            />
          </div>
          <div>
            <label className={`block text-sm font-medium mb-1 ${label}`}>Steps: {buffer.steps}</label>
            <input
              type="range" min={1} max={60} step={1}
              value={buffer.steps}
              onChange={(e) => onChange({ steps: Number(e.target.value) })}
              className="w-full accent-orange-600"
            />
          </div>
          <div>
            <label className={`block text-sm font-medium mb-1 ${label}`}>Seed</label>
            <input
              type="number"
              value={buffer.seed}
              onChange={(e) => onChange({ seed: Number(e.target.value) })}
              className={`w-full rounded-lg border px-3 py-2 text-sm ${inputBg} ${focusRing}`}
            />
            <p className={`text-xs mt-1 ${sub}`}>-1 = random</p>
          </div>
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

        {audioUrl && (
          <div className="space-y-2">
            <audio controls src={audioUrl} className="w-full" />
            <a
              href={audioUrl}
              download="acestep-music.wav"
              className={`inline-flex items-center gap-1.5 text-sm ${isDark ? "text-orange-400 hover:text-orange-300" : "text-orange-600 hover:text-orange-700"}`}
            >
              <Download className="w-4 h-4" /> Download WAV
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
