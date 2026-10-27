"""Run: python tests/frontend_tray_check.py [path/to/AutoHotkey64.exe].

Uses a separate, non-input Windows desktop and temporary settings. Includes the
real frontend functions, but exits before its normal startup: no game input,
SteamVR launch, shared mapping, heartbeat, or owner-settings writes.
"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile


CHECK = r'''
#Requires AutoHotkey v2.0
try {
    CheckShortcuts()
    CheckDriverToggle()
    CheckWindowIcons()
    FileAppend("PASS shortcut conflicts/persistence, Null Driver backup guards, and dynamic window icons`n", "*")
    ExitApp(0)
} catch as e {
    FileAppend(e.Message " at line " e.Line "`n", "**")
    ExitApp(1)
}
#Include FRONTEND_PATH

CheckShortcuts() {
    global MovementMode := false, ConsoleCommandBusy := true
    global MovementToggleHotkey := "", MovementToggleHotkeyDefault := "^+m"
    global MovementToggleHeld := false, MovementToggleEdit := ""
    global PhysicalKeys := Map(), LogicalKeys := Map()
    global TrayControlsInitialized := false
    global BootstrapFile := A_ScriptDir "\settings.ini", ErrorLogFile := A_ScriptDir "\errors.log"
    global AllBindActions := ["Interact"]
    global MovementKeyBinds := Map("Interact", "sc013"), MovementKeyLabels := Map("Interact", "Interact")
    LoadMovementToggleHotkey()
    SetMovementToggleHotkey("^!k")
    oldCombo := MovementToggleHotkey
    saved := IniRead(BootstrapFile, "KeyBinds", "MovementModeToggle")
    for value in ["m", "^+", "^+F23", "^+Numpad5", "^+LShift", "^+e"]
        Reject(value, "Choose")
    Reject("^+r", "already used")
    Check(MovementToggleHotkey = oldCombo, "Conflict replaced active shortcut")
    Check(IniRead(BootstrapFile, "KeyBinds", "MovementModeToggle") = saved, "Conflict changed saved shortcut")

    Check(DllCall("RegisterHotKey", "Ptr", A_ScriptHwnd, "Int", 0x4D54, "UInt", 7, "UInt", 0x78), "Could not reserve test Ctrl+Alt+Shift+F9")
    try {
        Reject("^!+F9", "Windows could not register")
        Check(MovementToggleHotkey = oldCombo, "OS conflict replaced active shortcut")
    } finally
        DllCall("UnregisterHotKey", "Ptr", A_ScriptHwnd, "Int", 0x4D54)

    BootstrapFile := A_ScriptDir
    Reject("^+F8", "could not be saved")
    Check(MovementToggleHotkey = oldCombo, "Failed save replaced active shortcut")
    BootstrapFile := A_ScriptDir "\settings.ini"
    Check(IniRead(BootstrapFile, "KeyBinds", "MovementModeToggle") = saved, "Failed save changed saved shortcut")
    SetMovementToggleHotkey("^+F8")
    Check(MovementToggleHotkeyDisplay() = "Ctrl+Shift+F8", "Named key was lost from shortcut label")
    Check(IniRead(BootstrapFile, "KeyBinds", "MovementModeToggle") = MovementToggleHotkey, "Replacement did not persist")
    RegisterMovementToggle(MovementToggleHotkey, false)
    MovementToggleHotkey := ""
    LoadMovementToggleHotkey()
    Check(MovementToggleHotkeyDisplay() = "Ctrl+Shift+F8", "Custom shortcut did not survive reload")
    SetMovementToggleHotkey("!+F8")
    Check(MovementToggleHotkeyDisplay() = "Alt+Shift+F8", "Same-base modifier change was lost")
    SetMovementToggleHotkey("^+F8")

    ; Sprint suppresses physical Shift and sends logical Alt. Match only the physical combination.
    PhysicalKeys := Map("Ctrl", true, "Shift", true)
    LogicalKeys := Map("Ctrl", true, "Alt", true)
    Check(MovementToggleContext(), "Physical Ctrl+Shift rejected in favor of remapped logical Alt")
    PhysicalKeys["Alt"] := true
    Check(!MovementToggleContext(), "Unexpected physical modifier accepted")
    PhysicalKeys.Delete("Alt")
    PhysicalKeys["LWin"] := true
    Check(!MovementToggleContext(), "Win-modified shortcut accepted")
    PhysicalKeys := Map()
    Check(!MovementToggleContext(), "Unmodified key would toggle Movement Mode")
    MovementToggleHeld := true
    Check(MovementToggleContext(), "Released modifiers stopped swallowing held-key repeats")

    ; A failed shortcut reset must not restore gameplay G over the retained Ctrl+Shift+G shortcut.
    MovementToggleHeld := false
    global MenuActions := [], ControlActions := ["RightGrip"]
    AllBindActions := ["RightGrip"]
    MovementKeyBinds := Map("RightGrip", "")
    MovementKeyLabels := Map("RightGrip", "Right Grip")
    global MovementKeyDefaults := Map("RightGrip", "sc022")
    SetMovementToggleHotkey("^+g")
    window := Gui()
    buttons := Map("RightGrip", window.AddButton(, "NONE"))
    Check(DllCall("RegisterHotKey", "Ptr", A_ScriptHwnd, "Int", 0x4D54, "UInt", 6, "UInt", 0x4D), "Could not reserve Ctrl+Shift+M")
    try {
        ResetKeyBindsToDefaults(buttons)
        Check(MovementKeyBinds["RightGrip"] = "", "Failed reset enabled gameplay key over shortcut")
        Check(buttons["RightGrip"].Text = "NONE", "Failed reset changed displayed gameplay binding")
        Check(MovementToggleHotkeyDisplay() = "Ctrl+Shift+G", "Failed reset changed active shortcut")
        Check(IniRead(BootstrapFile, "KeyBinds", "MovementModeToggle") = MovementToggleHotkey, "Failed reset changed saved shortcut")
    } finally {
        DllCall("UnregisterHotKey", "Ptr", A_ScriptHwnd, "Int", 0x4D54)
        window.Destroy()
    }
}

CheckDriverToggle() {
    global MainGui := Gui(), Active := "Original", NullDriverKey := "driver_null"
    global StatusText := MainGui.AddText(), ChkDriverEnabled := MainGui.AddCheckbox()
    global LivePath := A_ScriptDir "\steamvr.vrsettings"
    global StagingFile := A_ScriptDir "\steamvr.backup", ConfigFile := A_ScriptDir "\driver-state.ini"
    global MovementModeRequested := false, TrayControlsInitialized := false
    global TrayMovementItemLabel := "", TrayMovementIconAttemptedState := "OFF"
    original := '{"driver_null":{"enable":false},"steamvr":{"supersampleScale":1.3}}'
    WriteFileUtf8(LivePath, original)
    ChkDriverEnabled.OnEvent("Click", ToggleDriverEnabled)
    InitTrayControls()
    id := TrayItemId("Enable Null Driver in SteamVR")
    DetectHiddenWindows(true)
    PostMessage(0x111, id, 0,, "ahk_id " A_ScriptHwnd)
    Sleep(50)
    Check(ReadNullDriverEnabled(FileRead(LivePath)), "Tray enable did not update configuration")
    Check(FileRead(StagingFile) = original, "Enabling lost the original configuration backup")
    Check(ChkDriverEnabled.Value && TrayItemChecked(id), "Enable left checkbox/tray out of sync")
    Check(IniRead(ConfigFile, "State", "Active") = "Modded", "Enabled state was not saved")
    SendMessage(0xF5, 0, 0, ChkDriverEnabled)
    Sleep(-1) ; Dispatch the checkbox's queued AHK Click callback before checking the file.
    Check(FileRead(LivePath) = original, "Checkbox disable did not restore the flag while preserving settings")
    Check(!TrayItemChecked(id), "Checkbox disable left the tray checked")

    ; The config may change outside this frontend; toggle its current value, not a stale checkbox.
    WriteFileUtf8(LivePath, SetNullDriverEnabled(original, true))
    ToggleDriverFromTray()
    Check(FileRead(LivePath) = original, "Tray toggled stale checkbox state instead of current config")

    ToggleDriverFromTray()
    FileDelete(StagingFile)
    enabled := FileRead(LivePath)
    ToggleDriverFromTray()
    Check(FileRead(LivePath) = enabled, "Missing-backup guard allowed disabling")
    Check(ChkDriverEnabled.Value && TrayItemChecked(id), "Rejected disable changed checked state")
    FileDelete(LivePath)
    Active := "Original"
    ToggleDriverFromTray()
    Check(!FileExist(LivePath), "Missing-file failure created a SteamVR config")
    Check(!ChkDriverEnabled.Value && !TrayItemChecked(id), "Failed enable left checked state")
    MainGui.Destroy()
}

CheckWindowIcons() {
    global MainGui := Gui(), MovementModeRequested, TrayMovementIconAttemptedState := ""
    hidden := Gui()
    MainGui.Show("NA w200 h80")
    DetectHiddenWindows(false)
    offImages := Map()
    for state in ["OFF", "ON", "OFF"] {
        MovementModeRequested := state = "ON"
        UpdateTrayControls()
        Check(!A_DetectHiddenWindows, "Icon refresh changed hidden-window detection")
        created := Gui()
        for window in [MainGui, hidden, created] {
            for size in [0, 1] {
                key := (window.Hwnd = created.Hwnd ? "new" : window.Hwnd) ":" size
                image := WindowIconImage(window, size)
                if !offImages.Has(key)
                    offImages[key] := image
                else
                    Check(state = "ON" ? image != offImages[key] : image = offImages[key],
                        "Window icon did not follow OFF/ON/OFF: " key)
            }
        }
        created.Destroy()
    }
    hidden.Destroy()
    Check(WindowIconImage(MainGui, 1) = offImages[MainGui.Hwnd ":1"],
        "Closing another window invalidated the shared icon")
    MainGui.Destroy()
}

WindowIconImage(window, size) {
    icon := DllCall("SendMessageW", "Ptr", window.Hwnd, "UInt", 0x7F, "Ptr", size, "Ptr", 0, "Ptr")
    dc := DllCall("CreateCompatibleDC", "Ptr", 0, "Ptr")
    header := Buffer(40, 0)
    NumPut("UInt", 40, "Int", 32, "Int", -32, "UShort", 1, "UShort", 32, header)
    bits := 0
    bitmap := DllCall("CreateDIBSection", "Ptr", dc, "Ptr", header, "UInt", 0,
        "Ptr*", &bits, "Ptr", 0, "UInt", 0, "Ptr")
    Check(bitmap && bits, "Could not allocate icon rendering bitmap")
    previous := DllCall("SelectObject", "Ptr", dc, "Ptr", bitmap, "Ptr")
    try {
        DllCall("PatBlt", "Ptr", dc, "Int", 0, "Int", 0, "Int", 32, "Int", 32, "UInt", 0x42)
        Check(DllCall("DrawIconEx", "Ptr", dc, "Int", 0, "Int", 0, "Ptr", icon,
            "Int", 32, "Int", 32, "UInt", 0, "Ptr", 0, "UInt", 3), "Invalid window icon")
        DllCall("GdiFlush")
        return DllCall("ntdll\RtlComputeCrc32", "UInt", 0, "Ptr", bits, "UInt", 4096, "UInt")
    } finally {
        DllCall("SelectObject", "Ptr", dc, "Ptr", previous)
        DllCall("DeleteObject", "Ptr", bitmap)
        DllCall("DeleteDC", "Ptr", dc)
    }
}

TrayItemId(label) {
    Loop DllCall("GetMenuItemCount", "Ptr", A_TrayMenu.Handle, "Int") {
        text := Buffer(512)
        DllCall("GetMenuStringW", "Ptr", A_TrayMenu.Handle, "UInt", A_Index - 1,
            "Ptr", text, "Int", 256, "UInt", 0x400)
        if StrGet(text) = label
            return DllCall("GetMenuItemID", "Ptr", A_TrayMenu.Handle, "Int", A_Index - 1, "UInt")
    }
    throw Error("Tray item missing: " label)
}

TrayItemChecked(id) {
    return DllCall("GetMenuState", "Ptr", A_TrayMenu.Handle, "UInt", id, "UInt", 0, "UInt") & 8
}

Reject(value, reason) {
    try SetMovementToggleHotkey(value)
    catch as e {
        Check(InStr(e.Message, reason), "Wrong failure for " value ": " e.Message)
        return
    }
    throw Error("Accepted invalid, conflicting, or unsaved shortcut: " value)
}

MsgBox(*) {
    ; Error reporting is a UI boundary; verify retained bindings without a modal on the inactive desktop.
    return "OK"
}

GetKeyState(key, mode := "") {
    global PhysicalKeys, LogicalKeys
    keys := mode = "P" ? PhysicalKeys : LogicalKeys
    return keys.Has(key) && keys[key]
}

Check(ok, message) {
    if !ok
        throw Error(message)
}
'''


def main():
    if os.name != "nt":
        raise SystemExit("Requires Windows and AutoHotkey v2.")
    ahk = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ["ProgramFiles"]) / "AutoHotkey/v2/AutoHotkey64.exe"
    if not ahk.is_file():
        raise SystemExit(f"AutoHotkey v2 not found: {ahk}")
    frontend = Path(__file__).resolve().parents[1] / "frontend/SkyrimVR Devkit.ahk"
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    user32.CreateDesktopW.restype = ctypes.c_void_p
    user32.CloseDesktop.argtypes = [ctypes.c_void_p]
    with tempfile.TemporaryDirectory(prefix="vrdevkit-shortcut-") as temp:
        name = Path(temp).name
        desktop = user32.CreateDesktopW(name, None, None, 0, 0xFF, None)
        if not desktop:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            (Path(temp) / "icons").mkdir()
            for icon in ("MM-OFF.png", "MM-ON.png"):
                shutil.copyfile(frontend.parent / "icons" / icon, Path(temp) / "icons" / icon)
            script = Path(temp) / "check.ahk"
            script.write_text(CHECK.replace("FRONTEND_PATH", str(frontend)), encoding="utf-8")
            startup = subprocess.STARTUPINFO()
            startup.lpDesktop = "WinSta0\\" + name  # Never switch the input desktop.
            result = subprocess.run([str(ahk), "/ErrorStdOut", str(script)], startupinfo=startup,
                                    capture_output=True, text=True, timeout=20)
            print(result.stdout, end="")
            print(result.stderr, end="", file=sys.stderr)
            return result.returncode
        finally:
            user32.CloseDesktop(desktop)


if __name__ == "__main__":
    raise SystemExit(main())
