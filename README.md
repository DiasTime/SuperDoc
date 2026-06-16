# Document Resurrection AI

Upload a bad photo, skewed scan, screenshot, or old PDF. Get back something that
looks like the **original source file**: clean PDF, editable DOCX, structured JSON,
metadata, and a summary.

> Not OCR. **Document reconstruction.** See [`PLAN.md`](./PLAN.md) for the full
> architecture, milestones, and decisions.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 15, TypeScript, Tailwind, shadcn/ui, Framer Motion |
| Gateway | FastAPI, Python 3.12 |
| Worker | OpenCV, Pillow, PaddleOCR, Qwen-VL (Ollama dev / vLLM prod), reportlab, pdfplumber, pypdf, python-docx |
| Data | PostgreSQL (Prisma schema), Redis (queue), MinIO/S3 (artifacts) |
| Infra | Docker, Docker Compose |

## Monorepo layout

```
apps/web      Next.js frontend
apps/api      FastAPI gateway (thin: auth, upload, jobs, downloads)
apps/worker   Python pipeline (restore → OCR → VL → reconstruct)
packages/shared-types   TS types shared across the stack
prisma        Database schema (source of truth)
infra         ops + model download helpers
```

## Quick start (local, full stack)

```bash
cp .env.example .env
docker compose up --build
```

- Web → http://localhost:3000
- API docs → http://localhost:8000/docs
- API health → http://localhost:8000/health
- MinIO console → http://localhost:9001

## Quick start (frontend only — no Docker/Python needed)

```bash
pnpm install
pnpm --filter web dev
```

## Document understanding (AI)

The understanding stage talks to a Qwen-VL model over an OpenAI-compatible endpoint:

```bash
# dev: local Ollama
ollama pull qwen2.5vl        # or qwen2.5vl:3b for a lighter/faster model
# the worker reads it at http://localhost:11434/v1 (host.docker.internal from Docker)
```

Set `VL_ENDPOINT` to a vLLM server for production throughput — the client code is identical. If no VL endpoint is reachable, understanding degrades gracefully (the job still produces a clean PDF). See `.env.example` for `VL_*` and `RESTORE_*` knobs.

## What works today

Upload a photo → **clean, cropped, deskewed colour scan** (stamps/signatures/photos preserved; `RESTORE_MODE=color|gray|binary`) → **searchable PDF** (PaddleOCR text layer) → **typed `DocumentStructure` + summary** (Qwen-VL) → **JSON export**.

## Status

**M2 — Document Intelligence (in progress).** Full pipeline verified end-to-end in the Docker worker: restore → OCR → understand → reconstruct. M0/M1.1/M1.2 done. Remaining in M2: DOCX export, rich structure-aware HTML reconstruction, field box-grounding, vLLM prod path. See [`PLAN.md`](./PLAN.md) for full milestone progress.
