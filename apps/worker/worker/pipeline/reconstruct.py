"""Reconstruction outputs.

M1.1: wrap the restored page image into a clean PDF (Pillow).
M1.2: searchable PDF — restored image as the page, plus an invisible OCR text
      layer positioned per line so the PDF is selectable / searchable.
M2:   structure-aware HTML -> PDF/DOCX (structure_to_html / structure_to_docx /
      structure_to_rich_pdf).
"""

from __future__ import annotations

import html
import io
import json
import logging
from typing import Any

from PIL import Image

log = logging.getLogger("worker.pipeline.reconstruct")

_DPI = 150.0
_PT_PER_PX = 72.0 / _DPI
_INVISIBLE = 3  # PDF text render mode: no fill, no stroke

# Per-type accent colours (used in HTML and DOCX)
_TYPE_COLORS: dict[str, str] = {
    "INVOICE": "#1d4ed8",
    "CONTRACT": "#065f46",
    "ACT": "#92400e",
    "CERTIFICATE": "#6d28d9",
    "PASSPORT": "#be185d",
    "ID_CARD": "#0e7490",
    "FORM": "#374151",
    "COMMERCIAL_OFFER": "#b45309",
    "UNKNOWN": "#6b7280",
}


def structure_to_json(structure: dict[str, Any]) -> bytes:
    """Serialize the understanding output into a downloadable JSON artifact.

    This is the M2 `GET /download/json/:id` payload — the typed
    `DocumentStructure` (type, sections, key-values, signatures, metadata).
    """
    return json.dumps(structure, ensure_ascii=False, indent=2).encode("utf-8")


def image_to_pdf(image_bytes: bytes) -> bytes:
    """Image-only PDF (no text layer). Fallback when OCR produced nothing."""
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    out = io.BytesIO()
    image.save(out, format="PDF", resolution=_DPI)
    return out.getvalue()


def searchable_pdf(image_bytes: bytes, words: list[dict[str, Any]]) -> bytes:
    """Restored image + invisible, positioned OCR text → searchable PDF.

    Boxes are normalized 0–1 (y from the top). Each line is drawn invisibly and
    horizontally scaled to span its box, so selection/search line up with the
    visible glyphs underneath. Degrades to `image_to_pdf` if reportlab is absent.
    """
    try:
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception as exc:  # noqa: BLE001
        log.warning("reportlab unavailable; emitting image-only PDF: %s", exc)
        return image_to_pdf(image_bytes)

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w_px, h_px = image.size
    page_w, page_h = w_px * _PT_PER_PX, h_px * _PT_PER_PX

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    c.drawImage(ImageReader(image), 0, 0, width=page_w, height=page_h)

    for word in words:
        text = word.get("text", "").strip()
        if not text:
            continue
        xs = [p[0] for p in word["box"]]
        ys = [p[1] for p in word["box"]]
        x0 = min(xs) * page_w
        box_w = (max(xs) - min(xs)) * page_w
        # PDF origin is bottom-left; OCR y grows downward from the top.
        baseline_y = page_h - (max(ys) * page_h)
        font_size = max((max(ys) - min(ys)) * page_h * 0.8, 4.0)

        to = c.beginText()
        to.setTextRenderMode(_INVISIBLE)
        to.setFont("Helvetica", font_size)
        glyph_w = c.stringWidth(text, "Helvetica", font_size)
        if glyph_w > 0 and box_w > 0:
            to.setHorizScale(100.0 * box_w / glyph_w)
        to.setTextOrigin(x0, baseline_y)
        to.textLine(text)
        c.drawText(to)

    c.showPage()
    c.save()
    return buf.getvalue()


# ─────────────────────────── M2: structure-aware outputs ───────────────────────────


def _esc(text: Any) -> str:
    return html.escape(str(text)) if text is not None else ""


def _grounded_value(g: Any) -> tuple[str, float]:
    """Return (text, confidence) from a Grounded<string> dict or a plain string."""
    if isinstance(g, dict):
        return str(g.get("value") or ""), float(g.get("confidence") or 1.0)
    return str(g) if g is not None else "", 1.0


