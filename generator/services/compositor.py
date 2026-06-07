"""Composite a talking-head video as a circular "facecam" over a background video.

Uses ffmpeg: the background is looped to the facecam's length, the facecam is
cropped to a circle (with a colored ring), scaled, and overlaid. The output uses
the facecam's audio (the narration) so the full message is preserved.

Placement is either a preset corner (`position`) or explicit pixel coordinates
(`x`, `y` top-left + `diameter`) in the background video's own pixel space.
"""

import subprocess

from django.conf import settings


class CompositeError(RuntimeError):
    pass


# overlay x:y expressions by preset position (W/H = main, w/h = overlay)
_POSITIONS = {
    "bottom-left": "{m}:H-h-{m}",
    "bottom-center": "(W-w)/2:H-h-{m}",
    "bottom-right": "W-w-{m}:H-h-{m}",
}


def _hex_to_rgb(value):
    """'#rrggbb' -> (r, g, b); returns None on bad input."""
    value = (value or "").lstrip("#")
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _kf_expr(keyframes, key):
    """Step (hold-then-jump) ffmpeg expression over `t` for a keyframe coordinate.

    The facecam stays at each keyframe's value until the next keyframe's time,
    then cuts to it — no sliding between positions. keyframes: list of dicts
    with 't' and the given key (e.g. 'x').
    """
    pts = sorted(
        ((float(k["t"]), float(k[key])) for k in keyframes), key=lambda p: p[0]
    )
    if len(pts) == 1:
        return f"{pts[0][1]:.2f}"
    expr = f"{pts[-1][1]:.2f}"  # t >= last keyframe
    for i in range(len(pts) - 2, -1, -1):
        t1 = pts[i + 1][0]
        v_i = pts[i][1]
        expr = f"if(lt(t,{t1:.2f}),{v_i:.2f},{expr})"
    return expr


def overlay_circle(
    bg_path,
    face_path,
    out_path,
    position="bottom-left",
    x=None,
    y=None,
    diameter=None,
    border=None,
    border_color=None,
    keyframes=None,
):
    """Overlay face_path as a circular bubble on bg_path -> out_path (mp4)."""
    m = settings.COMPOSITE_MARGIN
    b = settings.COMPOSITE_BORDER if border is None else max(int(border), 0)
    rgb = _hex_to_rgb(border_color)
    if rgb is None:
        try:
            rgb = tuple(int(c) for c in settings.COMPOSITE_BORDER_RGB.split(","))
        except ValueError:
            rgb = (255, 255, 255)
    br, bgc, bb = rgb

    d = diameter or settings.COMPOSITE_DIAMETER
    r_out = d / 2
    r_in = max(r_out - b, 0)

    if keyframes:
        # Animated placement: x/y are time expressions, so they must be quoted
        # (they contain commas) inside the filtergraph.
        xy = f"x='{_kf_expr(keyframes, 'x')}':y='{_kf_expr(keyframes, 'y')}'"
    elif x is not None and y is not None:
        xy = f"{int(x)}:{int(y)}"
    else:
        xy = _POSITIONS.get(position, _POSITIONS["bottom-left"]).format(m=m)

    # rgba so all planes are full-res: keep pixels inside r_in, paint the ring
    # between r_in and r_out the border color, and cut alpha outside r_out.
    def _chan(fn, border_val):
        return (
            f"{fn}='if(lte(hypot(X-{d}/2,Y-{d}/2),{r_in}),{fn}(X,Y),{border_val})'"
        )

    filtergraph = (
        f"[1:v]scale={d}:{d},format=rgba,geq="
        f"{_chan('r', br)}:{_chan('g', bgc)}:{_chan('b', bb)}:"
        f"a='if(lte(hypot(X-{d}/2,Y-{d}/2),{r_out}),255,0)'[fc];"
        f"[0:v][fc]overlay={xy}:shortest=1[v]"
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop",
        "-1",
        "-i",
        bg_path,
        "-i",
        face_path,
        "-filter_complex",
        filtergraph,
        "-map",
        "[v]",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        out_path,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-5:]
        raise CompositeError("ffmpeg overlay failed: " + " | ".join(tail))
    return out_path
