import { useCallback, useEffect, useRef, useState } from "react";
import { Copy, Download, FileAudio, Loader2, Send, Upload } from "lucide-react";
import { ApiError, transcribe } from "@/lib/api";
import { segmentsToSrt, segmentsToVtt } from "@/lib/subtitles";
import { isRtlText, textDirection } from "@/lib/textStats";
import { focusRing } from "@/lib/theme";
import type { AsrStatus, TranscribeBuffer } from "@/types/models";

interface Props {
  isDark: boolean;
  buffer: TranscribeBuffer;
  onChange: (partial: Partial<TranscribeBuffer>) => void;
  asr: AsrStatus | null;
  onDownloadWeights: () => void;
  onSendToTts: (text: string) => void;
}

const ACCEPT = ".wav,.mp3,.flac,.ogg,.m4a,.webm";

function saveText(name: string, body: string, mime: string) {
  const url = URL.createObjectURL(new Blob([body], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function TranscribeEditor({
  isDark,
  buffer,
  onChange,
  asr,
  onDownloadWeights,
  onSendToTts,
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const weightsMissing = asr != null && !asr.downloaded;
  const canRun = !!file && !busy && !!asr && asr.downloaded;

  useEffect(() => {
    if (!busy) return;
    const t0 = Date.now();
    const id = window.setInterval(() => setElapsed((Date.now() - t0) / 1000), 100);
    return () => window.clearInterval(id);
  }, [busy]);

  const run = useCallback(async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setElapsed(0);
    try {
      const res = await transcribe({
        file,
        language: buffer.language,
        timestamps: buffer.timestamps,
      });
      onChange({
        text: res.text,
        segments: res.segments,
        detectedLanguage: res.language,
        fileName: file.name,
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Transcription failed");
    } finally {
      setBusy(false);
    }
  }, [file, buffer.language, buffer.timestamps, onChange]);

  const pick = (f: File | null | undefined) => {
    if (!f) return;
    setFile(f);
    setError(null);
  };

  const panel = isDark ? "bg-zinc-900 border-zinc-800" : "bg-white border-gray-200";
  const text = isDark ? "text-white" : "text-gray-900";
  const subtle = isDark ? "text-zinc-400" : "text-gray-600";
  const btn = `px-3 py-2 rounded-lg text-sm font-medium transition-colors border ${
    isDark
      ? "bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border-zinc-700"
      : "bg-gray-100 hover:bg-gray-200 text-gray-700 border-gray-300"
  } ${focusRing}`;

  if (weightsMissing) {
    return (
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className={`max-w-2xl mx-auto p-6 rounded-xl border ${panel}`}>
          <h2 className={`text-lg font-semibold ${text}`}>Speech-to-text needs a one-time download</h2>
          <p className={`text-sm mt-2 ${subtle}`}>
            Whisper large-v3-turbo is about 1.6 GB. It runs fully offline once downloaded, and
            transcribes 99 languages.
          </p>
          <button
            type="button"
            onClick={onDownloadWeights}
            className={`mt-4 px-4 py-2 rounded-lg bg-orange-600 hover:bg-orange-500 text-white text-sm font-medium ${focusRing}`}
          >
            Download Whisper (1.6 GB)
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4">
      <div className="max-w-4xl mx-auto space-y-4">
        {error && (
          <div
            className={`p-3 rounded-lg border text-sm ${
              isDark
                ? "bg-red-900/30 border-red-600/40 text-red-200"
                : "bg-red-50 border-red-200 text-red-700"
            }`}
          >
            {error}
          </div>
        )}

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pick(e.dataTransfer.files?.[0]);
          }}
          className={`p-6 rounded-xl border-2 border-dashed text-center transition-colors ${
            dragOver ? "border-orange-500" : isDark ? "border-zinc-700" : "border-gray-300"
          } ${panel}`}
        >
          <FileAudio className="w-8 h-8 mx-auto mb-2 text-orange-400" />
          <p className={`text-sm ${text}`}>
            {file ? file.name : "Drop an audio file here, or choose one"}
          </p>
          <p className={`text-xs mt-1 ${subtle}`}>WAV, MP3, FLAC, OGG, M4A, WebM · up to 100 MB</p>

          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => pick(e.target.files?.[0])}
          />
          <div className="flex items-center justify-center gap-2 mt-4">
            <button type="button" onClick={() => inputRef.current?.click()} className={btn}>
              <span className="flex items-center gap-1.5">
                <Upload className="w-4 h-4" /> Choose file
              </span>
            </button>
            <button
              type="button"
              onClick={() => void run()}
              disabled={!canRun}
              className={`px-4 py-2 rounded-lg text-sm font-medium text-white transition-colors ${focusRing} ${
                canRun ? "bg-orange-600 hover:bg-orange-500" : "bg-orange-600/40 cursor-not-allowed"
              }`}
            >
              {busy ? (
                <span className="flex items-center gap-1.5">
                  <Loader2 className="w-4 h-4 animate-spin" /> Transcribing… {elapsed.toFixed(1)}s
                </span>
              ) : (
                "Transcribe"
              )}
            </button>
          </div>
        </div>

        {(buffer.text || buffer.segments.length > 0) && (
          <div className={`p-4 rounded-xl border ${panel}`}>
            <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
              <h3 className={`text-sm font-semibold ${text}`}>
                Transcript
                {buffer.detectedLanguage && (
                  <span className={`ml-2 font-normal ${subtle}`}>
                    detected: {buffer.detectedLanguage}
                  </span>
                )}
              </h3>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={btn}
                  onClick={() => void navigator.clipboard.writeText(buffer.text)}
                >
                  <span className="flex items-center gap-1.5">
                    <Copy className="w-4 h-4" /> Copy
                  </span>
                </button>
                <button
                  type="button"
                  className={btn}
                  disabled={!buffer.text.trim()}
                  onClick={() => onSendToTts(buffer.text)}
                >
                  <span className="flex items-center gap-1.5">
                    <Send className="w-4 h-4" /> Send to Text-to-Voice
                  </span>
                </button>
                <button
                  type="button"
                  className={btn}
                  disabled={buffer.segments.length === 0}
                  title={
                    buffer.segments.length === 0
                      ? "Enable Timestamps and transcribe again"
                      : "Download SubRip subtitles"
                  }
                  onClick={() =>
                    saveText(
                      `${buffer.fileName || "transcript"}.srt`,
                      segmentsToSrt(buffer.segments),
                      "text/plain",
                    )
                  }
                >
                  <span className="flex items-center gap-1.5">
                    <Download className="w-4 h-4" /> .srt
                  </span>
                </button>
                <button
                  type="button"
                  className={btn}
                  disabled={buffer.segments.length === 0}
                  onClick={() =>
                    saveText(
                      `${buffer.fileName || "transcript"}.vtt`,
                      segmentsToVtt(buffer.segments),
                      "text/vtt",
                    )
                  }
                >
                  <span className="flex items-center gap-1.5">
                    <Download className="w-4 h-4" /> .vtt
                  </span>
                </button>
              </div>
            </div>

            <textarea
              value={buffer.text}
              onChange={(e) => onChange({ text: e.target.value })}
              rows={10}
              spellCheck={false}
              dir={textDirection(buffer.text)}
              className={`w-full rounded-lg border px-3 py-2 text-sm resize-y ${
                isRtlText(buffer.text) ? "text-right" : "text-left"
              } ${
                isDark
                  ? "bg-zinc-950 border-zinc-800 text-zinc-100"
                  : "bg-white border-gray-200 text-gray-900"
              } ${focusRing}`}
            />

            {buffer.segments.length > 0 && (
              <details className="mt-3">
                <summary className={`text-xs cursor-pointer ${subtle}`}>
                  {buffer.segments.length} timestamped segment
                  {buffer.segments.length !== 1 ? "s" : ""}
                </summary>
                <ul className={`mt-2 text-xs space-y-1 ${subtle}`}>
                  {buffer.segments.map((s, i) => (
                    <li key={i}>
                      <span className="tabular-nums">
                        [{s.start.toFixed(2)}–{s.end.toFixed(2)}]
                      </span>{" "}
                      {s.text}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
