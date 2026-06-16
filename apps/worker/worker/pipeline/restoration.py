"""Image restoration: terrible phone photo -> clean, OCR-ready page.

Pipeline: downscale -> detect the page (bright-paper mask, Canny fallback) ->
perspective warp + crop -> inset the physical edge -> illumination flatten ->
deskew -> adaptive-threshold binarize (crisp black text on white).

The old pipeline only ran when a document contour was found; when it wasn't, the
whole frame (desk and all) went through shadow-removal + CLAHE, which manufactured
"pencil-sketch" edge noise and never sharpened the text. The page detector below
is brightness-based (paper is brighter than the surface it sits on), so it crops
real photos that Canny edges miss — and binarization is what actually makes the
letters look *better* than the original, not just greyscaled.

All steps are defensive: if a step can't find what it needs it degrades to the
previous image rather than failing the job.
"""

from __future__ import annotations

import cv2
import numpy as np


def _resize_max(img: np.ndarray, max_side: int = 3500) -> np.ndarray:
    # 3500 (not 2200) so the cropped page keeps ~270+ DPI — at 2200 small text
    # came out only ~170 DPI and binarization turned it jagged/"pixelated".
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img


def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left
    rect[2] = pts[np.argmax(s)]  # bottom-right
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right
    rect[3] = pts[np.argmax(diff)]  # bottom-left
    return rect


def _page_quad_bright(img: np.ndarray, min_area: float = 0.15) -> np.ndarray | None:
    """Find the page as the largest desaturated-bright region (white paper vs. a
    coloured surface like a wooden desk), then its 4 corners.

    Saturation is the key discriminator: a brightness-only mask let specular wood
    highlights bridge into the page and drag the crop onto the desk. Paper is
    desaturated (low S) even where the desk is bright, so an (high V & low S) mask
    isolates it cleanly. Internal holes (dark photos/maps printed on the page) are
    filled so the page stays one blob, then the page's 4 extreme corners (min/max
    of x±y) drive a true perspective crop — robust to however many vertices the
    contour has.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    _, sat, val = cv2.split(hsv)
    mask = (((val > 110) & (sat < 70)) * 255).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count <= 1:
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))  # largest non-background
    area = img.shape[0] * img.shape[1]
    if stats[idx, cv2.CC_STAT_AREA] < min_area * area:
        return None
    comp = np.where(labels == idx, 255, 0).astype(np.uint8)
    comp = cv2.morphologyEx(comp, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))  # fill dark-image holes

    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pts = max(contours, key=cv2.contourArea).reshape(-1, 2).astype("float32")
    ssum, sdiff = pts.sum(axis=1), pts[:, 1] - pts[:, 0]
    return np.array(
        [pts[np.argmin(ssum)], pts[np.argmin(sdiff)], pts[np.argmax(ssum)], pts[np.argmax(sdiff)]],
        dtype="float32",
    )


def _page_quad_canny(gray: np.ndarray) -> np.ndarray | None:
    """Edge-based page detection — fallback for low brightness contrast."""
    edged = cv2.Canny(gray, 75, 200)
    edged = cv2.dilate(edged, np.ones((5, 5), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    area = gray.shape[0] * gray.shape[1]
    for c in contours:
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.contourArea(approx) > 0.25 * area:
            return approx.reshape(4, 2).astype("float32")
    return None


def _detect_page(img: np.ndarray) -> np.ndarray | None:
    quad = _page_quad_bright(img)
    if quad is None:
        quad = _page_quad_canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    return quad


def _four_point_warp(img: np.ndarray, quad: np.ndarray) -> np.ndarray:
    rect = _order_points(quad)
    (tl, tr, br, bl) = rect
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if width < 10 or height < 10:
        return img
    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(img, matrix, (width, height))


def _inset(img: np.ndarray, frac: float = 0.018) -> np.ndarray:
    """Shave the physical page edge / shadow line (and any thin desk sliver the
    quad overshot) left by the warp."""
    h, w = img.shape[:2]
    dy, dx = int(h * frac), int(w * frac)
    if h - 2 * dy < 10 or w - 2 * dx < 10:
        return img
    return img[dy : h - dy, dx : w - dx]


def _estimate_skew(gray: np.ndarray, search: float = 12.0, step: float = 0.5) -> float:
    """Find the rotation that best aligns text rows, via projection-profile search.

    Robust across OpenCV versions (no reliance on minAreaRect's angle convention):
    the correcting angle is the one whose horizontal projection has the sharpest
    row-to-row transitions (text lines stacked = high variance).
    """
    scale = 800 / gray.shape[1] if gray.shape[1] > 800 else 1.0
    small = cv2.resize(gray, (0, 0), fx=scale, fy=scale) if scale != 1.0 else gray
    binary = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = binary.shape[:2]
    center = (w / 2, h / 2)

    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-search, search + 1e-6, step):
        matrix = cv2.getRotationMatrix2D(center, float(angle), 1.0)
        rotated = cv2.warpAffine(binary, matrix, (w, h), flags=cv2.INTER_NEAREST)
        projection = rotated.sum(axis=1, dtype=np.float64)
        score = float(np.square(np.diff(projection)).sum())
        if score > best_score:
            best_score, best_angle = score, float(angle)
    return best_angle


def _rotate(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotate to correct residual skew (works on colour or greyscale)."""
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = (255, 255, 255) if img.ndim == 3 else 255
    return cv2.warpAffine(
        img, matrix, (w, h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=border,
    )


def _grayscale_enhance(gray: np.ndarray) -> np.ndarray:
    """Smooth, anti-aliased cleanup: flatten illumination, boost local contrast,
    sharpen. Keeps greyscale so it never pixelates — the safe mode for faint
    handwriting, photos, stamps, or anything binarization would shred.
    """
    background = cv2.medianBlur(cv2.dilate(gray, np.ones((9, 9), np.uint8)), 31)
    norm = cv2.divide(gray, background, scale=255)
    # edge-preserving denoise FIRST: kills paper grain + halftone/print dot noise
    # (which CLAHE+unsharp would otherwise amplify) while keeping text/line edges.
    norm = cv2.bilateralFilter(norm, 5, 50, 50)
    norm = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8)).apply(norm)
    blur = cv2.GaussianBlur(norm, (0, 0), 1.5)
    sharp = cv2.addWeighted(norm, 1.4, blur, -0.4, 0)  # gentle sharpen, less noise gain
    sharp[sharp > 240] = 255  # clean white background, keep edge anti-aliasing
    return sharp


