"""Vision-language document understanding (Stage 3, M2).

Turns a restored page image + the OCR text into a typed `DocumentStructure`
(see packages/shared-types: DocumentStructure). The model is served behind an
**OpenAI-compatible** endpoint, so the exact same client drives:

  - a local **Ollama** (`ollama pull qwen2.5vl`) for dev / low volume, and
  - a **vLLM** server for production throughput,

selected by `settings.vl_backend` — only the base URL and model tag differ.

Resilience mirrors the OCR stage: anything that goes wrong (endpoint down, model
not pulled, malformed JSON) degrades to an `UNKNOWN` structure so the job still
finishes with a PDF, rather than failing the whole pipeline.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from worker.config import settings

log = logging.getLogger("worker.pipeline.vl")

# Mirrors DocumentType in packages/shared-types and the Prisma enum.
DOC_TYPES = (
    "UNKNOWN",
    "CONTRACT",
    "INVOICE",
    "ACT",
    "CERTIFICATE",
    "PASSPORT",
    "ID_CARD",
    "FORM",
    "COMMERCIAL_OFFER",
)
_SIGNATURE_KINDS = ("signature", "stamp", "seal")
_DEFAULT_CONF = 0.9  # placeholder confidence until per-field grounding lands

EMPTY_STRUCTURE: dict[str, Any] = {
    "type": "UNKNOWN",
    "title": None,
    "summary": None,
    "sections": [],
    "signatures": [],
    "metadata": {},
}

_SYSTEM_PROMPT = (
    "You are a document-understanding engine. You are given a scanned or "
    "photographed document page and the OCR text read from it. Identify the "
    "document type and reconstruct its structure.\n\n"
    "Respond with ONLY a single JSON object — no prose, no markdown fences. "
    "Use this exact shape:\n"
    "{\n"
    '  "type": "<ONE OF: ' + ", ".join(DOC_TYPES) + '>",\n'
    '  "title": string | null,\n'
    '  "summary": string | null,   // 1-3 plain sentences\n'
    '  "sections": [\n'
    "    {\n"
    '      "heading": string | null,\n'
    '      "level": integer,        // 1 = top-level\n'
    '      "paragraphs": [string],\n'
    '      "keyValues": [{"key": string, "value": string}],\n'
    '      "tables": [{"caption": string | null, "rows": [[string]]}]\n'
    "    }\n"
    "  ],\n"
    '  "signatures": [{"kind": "signature|stamp|seal", "label": string | null}],\n'
    '  "metadata": {string: string}\n'
    "}\n\n"
    "Rules:\n"
    "- Use ONLY text present in the image / OCR. Never invent values; if you are "
    "unsure of a field, omit it rather than guess.\n"
    "- 'type' MUST be one of the listed values; use UNKNOWN if none fit.\n"
    "- Put document-level facts (dates, totals, IDs, parties) into keyValues or "
    "metadata so downstream code can ground them against the OCR boxes."
)


# ─────────────────────────── Provider interface ───────────────────────────


class VLProvider(ABC):
    """Swappable vision-language backend. Implementations must return a
    DocumentStructure-shaped dict (already normalized via `_normalize_structure`)."""

    @abstractmethod
    def extract_structure(
        self, image_bytes: bytes, ocr: dict[str, Any] | None
    ) -> dict[str, Any]:
        ...


class OpenAICompatVL(VLProvider):
    """Talks to any OpenAI-compatible chat-completions endpoint (Ollama, vLLM)."""

    def __init__(
        self,
        endpoint: str,
        model: str,
        api_key: str,
        max_tokens: int,
        timeout: float,
    ) -> None:
        from openai import OpenAI  # lazy: import only when a real call is wired up

        self._client = OpenAI(base_url=endpoint, api_key=api_key, timeout=timeout)
        self._model = model
        self._max_tokens = max_tokens

    def extract_structure(
        self, image_bytes: bytes, ocr: dict[str, Any] | None
    ) -> dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=_build_messages(image_bytes, ocr),
            max_tokens=self._max_tokens,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        return _normalize_structure(_parse_json(content))


# ─────────────────────────── Prompt assembly ───────────────────────────


def _ocr_lines(ocr: dict[str, Any] | None, max_chars: int = 2000) -> str:
    if not ocr:
        return ""
    words = ocr.get("words") or []
    text = "\n".join(w.get("text", "") for w in words if w.get("text", "").strip())
    return text[:max_chars]  # cap so a dense page can't blow the context window


def _downscale_for_vl(image_bytes: bytes, max_side: int = 1024) -> bytes:
    """Shrink the page for the VL model so the image's vision tokens fit the
    context window. Structure/type detection doesn't need full restoration
    resolution — the OCR text carries the exact characters.
    """
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(image_bytes))
        w, h = im.size
        if max(w, h) <= max_side:
            return image_bytes
        scale = max_side / max(w, h)
        im = im.convert("RGB").resize((max(1, int(w * scale)), max(1, int(h * scale))))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001 — never block understanding on a resize hiccup
        return image_bytes


def _build_messages(image_bytes: bytes, ocr: dict[str, Any] | None) -> list[dict[str, Any]]:
    b64 = base64.b64encode(_downscale_for_vl(image_bytes)).decode("ascii")
    ocr_text = _ocr_lines(ocr) or "(no OCR text available)"
    user_text = (
        "OCR text extracted from the page (treat as ground truth, do not invent "
        f"beyond it):\n{ocr_text}\n\nReturn the JSON object now."
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
            ],
        },
    ]


# ─────────────────────────── Parsing + normalization ───────────────────────────


def _parse_json(content: str) -> Any:
    """Parse the model's reply, tolerating markdown fences / surrounding prose."""
    text = content.strip()
    if text.startswith("```"):
        # drop the opening fence (``` or ```json) and the trailing fence
        text = text.split("\n", 1)[-1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    log.warning("VL reply was not valid JSON; using empty structure")
    return {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _grounded(value: str, confidence: float = _DEFAULT_CONF) -> dict[str, Any]:
    return {"value": value, "confidence": confidence}


def _norm_section(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    conf = _as_confidence(raw.get("confidence"))
    heading = _clean_str(raw.get("heading"))
    key_values = []
    for kv in _as_list(raw.get("keyValues")):
        if not isinstance(kv, dict):
            continue
        key = _clean_str(kv.get("key"))
        val = _clean_str(kv.get("value"))
        if key and val is not None:
            key_values.append({"key": key, "value": _grounded(val, conf)})
    tables = []
    for tbl in _as_list(raw.get("tables")):
        if not isinstance(tbl, dict):
            continue
        rows = [
            [
                {"text": str(cell), "rowSpan": 1, "colSpan": 1, "confidence": conf}
                for cell in _as_list(row)
            ]
            for row in _as_list(tbl.get("rows"))
        ]
        if rows:
            tables.append({"caption": _clean_str(tbl.get("caption")), "rows": rows})
    return {
        "heading": _grounded(heading, conf) if heading else None,
        "level": _as_int(raw.get("level"), default=1),
        "paragraphs": [str(p).strip() for p in _as_list(raw.get("paragraphs")) if str(p).strip()],
        "tables": tables,
        "keyValues": key_values,
    }


def _norm_signature(raw: Any) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    kind = str(raw.get("kind", "signature")).lower()
    if kind not in _SIGNATURE_KINDS:
        kind = "signature"
    # box grounding is a follow-up; emit an empty box for shape compatibility.
    return {"kind": kind, "box": [], "label": _clean_str(raw.get("label"))}


def _norm_metadata(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None}


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_confidence(value: Any) -> float:
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return _DEFAULT_CONF
    return min(1.0, max(0.0, conf))


def _normalize_structure(raw: Any) -> dict[str, Any]:
    """Coerce a model reply into a safe, DocumentStructure-shaped dict.

    Guarantees a valid `type` enum, list-typed collections, and str-typed
    metadata so the DB write and the frontend never choke on a wild reply.
    """
    if not isinstance(raw, dict):
        return dict(EMPTY_STRUCTURE)
    doc_type = str(raw.get("type", "UNKNOWN")).upper()
    if doc_type not in DOC_TYPES:
        doc_type = "UNKNOWN"
    return {
        "type": doc_type,
        "title": _clean_str(raw.get("title")),
        "summary": _clean_str(raw.get("summary")),
        "sections": [_norm_section(s) for s in _as_list(raw.get("sections"))],
        "signatures": [_norm_signature(s) for s in _as_list(raw.get("signatures"))],
        "metadata": _norm_metadata(raw.get("metadata")),
    }


# ─────────────────────────── OCR-driven box grounding ───────────────────────────


def _norm_text(text: str) -> str:
    """Normalize for fuzzy matching: lowercase, strip punctuation, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text.lower())).strip()


def ground_structure(structure: dict[str, Any], ocr: dict[str, Any] | None) -> dict[str, Any]:
    """Link extracted text fields to OCR word boxes by fuzzy text matching.

    For each grounded value (keyValue, heading, table cell) we search the OCR
    word list for the closest matching word and promote its confidence and box
    to the field — giving downstream consumers a reliable source location rather
    than the placeholder confidence emitted by the VL model.

    Modifies `structure` in-place and returns it.
    """
    if not ocr or not ocr.get("words"):
        return structure

    words: list[dict[str, Any]] = ocr["words"]

    # Build a lookup: normalized-text -> [(confidence, box), ...]
    index: dict[str, list[tuple[float, list[Any]]]] = {}
    for w in words:
        key = _norm_text(w.get("text", ""))
        if key:
            index.setdefault(key, []).append((w.get("confidence", 0.9), w.get("box", [])))

    def _best(text: str | None) -> tuple[float, list[Any]] | None:
        if not text:
            return None
        norm = _norm_text(str(text))
        if norm in index:
            return max(index[norm], key=lambda e: e[0])
        # Substring fallback: longest OCR token that appears in the extracted value
        best: tuple[float, list[Any]] | None = None
        best_len = 0
        for key, entries in index.items():
            if key and (key in norm or norm in key) and len(key) > best_len:
                best_len = len(key)
                best = max(entries, key=lambda e: e[0])
        return best

    def _update_grounded(g: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(g, dict):
            return g
        match = _best(g.get("value"))
        if match:
            return {"value": g["value"], "confidence": match[0], "box": match[1]}
        return g

    for section in structure.get("sections", []):
        if section.get("heading"):
            section["heading"] = _update_grounded(section["heading"])
        for kv in section.get("keyValues", []):
            if isinstance(kv.get("value"), dict):
                kv["value"] = _update_grounded(kv["value"])
        for tbl in section.get("tables", []):
            for row in tbl.get("rows", []):
                for i, cell in enumerate(row):
                    if isinstance(cell, dict) and cell.get("text"):
                        match = _best(cell["text"])
                        if match:
                            row[i] = {**cell, "confidence": match[0]}

    return structure


# ─────────────────────────── Stage entry point ───────────────────────────

_provider: VLProvider | None = None
_provider_failed = False


def get_provider() -> VLProvider | None:
    """Lazily construct the configured provider (one per worker process)."""
    global _provider, _provider_failed
    if _provider is not None or _provider_failed:
        return _provider
    try:
        _provider = OpenAICompatVL(
            endpoint=settings.vl_endpoint,
            model=settings.vl_model_name,
            api_key=settings.vl_api_key,
            max_tokens=settings.vl_max_tokens,
            timeout=settings.vl_timeout,
        )
        log.info(
            "VL provider ready", extra={"backend": settings.vl_backend, "model": settings.vl_model_name}
        )
    except Exception as exc:  # noqa: BLE001 — missing openai / bad config degrades to pass-through
        log.warning("VL provider unavailable; understanding will pass through: %s", exc)
        _provider_failed = True
    return _provider


def understand(
    image_bytes: bytes,
    ocr: dict[str, Any] | None,
    provider: VLProvider | None = None,
) -> dict[str, Any]:
    """Return a DocumentStructure-shaped dict for the page. Never raises.

    Falls back to an UNKNOWN structure if understanding is disabled, the provider
    can't be built, or the call fails — so the job still completes.
    """
    if not settings.vl_enabled:
        return dict(EMPTY_STRUCTURE)
    provider = provider or get_provider()
    if provider is None:
        return dict(EMPTY_STRUCTURE)
    try:
        structure = provider.extract_structure(image_bytes, ocr)
        return ground_structure(structure, ocr)
    except Exception:  # noqa: BLE001 — a bad page/model must not kill the job
        log.exception("VL understanding failed; returning UNKNOWN structure")
        return dict(EMPTY_STRUCTURE)
