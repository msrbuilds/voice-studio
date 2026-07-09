import { useEffect, useState } from "react";
import { Loader2, Pencil, Wand2, X } from "lucide-react";
import { ApiError, transcribeVoice } from "@/lib/api";
import { focusRing } from "@/lib/theme";
import { isRtlText, textDirection } from "@/lib/textStats";
import type { Voice, VoiceMetadata } from "@/types/models";

interface Props {
  voice: Voice | null;
  theme: "light" | "dark";
  onClose: () => void;
  onSave: (meta: VoiceMetadata) => Promise<void>;
}

export function VoiceMetaDialog({ voice, theme, onClose, onSave }: Props) {
  const [name, setName] = useState("");
  const [gender, setGender] = useState<"man" | "woman" | "nonbinary" | "">("");
  const [language, setLanguage] = useState("en");
  const [transcript, setTranscript] = useState("");
  const [busy, setBusy] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isDark = theme === "dark";

  useEffect(() => {
    if (voice) {
      setName(voice.name);
      setGender((voice.gender as "man" | "woman" | "nonbinary" | null) ?? "");
      setLanguage(voice.language ?? "en");
      setTranscript(voice.reference_transcript ?? "");
      setError(null);
    }
  }, [voice]);

  if (!voice) return null;

  const handleSubmit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onSave({
        name: name.trim() || undefined,
        gender: gender || undefined,
        language: language.trim() || undefined,
        reference_transcript: transcript.trim(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  // Fills the field but does NOT save — the user reviews, then presses Save.
  const handleTranscribe = async () => {
    setTranscribing(true);
    setError(null);
    try {
      const res = await transcribeVoice(voice.id, language.trim() || null);
      setTranscript(res.text);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 503
          ? "Speech-to-text weights aren't downloaded yet. Open Transcribe mode to download Whisper."
          : err instanceof Error
            ? err.message
            : String(err),
      );
    } finally {
      setTranscribing(false);
    }
  };

  const surface = isDark ? "bg-zinc-900" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const text = isDark ? "text-white" : "text-gray-900";
  const labelText = isDark ? "text-zinc-400" : "text-gray-600";
  const subtext = isDark ? "text-zinc-400" : "text-gray-600";
  const idColor = isDark ? "text-zinc-400" : "text-gray-700";
  const inputBg = isDark ? "bg-zinc-800" : "bg-white";
  const inputBorder = isDark ? "border-zinc-700" : "border-gray-300";
  const inputText = isDark ? "text-white" : "text-gray-900";
  const placeholder = isDark ? "placeholder-zinc-500" : "placeholder-gray-400";
  const cancelText = isDark ? "text-zinc-300 hover:text-white" : "text-gray-600 hover:text-gray-900";

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className={`${surface} ${border} border rounded-xl shadow-xl w-full max-w-md p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Pencil className="w-5 h-5 text-orange-400" />
            <h2 className={`text-lg font-semibold ${text}`}>Edit voice</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`p-1 ${isDark ? "text-zinc-400 hover:text-white" : "text-gray-600 hover:text-gray-900"} ${focusRing}`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className={`text-xs mb-4 ${subtext}`}>
          <code className={idColor}>{voice.id}</code>
          {" · "}
          <span className="capitalize">{voice.source}</span>
        </p>

        <div className="space-y-3">
          <label className="block">
            <span className={`text-xs font-medium mb-1 block ${labelText}`}>Display name</span>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Amelia"
              className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} ${placeholder} focus:outline-none focus:border-orange-500`}
            />
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className={`text-xs font-medium mb-1 block ${labelText}`}>Gender</span>
              <select
                value={gender}
                onChange={(e) => setGender(e.target.value as typeof gender)}
                className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} focus:outline-none focus:border-orange-500`}
              >
                <option value="">—</option>
                <option value="woman">Woman</option>
                <option value="man">Man</option>
                <option value="nonbinary">Non-binary</option>
              </select>
            </label>
            <label className="block">
              <span className={`text-xs font-medium mb-1 block ${labelText}`}>Language</span>
              <input
                type="text"
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                placeholder="en"
                maxLength={8}
                className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} ${placeholder} focus:outline-none focus:border-orange-500`}
              />
            </label>
          </div>

          <label className="block">
            <div className="flex items-center justify-between mb-1">
              <span className={`text-xs font-medium block ${labelText}`}>
                Reference transcript <span className="opacity-60">(optional, for VoxCPM)</span>
              </span>
              <button
                type="button"
                onClick={() => void handleTranscribe()}
                disabled={transcribing || busy}
                title="Transcribe this clip with Whisper, then review before saving"
                className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md border transition-colors disabled:cursor-not-allowed ${
                  isDark
                    ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border-zinc-700 disabled:text-zinc-500"
                    : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300 disabled:text-gray-400"
                } ${focusRing}`}
              >
                {transcribing ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" /> Transcribing…
                  </>
                ) : (
                  <>
                    <Wand2 className="w-3 h-3" /> Transcribe
                  </>
                )}
              </button>
            </div>
            <textarea
              value={transcript}
              onChange={(e) => setTranscript(e.target.value)}
              rows={2}
              placeholder="Exact words spoken in this voice's reference clip"
              dir={textDirection(transcript)}
              className={`w-full px-3 py-2 ${inputBg} ${inputBorder} border rounded-md text-sm ${inputText} ${placeholder} focus:outline-none focus:border-orange-500 ${
                isRtlText(transcript) ? "text-right" : "text-left"
              }`}
            />
          </label>
        </div>

        {error && (
          <p className="mt-3 text-sm text-red-400">{error}</p>
        )}

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className={`px-4 py-2 text-sm ${cancelText} ${focusRing}`}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={busy}
            className={`px-4 py-2 text-sm bg-orange-600 hover:bg-orange-500 disabled:bg-zinc-700 disabled:text-zinc-400 text-white rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${focusRing}`}
          >
            {busy ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}
