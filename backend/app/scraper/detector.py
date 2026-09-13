"""
PowerPoint File Detector & Validator.
Validates Content-Type headers, magic bytes, and OOXML structures to confirm PowerPoint files.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path


# Known PowerPoint MIME types
PPT_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.presentationml.template",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
    "application/vnd.ms-powerpoint",
    "application/powerpoint",
    "application/x-mspowerpoint",
    "application/x-powerpoint",
    "application/ppt",
    "application/pptx",
}

# Magic bytes
ZIP_MAGIC = b"PK\x03\x04"  # Standard OOXML .pptx magic bytes
OLE_MAGIC = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"  # Legacy .ppt binary format


def is_powerpoint_content(content: bytes) -> tuple[bool, str]:
    """
    Check if the given binary content is a valid PowerPoint presentation.
    Returns (is_valid, format_type) e.g. (True, "pptx") or (False, "").
    """
    if len(content) < 512:
        return False, ""

    # Check OOXML .pptx
    if content.startswith(ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                namelist = zf.namelist()
                # A valid PPTX archive contains [Content_Types].xml and presentation.xml or ppt/ directory
                has_content_types = "[Content_Types].xml" in namelist
                has_ppt_dir = any(name.startswith("ppt/") for name in namelist)
                if has_content_types and has_ppt_dir:
                    return True, "pptx"
                
                # Check for presentation XML content types
                if has_content_types:
                    try:
                        ct_xml = zf.read("[Content_Types].xml").decode("utf-8", errors="ignore")
                        if "presentationml" in ct_xml or "powerpoint" in ct_xml:
                            return True, "pptx"
                    except Exception:
                        pass
        except Exception:
            pass

    # Check legacy binary .ppt
    if content.startswith(OLE_MAGIC):
        return True, "ppt"

    return False, ""


def is_powerpoint_url_or_header(url: str, content_type_header: str = "") -> bool:
    """
    Heuristic check based on URL extension and Content-Type header.
    """
    url_lower = url.lower().split("?")[0]
    if url_lower.endswith((".pptx", ".ppt", ".potx", ".ppsx")):
        return True

    if content_type_header:
        ct_clean = content_type_header.split(";")[0].strip().lower()
        if ct_clean in PPT_MIME_TYPES or "presentation" in ct_clean or "powerpoint" in ct_clean:
            return True

    return False
