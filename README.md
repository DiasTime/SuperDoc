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
| Worker | OpenCV, Pillow, PaddleOCR, Qwen2.5-VL 7B (self-hosted), pdfplumber, pypdf, python-docx |
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

## Status

**M0 — Foundation.** Runnable shell. See `PLAN.md` for milestone progress.