def _color_enhance(bgr: np.ndarray) -> np.ndarray:
    """Colour cleanup that keeps the document's real colours — stamps, signatures,
    photos, logos. Flattens illumination per channel so the paper goes clean white
    while coloured ink keeps its hue, denoises, sharpens, and lifts saturation a
    little so faded stamps/ink read clearly. The most faithful "looks like the
    original" output.
    """
    channels = []
    for c in cv2.split(bgr):
        background = cv2.medianBlur(cv2.dilate(c, np.ones((9, 9), np.uint8)), 31)
        channels.append(cv2.divide(c, background, scale=255))
    out = cv2.merge(channels)
    out = cv2.bilateralFilter(out, 5, 50, 50)  # edge-preserving denoise
    # white-balance: lift the paper white-point so a uniformly grey/dim scan goes
    # white (the per-channel divide alone can leave a grey cast on flat scans).
    luma = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    wp = float(np.percentile(luma, 80))
    if wp > 1:
        out = np.clip(out.astype(np.float32) * (250.0 / wp), 0, 255).astype(np.uint8)
    blur = cv2.GaussianBlur(out, (0, 0), 1.5)
    out = cv2.addWeighted(out, 1.3, blur, -0.3, 0)  # gentle sharpen
    # lift saturation so colour content (stamps/signatures) stays vivid
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.25, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    # snap near-white paper to pure white; coloured/dark content is untouched
    luma = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    out[luma > 235] = 255
    return out


def _clean_border_bands(bgr: np.ndarray, lo: int = 190, hi: int = 243,
                        min_area: float = 0.004) -> np.ndarray:
    """Whiten neutral grey background bands/wedges that the crop included and that
    touch a border. Restricted to low-saturation (neutral) blobs, so coloured
    content — stamps, signatures, photos — is never touched.
    """
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sat = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)[..., 1]
    band = (((gray >= lo) & (gray < hi) & (sat < 40)) * 255).astype(np.uint8)
    band = cv2.morphologyEx(band, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(band, 8)
    out = bgr.copy()
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if area < min_area * h * w:
            continue
        if x <= 2 or y <= 2 or x + bw >= w - 2 or y + bh >= h - 2:  # touches a border
            out[labels == i] = 255
    return out


def _binarize(gray: np.ndarray) -> np.ndarray:
    """Even out lighting, sharpen strokes, then adaptive-threshold to crisp B/W.

    Falls back to the smooth greyscale enhance if thresholding goes degenerate
    (mostly black or text washed out) — e.g. faint pencil or photos.
    """
    background = cv2.medianBlur(cv2.dilate(gray, np.ones((9, 9), np.uint8)), 31)
    norm = cv2.divide(gray, background, scale=255)

    blur = cv2.GaussianBlur(norm, (0, 0), 3)
    sharp = cv2.addWeighted(norm, 1.5, blur, -0.5, 0)

    binar = cv2.adaptiveThreshold(
        sharp, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    binar = cv2.medianBlur(binar, 3)  # despeckle

    white = float((binar == 255).mean())
    if white < 0.55 or white > 0.999:
        return _grayscale_enhance(gray)
    return binar


def _whiten_border(img: np.ndarray, frac: float = 0.01) -> np.ndarray:
    h, w = img.shape[:2]
    dy, dx = max(1, int(h * frac)), max(1, int(w * frac))
    out = img.copy()
    out[:dy, :] = 255
    out[h - dy :, :] = 255
    out[:, :dx] = 255
    out[:, w - dx :] = 255
    return out


def restore(image_bytes: bytes, max_side: int = 3500, mode: str = "color") -> bytes:
    """Restore a photo of a document. Returns PNG bytes of the cleaned page.

    max_side: working-resolution cap (higher = crisper small text, larger files).
    mode:
      "color"  – keep the document's real colours (stamps, signatures, photos,
                 logos) with the paper flattened to white. Most faithful to the
                 original source. (default)
      "gray"   – smooth greyscale.
      "binary" – crisp 1-bit B/W (best for pure-text pages only).
    """
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image")

    img = _resize_max(img, max_side)

    quad = _detect_page(img)
    if quad is not None:
        img = _inset(_four_point_warp(img, quad))

    angle = _estimate_skew(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    if abs(angle) >= 0.3:
        img = _rotate(img, angle)

    if mode == "binary":
        cleaned = _binarize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    elif mode == "gray":
        cleaned = _grayscale_enhance(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    else:  # color
        cleaned = _clean_border_bands(_color_enhance(img))
    out = _whiten_border(cleaned)

    ok, buf = cv2.imencode(".png", out)
    if not ok:
        raise ValueError("could not encode restored image")
    return buf.tobytes()