def structure_to_html(structure: dict[str, Any]) -> str:
    """Render DocumentStructure as semantic, print-ready HTML.

    Used as the intermediate format for the rich PDF (WeasyPrint) and as a
    standalone HTML export.  Per-doc-type accent colours make invoice / contract
    / passport instantly distinguishable.
    """
    doc_type = str(structure.get("type") or "UNKNOWN")
    title_raw = structure.get("title") or "Document"
    summary = structure.get("summary") or ""
    sections: list[dict[str, Any]] = structure.get("sections") or []
    sigs: list[dict[str, Any]] = structure.get("signatures") or []
    metadata: dict[str, str] = structure.get("metadata") or {}
    accent = _TYPE_COLORS.get(doc_type, "#6b7280")
    type_label = doc_type.replace("_", " ")

    parts: list[str] = [
        f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:Georgia,"Times New Roman",serif;max-width:780px;margin:0 auto;
        padding:48px 40px;color:#1f2937;font-size:13px;line-height:1.65}}
  .badge{{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.08em;
          text-transform:uppercase;padding:3px 10px;border-radius:999px;
          background:{accent}22;color:{accent};margin-bottom:14px}}
  h1{{font-size:22px;font-weight:700;color:{accent};margin-bottom:8px}}
  .summary{{color:#4b5563;font-style:italic;margin-bottom:18px;font-size:12px}}
  h2{{font-size:15px;font-weight:700;margin:22px 0 6px;border-bottom:1px solid #e5e7eb;
      padding-bottom:4px;color:{accent}}}
  h3{{font-size:13px;font-weight:700;margin:14px 0 4px}}
  h4,h5,h6{{font-size:12px;font-weight:700;margin:10px 0 3px}}
  p{{margin:4px 0 8px}}
  dl{{display:grid;grid-template-columns:auto 1fr;gap:2px 16px;
      margin:8px 0 14px;font-size:12px}}
  dt{{font-weight:700;color:#374151;padding:2px 0}}
  dd{{color:#1f2937;padding:2px 0}}
  table{{border-collapse:collapse;width:100%;margin:10px 0 16px;font-size:12px}}
  th,td{{border:1px solid #d1d5db;padding:5px 8px;text-align:left;vertical-align:top}}
  th{{background:#f3f4f6;font-weight:700}}
  caption{{text-align:left;font-weight:700;margin-bottom:4px;font-size:12px}}
  .low-conf{{background:#fef3c7;color:#92400e}}
  .sig-block{{display:inline-block;border:1px dashed #9ca3af;padding:6px 20px;
              margin:4px 8px 4px 0;font-size:11px;color:#6b7280;border-radius:4px}}
  .meta-table{{width:auto;min-width:280px}}
  @media print{{body{{padding:24px}}}}
</style>
</head>
<body>
<div class="badge">{_esc(type_label)}</div>
<h1>{_esc(title_raw)}</h1>
"""
    ]

    if summary:
        parts.append(f'<p class="summary">{_esc(summary)}</p>\n')

    if metadata:
        parts.append('<table class="meta-table"><tbody>\n')
        for k, v in metadata.items():
            parts.append(f"<tr><th>{_esc(k)}</th><td>{_esc(v)}</td></tr>\n")
        parts.append("</tbody></table>\n")

    for section in sections:
        heading_raw = section.get("heading")
        level = max(1, int(section.get("level") or 1))
        if heading_raw is not None:
            h_text, h_conf = _grounded_value(heading_raw)
            if h_text:
                tag = f"h{min(level + 1, 6)}"
                conf_cls = ' class="low-conf"' if h_conf < 0.7 else ""
                parts.append(f"<{tag}{conf_cls}>{_esc(h_text)}</{tag}>\n")

        kvs: list[dict[str, Any]] = section.get("keyValues") or []
        if kvs:
            parts.append("<dl>\n")
            for kv in kvs:
                k = kv.get("key") or ""
                v, conf = _grounded_value(kv.get("value"))
                val_cls = ' class="low-conf"' if conf < 0.7 else ""
                parts.append(f"<dt>{_esc(k)}</dt><dd{val_cls}>{_esc(v)}</dd>\n")
            parts.append("</dl>\n")

        for p_text in (section.get("paragraphs") or []):
            if str(p_text).strip():
                parts.append(f"<p>{_esc(p_text)}</p>\n")

        for tbl in (section.get("tables") or []):
            caption = tbl.get("caption")
            if caption:
                parts.append(f"<table><caption>{_esc(caption)}</caption>\n")
            else:
                parts.append("<table>\n")
            for i, row in enumerate(tbl.get("rows") or []):
                parts.append("<tr>")
                tag = "th" if i == 0 else "td"
                for cell in row:
                    if isinstance(cell, dict):
                        text = cell.get("text") or ""
                        conf = float(cell.get("confidence") or 1.0)
                        rs = int(cell.get("rowSpan") or 1)
                        cs = int(cell.get("colSpan") or 1)
                        attrs = ""
                        if rs > 1:
                            attrs += f' rowspan="{rs}"'
                        if cs > 1:
                            attrs += f' colspan="{cs}"'
                        if conf < 0.7:
                            attrs += ' class="low-conf"'
                        parts.append(f"<{tag}{attrs}>{_esc(text)}</{tag}>")
                    else:
                        parts.append(f"<{tag}>{_esc(cell)}</{tag}>")
                parts.append("</tr>\n")
            parts.append("</table>\n")

    if sigs:
        parts.append("<h2>Signatures &amp; Stamps</h2>\n")
        for sig in sigs:
            kind = str(sig.get("kind") or "signature")
            label = sig.get("label")
            text = kind.upper()
            if label:
                text += f" — {label}"
            parts.append(f'<span class="sig-block">{_esc(text)}</span>\n')

    parts.append("</body></html>")
    return "".join(parts)


def structure_to_rich_pdf(structure: dict[str, Any]) -> bytes | None:
    """Convert DocumentStructure → HTML → PDF via WeasyPrint.

    Returns None (caller should fall back to searchable PDF) when:
    - WeasyPrint is unavailable
    - structure is empty / UNKNOWN
    - conversion raises an exception
    """
    doc_type = str(structure.get("type") or "UNKNOWN")
    has_content = bool(structure.get("sections") or structure.get("metadata"))
    if doc_type == "UNKNOWN" and not has_content:
        return None
    try:
        from weasyprint import HTML as WPHtml

        html_src = structure_to_html(structure)
        return WPHtml(string=html_src).write_pdf()
    except Exception as exc:  # noqa: BLE001
        log.warning("WeasyPrint rich PDF failed; caller will use searchable PDF: %s", exc)
        return None


def structure_to_docx(structure: dict[str, Any]) -> bytes | None:
    """Build an editable DOCX from DocumentStructure.

    Returns None when python-docx is unavailable (caller skips the export).
    Low-confidence values are highlighted in amber so reviewers can spot them.
    """
    try:
        from docx import Document as DocxDocument
        from docx.oxml.ns import qn
        from docx.shared import Pt, RGBColor
    except ImportError:
        log.warning("python-docx unavailable; skipping DOCX export")
        return None

    doc_type = str(structure.get("type") or "UNKNOWN")
    title_raw = structure.get("title") or "Document"
    summary = structure.get("summary") or ""
    sections: list[dict[str, Any]] = structure.get("sections") or []
    sigs: list[dict[str, Any]] = structure.get("signatures") or []
    metadata: dict[str, str] = structure.get("metadata") or {}

    doc = DocxDocument()

    # Remove default empty paragraph that python-docx adds
    for p in list(doc.paragraphs):
        p._element.getparent().remove(p._element)

    type_label = doc_type.replace("_", " ")
    doc.add_heading(f"{type_label}: {title_raw}", level=0)

    if summary:
        p = doc.add_paragraph(summary)
        if p.runs:
            p.runs[0].italic = True

    if metadata:
        doc.add_heading("Document Details", level=1)
        tbl = doc.add_table(rows=len(metadata), cols=2)
        tbl.style = "Table Grid"
        for i, (k, v) in enumerate(metadata.items()):
            tbl.cell(i, 0).text = k
            tbl.cell(i, 0).paragraphs[0].runs[0].bold = True
            tbl.cell(i, 1).text = v

    for section in sections:
        heading_raw = section.get("heading")
        level = max(1, int(section.get("level") or 1))
        if heading_raw is not None:
            h_text, _ = _grounded_value(heading_raw)
            if h_text:
                doc.add_heading(h_text, level=min(level, 4))

        kvs: list[dict[str, Any]] = section.get("keyValues") or []
        if kvs:
            tbl = doc.add_table(rows=len(kvs), cols=2)
            tbl.style = "Table Grid"
            for i, kv in enumerate(kvs):
                k = kv.get("key") or ""
                v, conf = _grounded_value(kv.get("value"))
                tbl.cell(i, 0).text = k
                if tbl.cell(i, 0).paragraphs[0].runs:
                    tbl.cell(i, 0).paragraphs[0].runs[0].bold = True
                tbl.cell(i, 1).text = v
                if conf < 0.7 and tbl.cell(i, 1).paragraphs[0].runs:
                    tbl.cell(i, 1).paragraphs[0].runs[0].font.highlight_color = 4  # yellow

        for p_text in (section.get("paragraphs") or []):
            if str(p_text).strip():
                doc.add_paragraph(str(p_text))

        for tbl_data in (section.get("tables") or []):
            caption = tbl_data.get("caption")
            if caption:
                p = doc.add_paragraph(caption)
                if p.runs:
                    p.runs[0].bold = True
            rows = tbl_data.get("rows") or []
            if not rows:
                continue
            n_cols = max((len(row) for row in rows), default=0)
            if n_cols == 0:
                continue
            dtbl = doc.add_table(rows=len(rows), cols=n_cols)
            dtbl.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, cell in enumerate(row[:n_cols]):
                    if isinstance(cell, dict):
                        text = str(cell.get("text") or "")
                        conf = float(cell.get("confidence") or 1.0)
                    else:
                        text = str(cell) if cell is not None else ""
                        conf = 1.0
                    dtbl.cell(i, j).text = text
                    if conf < 0.7 and i == 0 and dtbl.cell(i, j).paragraphs[0].runs:
                        dtbl.cell(i, j).paragraphs[0].runs[0].bold = True

    if sigs:
        doc.add_heading("Signatures & Stamps", level=1)
        for sig in sigs:
            kind = str(sig.get("kind") or "signature")
            label = sig.get("label")
            text = f"[{kind.upper()}]"
            if label:
                text += f" — {label}"
            doc.add_paragraph(text)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
