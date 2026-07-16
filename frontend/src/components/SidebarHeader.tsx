import { useState } from "react";
import { Moon, PanelLeftClose, PanelLeftOpen, RefreshCw, Sun } from "lucide-react";
import { useUpdate } from "@/hooks/useUpdate";
import { UpdateDialog } from "./UpdateDialog";
import { focusRing } from "@/lib/theme";

// The left column's chrome — logo, product name, version + update check, and the
// collapse control. Shared by every left panel (VoiceLibrary, TranscribeControls)
// so they can't drift apart: the Transcribe panel originally cloned this by hand
// and silently lost the version check and collapse toggle.

function iconBtnCls(isDark: boolean): string {
  return isDark
    ? "text-zinc-400 hover:text-white hover:bg-zinc-800"
    : "text-gray-600 hover:text-gray-900 hover:bg-gray-100";
}

interface HeaderProps {
  isDark: boolean;
  /** Rendered as `v{version}`; em dash while config is still loading. */
  version: string | null | undefined;
  onCollapse: () => void;
  collapseTitle: string;
}

export function SidebarHeader({ isDark, version, onCollapse, collapseTitle }: HeaderProps) {
  const { info: updateInfo, checking, check } = useUpdate();
  const [updateOpen, setUpdateOpen] = useState(false);
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const heading = isDark ? "text-zinc-400" : "text-gray-600";
  const iconBtn = iconBtnCls(isDark);

  return (
    <>
      <div className={`p-3 xxl:p-4 border-b flex items-center gap-3 ${border}`}>
        <img
          src={isDark ? "/logo-dark-sm.png" : "/logo-light-sm.png"}
          alt="Voice Studio logo"
          width={36}
          height={36}
          className="w-9 h-9 rounded-lg shrink-0"
        />
        <div className="min-w-0 flex-1">
          <h1 className={`font-semibold text-sm truncate ${isDark ? "text-white" : "text-gray-900"}`}>
            Voice Studio by MSR
          </h1>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className={`text-xs tabular-nums ${heading}`}>v{version ?? "—"}</span>
            <button
              type="button"
              onClick={() => (updateInfo?.update_available ? setUpdateOpen(true) : void check())}
              disabled={checking}
              className={`relative p-0.5 rounded transition-colors ${iconBtn} ${focusRing}`}
              title={updateInfo?.update_available ? `Update to v${updateInfo.latest}` : "Check for updates"}
            >
              <RefreshCw className={`w-3 h-3 ${checking ? "animate-spin" : ""}`} />
              {updateInfo?.update_available && !checking && (
                <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-orange-500" />
              )}
            </button>
          </div>
        </div>
        <button
          type="button"
          onClick={onCollapse}
          className={`p-1 rounded transition-colors ${iconBtn} ${focusRing}`}
          title={collapseTitle}
        >
          <PanelLeftClose className="w-4 h-4" />
        </button>
      </div>
      {updateOpen && updateInfo && (
        <UpdateDialog isDark={isDark} info={updateInfo} onClose={() => setUpdateOpen(false)} />
      )}
    </>
  );
}

interface StripProps {
  isDark: boolean;
  onOpen: () => void;
  openTitle: string;
  onThemeToggle: () => void;
}

/** The collapsed left column: logo, re-open control, theme toggle. */
export function SidebarStrip({ isDark, onOpen, openTitle, onThemeToggle }: StripProps) {
  const surface = isDark ? "bg-zinc-950" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const iconBtn = iconBtnCls(isDark);

  return (
    <aside
      className={`w-12 shrink-0 z-10 border-r flex flex-col items-center pt-4 gap-3 transition-colors ${surface} ${border}`}
    >
      <img
        src={isDark ? "/logo-dark-sm.png" : "/logo-light-sm.png"}
        alt="Voice Studio logo"
        width={36}
        height={36}
        className="w-9 h-9 rounded-lg"
      />
      <button
        type="button"
        onClick={onOpen}
        className={`p-2 rounded-lg transition-colors ${iconBtn} ${focusRing}`}
        title={openTitle}
      >
        <PanelLeftOpen className="w-5 h-5" />
      </button>
      <button
        type="button"
        onClick={onThemeToggle}
        className={`p-2 rounded-lg transition-colors ${iconBtn} ${focusRing}`}
        title="Toggle theme"
      >
        {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
      </button>
    </aside>
  );
}
