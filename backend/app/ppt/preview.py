"""
PowerPoint Slide Preview Thumbnail Generator.
Generates high-resolution PNG previews using PowerPoint COM automation on Windows,
with a robust PIL-based graphical fallback for non-Windows or headless systems.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pptx
from pptx.util import Inches, Pt


def render_slide_preview(pptx_path: Path | str, slide_index: int, output_png_path: Path | str) -> Path:
    """
    Renders a preview PNG image of a specific slide in a PPTX file.
    Uses PowerPoint COM if available on Windows, otherwise uses PIL fallback.
    """
    pptx_path = Path(pptx_path).resolve()
    output_png_path = Path(output_png_path).resolve()
    output_png_path.parent.mkdir(parents=True, exist_ok=True)

    # Attempt COM rendering on Windows
    if sys.platform == "win32":
        try:
            import win32com.client
            import pythoncom

            pythoncom.CoInitialize()
            try:
                # Use dynamic dispatch for better compatibility
                ppt_app = win32com.client.dynamic.Dispatch("PowerPoint.Application")
                # Make PowerPoint visible for debugging
                ppt_app.Visible = True
                # Use absolute paths and ensure they exist
                abs_pptx_path = str(pptx_path.absolute())
                abs_output_path = str(output_png_path.absolute())
                # Try opening with minimal parameters
                presentation = ppt_app.Presentations.Open(abs_pptx_path)
                try:
                    # PowerPoint slide index is 1-based in COM
                    com_slide_idx = slide_index + 1
                    if 1 <= com_slide_idx <= presentation.Slides.Count:
                        slide = presentation.Slides(com_slide_idx)
                        slide.Export(abs_output_path, "PNG")
                        if output_png_path.exists() and output_png_path.stat().st_size > 0:
                            return output_png_path
                finally:
                    presentation.Close()
                    ppt_app.Visible = False
            finally:
                pythoncom.CoUninitialize()
        except Exception as com_err:
            # Fall back to PIL renderer
            print(f"PowerPoint COM rendering failed: {com_err}")
            pass

    # PIL Fallback Renderer
    return _render_pil_fallback(pptx_path, slide_index, output_png_path)


def _render_pil_fallback(pptx_path: Path, slide_index: int, output_png_path: Path) -> Path:
    """
    Renders a clean card representation of the slide using PIL.
    """
    width, height = 1280, 720
    img = Image.new("RGB", (width, height), color=(248, 250, 252))  # Slate-50 background
    draw = ImageDraw.Draw(img)

    # Decorative top bar
    draw.rectangle([(0, 0), (width, 8)], fill=(6, 114, 203))  # Brand accent

    title_text = f"Slide {slide_index + 1}"
    body_texts: list[str] = []
    shape_count = 0
    has_chart = False
    has_image = False

    try:
        prs = pptx.Presentation(str(pptx_path))
        if slide_index < len(prs.slides):
            slide = prs.slides[slide_index]
            shape_count = len(slide.shapes)
            for shape in slide.shapes:
                # Check for different shape types
                if hasattr(shape, 'shape_type'):
                    if shape.shape_type == 3:  # Chart
                        has_chart = True
                    elif shape.shape_type == 13:  # Picture
                        has_image = True
                
                # Extract text content
                try:
                    if hasattr(shape, 'has_text_frame') and shape.has_text_frame:
                        text = shape.text_frame.text.strip()
                        if text:
                            if not title_text or title_text == f"Slide {slide_index + 1}":
                                title_text = text.split("\n")[0][:80]
                            else:
                                for line in text.split("\n"):
                                    if line.strip() and len(body_texts) < 8:
                                        body_texts.append(line.strip()[:100])
                except Exception:
                    pass
    except Exception as e:
        print(f"Error extracting slide content: {e}")
        pass

    # Try to load a font, or use default
    font_title = None
    font_body = None
    font_meta = None
    try:
        # Check standard Windows fonts
        for font_name in ["segoeui.ttf", "arial.ttf", "calibri.ttf"]:
            font_path = Path("C:/Windows/Fonts") / font_name
            if font_path.exists():
                font_title = ImageFont.truetype(str(font_path), 36)
                font_body = ImageFont.truetype(str(font_path), 22)
                font_meta = ImageFont.truetype(str(font_path), 18)
                break
    except Exception:
        pass

    if not font_title:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_meta = ImageFont.load_default()

    # Draw Card Content Box
    draw.rounded_rectangle(
        [(60, 50), (width - 60, height - 60)],
        radius=16,
        fill=(255, 255, 255),
        outline=(226, 232, 240),
        width=2,
    )

    # Header section
    draw.text((100, 90), title_text, fill=(30, 41, 59), font=font_title)
    draw.line([(100, 150), (width - 100, 150)], fill=(241, 245, 249), width=2)

    # Content section
    y_pos = 180
    for line in body_texts:
        draw.text((120, y_pos), f"•  {line}", fill=(71, 85, 105), font=font_body)
        y_pos += 45

    # Add visual indicators for charts/images
    if has_chart:
        draw.text((120, y_pos + 10), "📊 Contains Chart/Data", fill=(6, 114, 203), font=font_body)
        y_pos += 45
    if has_image:
        draw.text((120, y_pos + 10), "🖼️ Contains Image", fill=(6, 114, 203), font=font_body)
        y_pos += 45

    # Footer Metadata
    meta_parts = [f"PowerPoint Slide #{slide_index + 1}", f"{shape_count} Elements"]
    if has_chart:
        meta_parts.append("Chart")
    if has_image:
        meta_parts.append("Image")
    meta_text = "  •  ".join(meta_parts)
    draw.text((100, height - 110), meta_text, fill=(148, 163, 184), font=font_meta)

    img.save(str(output_png_path), "PNG", quality=95)
    return output_png_path
