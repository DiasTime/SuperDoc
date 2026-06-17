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


def _page_quad_bright(
    img: np.ndarray, min_area: float = 0.15
) -> tuple[np.ndarray, np.ndarray] | None:
    """Find the page as the largest desaturated-bright region (white paper vs. a
    coloured surface like a wooden desk), then its 4 corners.

    Returns ``(quad, mask)`` where ``mask`` is the filled page region — the warp
    uses it to whiten anything that isn't the real page (e.g. a desk wedge pulled
    in when an off-frame corner is extrapolated).

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
    # Fill internal holes (dark photos/maps printed on the page) by flood-filling
    # the background from a corner and OR-ing back the enclosed holes. Unlike a big
    # MORPH_CLOSE, this never bulges the outer page boundary into the desk — so the
    # detected edges hug the real page and the perspective corners stay accurate.
    h, w = comp.shape
    flood = comp.copy()
    cv2.floodFill(flood, np.zeros((h + 2, w + 2), np.uint8), (0, 0), 255)
    comp = comp | cv2.bitwise_not(flood)
    comp = cv2.morphologyEx(comp, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))  # de-speckle edges

    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    page = max(contours, key=cv2.contourArea)
    return _refine_quad(page, _quad_from_contour(page)), comp


def _quad_from_contour(page: np.ndarray) -> np.ndarray:
    """Best 4 corners of the page contour.

    A photo of a flat page on a desk is a convex quadrilateral with mild
    perspective (a trapezoid). The true corners come from polygon-approximating
    the convex hull — `approxPolyDP` lands on the actual corners, so the
    perspective warp straightens the page with the correct aspect ratio and clips
    no text. The old "extreme x±y points" heuristic put corners on the long edges
    of a rotated page, which warped to the wrong ratio and left residual tilt +
    cut a corner. Falls back to minAreaRect, then extreme points, if approximation
    doesn't yield a clean quad.
    """
    hull = cv2.convexHull(page)
    peri = cv2.arcLength(hull, True)
    for frac in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
        approx = cv2.approxPolyDP(hull, frac * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype("float32")

    # No clean quad: if the contour fills a rotated rectangle well, use that
    # (pure rotation, no perspective); otherwise the extreme-point fallback.
    box = cv2.boxPoints(cv2.minAreaRect(page)).astype("float32")
    if cv2.contourArea(page) / max(cv2.contourArea(box.astype(np.int32)), 1.0) >= 0.90:
        return box
    pts = page.reshape(-1, 2).astype("float32")
    ssum, sdiff = pts.sum(axis=1), pts[:, 1] - pts[:, 0]
    return np.array(
        [pts[np.argmin(ssum)], pts[np.argmin(sdiff)], pts[np.argmax(ssum)], pts[np.argmax(sdiff)]],
        dtype="float32",
    )


def _refine_quad(contour: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Refine page corners by fitting a straight line to each of the 4 edges and
    intersecting adjacent lines.

    The mask boundary is jagged, and a corner that falls outside the photo frame
    (the page runs off the edge of the shot) is reported by the contour as a point
    *on* the frame edge — which warps to a sheared page (a printed map comes out as
    a parallelogram). Fitting a line to each whole edge and intersecting recovers
    the true corner, even off-frame, so the warp squares the page. Falls back to
    the contour quad whenever an edge lacks support or the refit is degenerate.
    """
    quad = _order_points(quad)  # tl, tr, br, bl
    pts = contour.reshape(-1, 2).astype(np.float32)
    edges = [(quad[0], quad[1]), (quad[1], quad[2]), (quad[2], quad[3]), (quad[3], quad[0])]

    lines: list[np.ndarray] = []
    for a, b in edges:
        ab = b - a
        length = float(np.hypot(ab[0], ab[1])) + 1e-9
        t = (pts - a) @ ab / (length * length)
        perp = np.abs(ab[0] * (pts[:, 1] - a[1]) - ab[1] * (pts[:, 0] - a[0])) / length
        # the clean middle of the edge only: drop corner regions (t outside 0.2–0.8)
        # and points that don't lie along this edge (the opposite edge / stray blobs)
        keep = (t > 0.20) & (t < 0.80) & (perp < max(length * 0.04, 12.0))
        group = pts[keep]
        if len(group) < 10:
            return quad
        lines.append(cv2.fitLine(group, cv2.DIST_HUBER, 0, 0.01, 0.01).ravel())

    def intersect(l1: np.ndarray, l2: np.ndarray) -> np.ndarray | None:
        vx1, vy1, x1, y1 = l1
        vx2, vy2, x2, y2 = l2
        det = vx2 * vy1 - vy2 * vx1
        if abs(det) < 1e-6:
            return None
        s = (vx2 * (y2 - y1) - vy2 * (x2 - x1)) / det
        return np.array([x1 + vx1 * s, y1 + vy1 * s], dtype=np.float32)

    # corner i = intersection of the edge before it and the edge after it
    corners = [
        intersect(lines[3], lines[0]), intersect(lines[0], lines[1]),
        intersect(lines[1], lines[2]), intersect(lines[2], lines[3]),
    ]
    if any(c is None for c in corners):
        return quad
    refined = np.array(corners, dtype=np.float32)

    # sanity guard: accept the refit only if it stays a sane quad — similar area
    # and no corner flung absurdly far (allows real off-frame extrapolation, blocks
    # blow-ups from a bad line fit).
    approx_area = cv2.contourArea(quad)
    if approx_area <= 0:
        return quad
    diag = float(np.hypot(*(quad[2] - quad[0]))) or 1.0
    moved = np.linalg.norm(refined - quad, axis=1).max()
    if not (0.7 < cv2.contourArea(refined) / approx_area < 1.6) or moved > 0.25 * diag:
        return quad
    return refined


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


