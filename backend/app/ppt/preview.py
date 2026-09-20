"""
PowerPoint Slide Preview Thumbnail Generator.
Generates native, high-resolution PNG slide previews using Microsoft PowerPoint COM automation on Windows.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Thread lock to serialize COM calls across parallel scrape workers
_com_lock = threading.Lock()
_registration_done = False


def _find_powerpoint_exe() -> str | None:
    """Finds the local PowerPoint executable path on Windows."""
    candidates = [
        r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"C:\Program Files\Microsoft Office\Office16\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office16\POWERPNT.EXE",
        r"C:\Program Files\Microsoft Office\Office15\POWERPNT.EXE",
        r"C:\Program Files (x86)\Microsoft Office\Office15\POWERPNT.EXE",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c

    # Also check ClickToRun registry configuration
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Office\ClickToRun\Configuration",
        ) as k:
            install_path, _ = winreg.QueryValueEx(k, "ClientFolder")
            # Usually C:\Program Files\Common Files\Microsoft Shared\ClickToRun
            # Check adjacent root/Office16
            parent = Path(install_path).parents[2]
            for sub in ["root/Office16/POWERPNT.EXE", "Office16/POWERPNT.EXE"]:
                candidate = parent / sub
                if candidate.is_file():
                    return str(candidate)
    except Exception:
        pass

    return None


def _ensure_powerpoint_registered() -> None:
    """
    Ensures PowerPoint.Application COM ProgID and LocalServer32 are registered
    under HKCU so that 64-bit Python can dispatch 32-bit/64-bit ClickToRun PowerPoint.
    """
    global _registration_done
    if _registration_done or sys.platform != "win32":
        return

    try:
        import winreg

        ppt_exe = _find_powerpoint_exe()
        if not ppt_exe:
            return

        clsid = "{91493441-5A91-11CF-8700-00AA0060263B}"
        cmd_str = f'"{ppt_exe}" /AUTOMATION'

        keys_to_set = [
            (r"Software\Classes\PowerPoint.Application", "Microsoft PowerPoint Presentation"),
            (r"Software\Classes\PowerPoint.Application\CLSID", clsid),
            (r"Software\Classes\PowerPoint.Application\CurVer", "PowerPoint.Application.16"),
            (r"Software\Classes\PowerPoint.Application.16", "Microsoft PowerPoint Presentation"),
            (r"Software\Classes\PowerPoint.Application.16\CLSID", clsid),
            (f"Software\\Classes\\CLSID\\{clsid}", "Microsoft PowerPoint Application"),
            (f"Software\\Classes\\CLSID\\{clsid}\\LocalServer32", cmd_str),
            (f"Software\\Classes\\CLSID\\{clsid}\\ProgID", "PowerPoint.Application.16"),
            (f"Software\\Classes\\CLSID\\{clsid}\\VersionIndependentProgID", "PowerPoint.Application"),
            (f"Software\\Classes\\Wow6432Node\\CLSID\\{clsid}\\LocalServer32", cmd_str),
            (f"Software\\Classes\\Wow6432Node\\CLSID\\{clsid}\\ProgID", "PowerPoint.Application.16"),
        ]

        for subkey, val in keys_to_set:
            try:
                k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, subkey)
                winreg.SetValue(k, "", winreg.REG_SZ, val)
                winreg.CloseKey(k)
            except Exception:
                pass

        _registration_done = True
    except Exception:
        pass


def _get_powerpoint_com_app():
    """
    Acquires a PowerPoint COM application instance.
    Tries GetActiveObject, then Dispatch, and falls back to launching /AUTOMATION.
    """
    import win32com.client

    # 1. Try connecting to already running instance
    try:
        return win32com.client.GetActiveObject("PowerPoint.Application")
    except Exception:
        pass

    # 2. Try dispatching via registered COM class
    try:
        return win32com.client.Dispatch("PowerPoint.Application")
    except Exception:
        pass

    # 3. If dispatch fails (e.g. strict ClickToRun sandbox), launch with /AUTOMATION
    ppt_exe = _find_powerpoint_exe()
    if ppt_exe and Path(ppt_exe).is_file():
        subprocess.Popen([ppt_exe, "/AUTOMATION"])
        # Poll for registration in Running Object Table (up to 8 seconds)
        for _ in range(16):
            time.sleep(0.5)
            try:
                return win32com.client.GetActiveObject("PowerPoint.Application")
            except Exception:
                pass

    # If still not found, retry Dispatch once more to get the exact COM error
    return win32com.client.Dispatch("PowerPoint.Application")


def render_slide_preview(pptx_path: Path | str, slide_index: int, output_png_path: Path | str) -> Path:
    """
    Renders a native preview PNG image of a specific slide in a PPTX file using PowerPoint COM.
    No fallback to PIL is performed - fails explicitly if PowerPoint COM cannot render.
    """
    pptx_path = Path(pptx_path).resolve()
    output_png_path = Path(output_png_path).resolve()
    output_png_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        raise RuntimeError(f"PowerPoint COM preview requires Windows. Current platform: {sys.platform}")

    try:
        import pythoncom
    except ImportError as e:
        raise RuntimeError(f"PowerPoint COM preview requires pywin32: {e}")

    _ensure_powerpoint_registered()

    abs_pptx_path = str(pptx_path)
    abs_output_path = str(output_png_path)

    # Acquire lock so only one thread executes PowerPoint COM actions at a time
    with _com_lock:
        pythoncom.CoInitialize()
        presentation = None
        try:
            ppt_app = _get_powerpoint_com_app()
            # Open read-only, untitled=False, with_window=False
            presentation = ppt_app.Presentations.Open(abs_pptx_path, True, False, False)

            # PowerPoint slide index is 1-based in COM
            com_slide_idx = slide_index + 1
            if not (1 <= com_slide_idx <= presentation.Slides.Count):
                raise ValueError(
                    f"Slide index {com_slide_idx} out of range (total slides: {presentation.Slides.Count})"
                )

            slide = presentation.Slides(com_slide_idx)
            slide.Export(abs_output_path, "PNG", 1280, 720)

            if not output_png_path.exists() or output_png_path.stat().st_size == 0:
                raise RuntimeError(f"PowerPoint COM export completed but no PNG was generated at {output_png_path}")

            print(f"[PowerPoint COM] Successfully exported slide {com_slide_idx} -> {output_png_path.name} ({output_png_path.stat().st_size} bytes)")
            return output_png_path

        except Exception as err:
            raise RuntimeError(f"PowerPoint COM preview generation failed: {err}") from err
        finally:
            if presentation is not None:
                try:
                    presentation.Close()
                except Exception:
                    pass
            pythoncom.CoUninitialize()
