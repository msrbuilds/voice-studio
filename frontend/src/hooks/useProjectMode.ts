import { useCallback, useEffect, useState } from "react";
import type { MusicBuffer, ProjectMode, TtsBuffer } from "@/types/models";

const MODE_KEY = "vs.mode";
const TTS_KEY = "vs.tts";
const MUSIC_KEY = "vs.music";
const EMPTY_TTS: TtsBuffer = { text: "", voiceId: null, language: null };
const EMPTY_MUSIC: MusicBuffer = {
  caption: "",
  lyrics: "",
  instrumental: true,
  durationSec: 30,
  steps: 8,
  seed: -1,
};

function readMode(): ProjectMode | null {
  const v = localStorage.getItem(MODE_KEY);
  return v === "tts" || v === "podcast" || v === "music" ? v : null;
}
function readMusic(): MusicBuffer {
  try {
    const raw = localStorage.getItem(MUSIC_KEY);
    if (!raw) return EMPTY_MUSIC;
    const p = JSON.parse(raw) as Partial<MusicBuffer>;
    return { ...EMPTY_MUSIC, ...p };
  } catch {
    return EMPTY_MUSIC;
  }
}
function readTts(): TtsBuffer {
  try {
    const raw = localStorage.getItem(TTS_KEY);
    if (!raw) return EMPTY_TTS;
    const p = JSON.parse(raw) as Partial<TtsBuffer>;
    return {
      text: p.text ?? "",
      voiceId: p.voiceId ?? null,
      language: p.language ?? null,
      omnivoiceMode: p.omnivoiceMode,
      voiceDesign: p.voiceDesign,
    };
  } catch {
    return EMPTY_TTS;
  }
}

export interface UseProjectModeApi {
  mode: ProjectMode | null;
  setMode: (m: ProjectMode) => void;
  tts: TtsBuffer;
  setTtsText: (text: string) => void;
  setTtsVoice: (voiceId: string | null) => void;
  setTtsLanguage: (language: string | null) => void;
  setTtsOmniMode: (mode: "clone" | "design" | "auto") => void;
  setTtsVoiceDesign: (voiceDesign: string) => void;
  music: MusicBuffer;
  setMusic: (partial: Partial<MusicBuffer>) => void;
}

export function useProjectMode(): UseProjectModeApi {
  const [mode, setModeState] = useState<ProjectMode | null>(readMode);
  const [tts, setTts] = useState<TtsBuffer>(readTts);
  const [music, setMusicState] = useState<MusicBuffer>(readMusic);

  useEffect(() => {
    if (mode) localStorage.setItem(MODE_KEY, mode);
  }, [mode]);
  useEffect(() => {
    localStorage.setItem(TTS_KEY, JSON.stringify(tts));
  }, [tts]);
  useEffect(() => {
    localStorage.setItem(MUSIC_KEY, JSON.stringify(music));
  }, [music]);

  const setMode = useCallback((m: ProjectMode) => setModeState(m), []);
  const setTtsText = useCallback((text: string) => setTts((t) => ({ ...t, text })), []);
  const setTtsVoice = useCallback((voiceId: string | null) => setTts((t) => ({ ...t, voiceId })), []);
  const setTtsLanguage = useCallback((language: string | null) => setTts((t) => ({ ...t, language })), []);
  const setTtsOmniMode = useCallback(
    (omnivoiceMode: "clone" | "design" | "auto") => setTts((t) => ({ ...t, omnivoiceMode })),
    [],
  );
  const setTtsVoiceDesign = useCallback(
    (voiceDesign: string) => setTts((t) => ({ ...t, voiceDesign })),
    [],
  );
  const setMusic = useCallback(
    (partial: Partial<MusicBuffer>) => setMusicState((m) => ({ ...m, ...partial })),
    [],
  );

  return {
    mode,
    setMode,
    tts,
    setTtsText,
    setTtsVoice,
    setTtsLanguage,
    setTtsOmniMode,
    setTtsVoiceDesign,
    music,
    setMusic,
  };
}
