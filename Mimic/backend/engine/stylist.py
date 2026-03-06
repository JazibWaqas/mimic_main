"""
Stylist: Applies visual aesthetics and text overlays to videos.
This module translates StyleBlueprints into FFmpeg filter chains.
"""

from pathlib import Path
import subprocess
from typing import Dict, Any, List
from models import StyleConfig

def apply_visual_styling(
    input_video: str,
    output_video: str,
    text_overlay: str,
    text_style: Dict[str, Any],
    color_grading: Dict[str, Any] = None,
    text_events: List[Any] = None, # v12.2 Support for timed text
    style_config: StyleConfig = None # v14.9 Style Control (Post-Editor Layer)
) -> None:
    """
    Apply visual styling and text overlay to a video using FFmpeg.
    Supports both legacy global overlay and v14.9 StyleConfig.
    """
    
    # If a v14.9 style_config is provided, it OVERRIDES legacy color_grading/text_style dicts
    # However, text_overlay and text_events (the CONTENT) still come from the blueprint/AI.
    
    has_timed_events = bool(text_events and len(text_events) > 0)
    has_global_text = bool(text_overlay and text_overlay.strip())
    
    # Priority Gate: If timed events exist, they OVERRIDE global static text.
    if has_timed_events:
        has_global_text = False
    
    # 1. Map Style Configuration
    # Use v14.9 StyleConfig if provided, otherwise fallback to legacy
    if style_config:
        # Map v14.9 Config
        current_font = style_config.text.font.lower()
        current_weight = style_config.text.weight
        current_font_color = style_config.text.color
        current_shadow = style_config.text.shadow
        current_placement = style_config.text.position
        current_animation = style_config.text.animation
        
        color_preset = style_config.color.preset
        grain = style_config.texture.grain
    else:
        # Fallback to Legacy Dicts
        current_font = text_style.get("font_style", "arial").lower()
        current_weight = 600
        current_font_color = "white"
        current_shadow = True
        current_placement = text_style.get("placement", "center").lower()
        current_animation = "fade"
        
        # Color Grading Legacy
        legacy_tone = (color_grading or {}).get("tone", "").lower()
        legacy_contrast = (color_grading or {}).get("contrast", "").lower()
        if "warm" in legacy_tone: color_preset = "warm"
        elif "cool" in legacy_tone: color_preset = "cool"
        elif "high" in legacy_contrast: color_preset = "high_contrast"
        else: color_preset = "neutral"
        grain = False

    # 2. Map Font Selection (Windows Path Resolution)
    font_map = {
        "inter": "inter.ttf",
        "roboto": "roboto.ttf",
        "outfit": "outfit.ttf",
        "serif": "georgia.ttf",
        "sans-serif": "arial.ttf",
        "mono": "consola.ttf",
    }
    
    font_file = font_map.get(current_font, "arial.ttf")
    # v14.9: If font doesn't exist in C:/Windows/Fonts, try local project fonts if any
    font_path = Path("C:/Windows/Fonts") / font_file
    if not font_path.exists():
        # Fallback to Arial if specific brand font isn't on the system
        font_path = Path("C:/Windows/Fonts") / "arial.ttf"
    
    # Pre-calculate string for f-strings (Python 3.10 compat: no backslashes in expression parts)
    font_path_str = str(font_path).replace("\\", "/")

    # 3. Build Filter Chain
    filters = []
    
    # A. Color Grading (Post-Editor Presets)
    if color_preset == "warm":
        # Warm: sepia + saturation boost + brightness
        filters.append("eq=saturation=1.1:brightness=0.02")
        filters.append("colorbalance=rh=0.08:gh=0.04:bh=-0.04") # Traditional warm
    elif color_preset == "cool":
        # Cool: blue tint
        filters.append("eq=saturation=0.9:brightness=-0.02")
        filters.append("colorbalance=rh=-0.04:gh=0.01:bh=0.08")
    elif color_preset == "high_contrast":
        # High Contrast
        filters.append("eq=contrast=1.2:saturation=1.15")
    elif color_preset == "vintage":
        # Vintage: Desaturated + Sepia
        filters.append("eq=saturation=0.7:contrast=0.9")
        filters.append("colorbalance=rh=0.1:gh=0.05:bh=-0.05")
        grain = True # Force grain for vintage

    # B. Film Grain (If enabled)
    if grain:
        # Very subtle film grain
        filters.append("noise=alls=7:allf=t+u")

    # C. Text Overlays
    shadow_opt = f":shadowcolor=black@0.6:shadowx=2:shadowy=2" if current_shadow else ""
    
    # C1. Legacy Global Text
    if has_global_text:
        import textwrap
        raw_lines = text_overlay.replace("|", "\n").split("\n")
        lines = []
        for line in raw_lines:
            if len(line.strip()) > 35:
                lines.extend(textwrap.wrap(line.strip(), width=35))
            else:
                if line.strip(): lines.append(line.strip())
        
        font_size = 42
        line_height = font_size * 1.5
        
        if "top" in current_placement:
            base_y_expr = "h/5"
        elif "bottom" in current_placement:
            base_y_expr = f"h*0.8 - ({len(lines)} * {line_height}/2)"
        else:
            base_y_expr = f"(h - ({len(lines)} * {line_height}))/2"
            
        for i, line in enumerate(lines):
            clean_l = _sanitize_text_for_ffmpeg(line)
            y_offset = f"({base_y_expr}) + {i * line_height}"
            
            # Escape color for FFmpeg (needs to be 0xRRGGBB or name)
            draw_color = current_font_color.replace("#", "0x") if current_font_color.startswith("#") else current_font_color
            
            drawtext = (
                f"drawtext=text='{clean_l}':"
                f"x=(w-text_w)/2:y={y_offset}:"
                f"fontsize={font_size}:fontcolor={draw_color}:"
                f"fontfile='{font_path_str}'"
                f"{shadow_opt}"
            )
            filters.append(drawtext)

    # C2. v12.2 Timed Text Events
    if has_timed_events:
        for evt in text_events:
            content = getattr(evt, 'content', evt.get('content') if isinstance(evt, dict) else str(evt))
            start_t = getattr(evt, 'start', evt.get('start', 0) if isinstance(evt, dict) else 0)
            end_t = getattr(evt, 'end', evt.get('end', 5) if isinstance(evt, dict) else 5)
            role = getattr(evt, 'role', evt.get('role', 'Decorative') if isinstance(evt, dict) else "").lower()
            
            clean_content = _sanitize_text_for_ffmpeg(content)
            evt_font_size = 64 if "anchor" in role else 48
            
            # Role-based placement
            if "anchor" in role:
                x_pos = "(w-text_w)/2"
                y_pos = "(h-text_h)/2" 
            elif "emphasis" in role:
                x_pos = "(w-text_w)/2"
                y_pos = "(h-text_h)/3"
            else:
                x_pos = "(w-text_w)/2"
                y_pos = "h-(h/5)"
            
            draw_color = current_font_color.replace("#", "0x") if current_font_color.startswith("#") else current_font_color
            
            drawtext = (
                f"drawtext=text='{clean_content}':"
                f"enable='between(t,{start_t},{end_t})':"
                f"x={x_pos}:y={y_pos}:"
                f"fontsize={evt_font_size}:fontcolor={draw_color}:"
                f"fontfile='{font_path_str}'"
                f"{shadow_opt}"
            )
            filters.append(drawtext)
    
    # 4. FFmpeg Execution
    if not filters:
        import shutil
        shutil.copy2(input_video, output_video)
        return
        
    filter_chain = ",".join(filters)
    
    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", filter_chain,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-c:a", "copy",
        output_video
    ]
    
    print(f"  [STYLIST] Applying v14.9 Style (Preset: {color_preset}): {len(filters)} filters")
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        print(f"  [OK] Stylized video ready: {Path(output_video).name}")
    except Exception as e:
        print(f"  [WARN] Stylist failed (likely FFmpeg syntax/missing font), falling back to unstylized: {e}")
        import shutil
        shutil.copy2(input_video, output_video)

def _sanitize_text_for_ffmpeg(text: str) -> str:
    """Helper to strip dangerous characters for Windows FFmpeg."""
    clean = text.replace(":", "").replace(",", "").replace("'", "").replace('"', "").replace("\\", "")
    return "".join(c for c in clean if c.isalnum() or c in " .!?#@%&*()-_=+[]{}|;~")
