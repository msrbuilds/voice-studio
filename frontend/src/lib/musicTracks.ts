export interface TrackOption { value: string; label: string }

// ACE-Step's 12 fixed stems (constants.TRACK_NAMES), with display labels.
export const TRACK_OPTIONS: TrackOption[] = [
  { value: "drums", label: "Drums" },
  { value: "bass", label: "Bass" },
  { value: "vocals", label: "Vocals" },
  { value: "backing_vocals", label: "Backing vocals" },
  { value: "guitar", label: "Guitar" },
  { value: "keyboard", label: "Keyboard" },
  { value: "synth", label: "Synth" },
  { value: "strings", label: "Strings" },
  { value: "brass", label: "Brass" },
  { value: "woodwinds", label: "Woodwinds" },
  { value: "percussion", label: "Percussion" },
  { value: "fx", label: "FX" },
];