def _detect_page(img: np.ndarray) -> tuple[np.ndarray, np.ndarray | None] | None:
    found = _page_quad_bright(img)
    if found is not None:
        return found  # (quad, mask)
    quad = _page_quad_canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    return (quad, None) if quad is not None else None


def _four_point_warp(
    img: np.ndarray, quad: np.ndarray, page_mask: np.ndarray | None = None
) -> np.ndarray:
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
    # White border fill: when a refined corner lies outside the photo (the page ran
    # off the edge of the shot), the missing wedge reads as clean white paper
    # instead of a black triangle.
    warped = cv2.warpPerspective(
        img, matrix, (width, height),
        flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255),
    )
    # Whiten anything that isn't the detected page. When a corner is extrapolated
    # off-frame, the quad covers a triangle of desk next to the true page corner;
    # that desk is *outside* the page mask, so warping the mask and clearing
    # everything beyond it erases the wedge/smudge while leaving page content (the
    # map sits inside the mask via the earlier hole-fill, so it is never touched).
    if page_mask is not None:
        # Use the mask boundary as-is (no dilation): the page edge is white margin,
        # so whitening right up to it removes the desk smudge cleanly, while the map
        # sits well inside the mask and is untouched. Erode a hair to kill the 1-px
        # warp seam at the boundary.
        mask = cv2.erode(page_mask, np.ones((3, 3), np.uint8))
        warped_mask = cv2.warpPerspective(
            mask, matrix, (width, height), flags=cv2.INTER_NEAREST
        )
        warped[warped_mask < 128] = 255
    return warped


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
    """Rotate to correct residual skew (works on colour or greyscale).

    The output canvas is *expanded* to fit the rotated image so a corner is never
    pushed out of frame and clipped — the old fixed-size rotate cut a triangle off
    each corner (e.g. bottom-right text) whenever it fired on a near-full-frame
    page. The new white corners are cosmetic and get cleaned by the border passes.
    """
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    matrix[0, 2] += (new_w - w) / 2
    matrix[1, 2] += (new_h - h) / 2
    border = (255, 255, 255) if img.ndim == 3 else 255
    return cv2.warpAffine(
        img, matrix, (new_w, new_h),
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

    Continuous-tone regions (printed photos, maps, dark fills) are *protected*: the
    per-channel divide that crisps text-on-paper amplifies local contrast, which
    shreds a grey photo into salt-and-pepper noise. So the divide is only applied
    where the local background is bright (real paper); where it is dark — a printed
    image — the original tones are kept and merely illumination-corrected. A
    feathered mask blends the two so there is no visible seam. On a pure-text page
    the mask is empty and the result is identical to the plain flatten.
    """
    bgr = cv2.bilateralFilter(bgr, 5, 50, 50)  # edge-preserving denoise first

    norm_channels, bg_channels = [], []
    for c in cv2.split(bgr):
        background = cv2.medianBlur(cv2.dilate(c, np.ones((9, 9), np.uint8)), 31)
        bg_channels.append(background)
        norm_channels.append(cv2.divide(c, background, scale=255))
    norm = cv2.merge(norm_channels)  # crisp paper/text (but shreds photos)

    # "photo" = where the local background is dark -> a printed image, not paper.
    bg_luma = cv2.cvtColor(cv2.merge(bg_channels), cv2.COLOR_BGR2GRAY)
    photo = (bg_luma < 160).astype(np.float32)
    photo = np.clip(cv2.GaussianBlur(photo, (0, 0), 9), 0, 1)[..., None]  # feather
    out = (norm.astype(np.float32) * (1.0 - photo)
           + bgr.astype(np.float32) * photo).astype(np.uint8)

    # white-balance: lift the paper white-point so a uniformly grey/dim scan goes
    # white. Measured on paper (non-photo) pixels only, so a big dark image can't
    # drag the white-point down and over-brighten the page.
    luma = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    paper_luma = luma[photo[..., 0] < 0.5]
    wp = float(np.percentile(paper_luma if paper_luma.size else luma, 80))
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


def _clean_border_bands(bgr: np.ndarray, lo: int = 150, hi: int = 243,
                        min_area: float = 0.004) -> np.ndarray:
    """Whiten neutral grey background bands/wedges that the crop included and that
    touch a border. Restricted to low-saturation (neutral) blobs, so coloured
    content — stamps, signatures, photos — is never touched. The grey floor is low
    enough to catch a soft desk shadow along a page edge (which can fade to mid
    grey), but the border-touching + min-area + neutral constraints keep real
    content safe: a printed photo/map sits in the interior, not on the border.
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

    detection = _detect_page(img)
    if detection is not None:
        quad, page_mask = detection
        img = _inset(_four_point_warp(img, quad, page_mask=page_mask))

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
