# Document Resurrection AI — Development Plan

> **Vision:** A user uploads a bad photo / skewed scan / old PDF. The system returns
> something that looks like the *original source file*: clean PDF, editable DOCX,
> structured JSON, extracted metadata, and a summary.
>
> **Not OCR. Document reconstruction.** The AI understands document *type, hierarchy,
> layout, sections, tables, signatures, stamps, forms, and key–value pairs* — then
> rebuilds the document.

This document is the single source of truth for *how* we build it. It is updated as
milestones complete. Each task has a checkbox. Work proceeds top-to-bottom in
vertical slices — each milestone is independently runnable and demoable.

---

## 0. Decisions locked in

| Decision | Choice | Rationale |
|---|---|---|
| AI vision model | **Self-host Qwen2.5-VL 7B** | Full control, privacy (handles passports/IDs/contracts), cheap at scale. Needs a GPU box (~16GB+ VRAM). |
| OCR engine | PaddleOCR | Strong multilingual OCR with box + confidence output. |
| Pipeline execution | **Async** (queue + workers) | 7B VL inference is seconds–minutes/page; never block an HTTP request. |
| Reconstruction fidelity | readability > aesthetics > exact replication | Pixel-perfect = months. Semantic HTML→PDF = days and looks professional. |
| Repo shape | **Monorepo** (pnpm workspaces + Python uv) | Shared types across front/back, one `docker compose up`. |
| Storage | PostgreSQL (metadata) + S3-compatible object store (files/artifacts) | Don't store blobs in Postgres. MinIO locally, S3 in prod. |

### Architecture (target)

```
Browser (Next.js 15)
   │  POST /upload (presigned → object store)
   ▼
FastAPI gateway ──create job──▶ Postgres (jobs, documents)
   │  enqueue job id                ▲ status updates
   ▼                                │
Queue (Redis + RQ/Celery)          │
   ▼                                │
Worker (GPU box) ──────────────────┘
   ├─ Image restore  (OpenCV: deskew, denoise, shadow removal, crop, perspective)
   ├─ OCR            (PaddleOCR → text + boxes + confidence)
   ├─ Understanding  (Qwen2.5-VL 7B → typed document structure)
   └─ Reconstruct    (HTML/CSS → PDF + DOCX + JSON)
   ▼
Object store (artifacts)  +  Postgres (metadata)
   ▼
Browser polls GET /document/:id → result + downloads
```

### Monorepo layout (target)

```
SuperDoc/
├── PLAN.md                  # this file
├── README.md
├── docker-compose.yml       # postgres + redis + minio + api + worker + web
├── .env.example
├── pnpm-workspace.yaml
├── package.json             # workspace root
├── prisma/
│   └── schema.prisma        # DB schema (source of truth)
├── packages/
│   └── shared-types/        # TS types shared by web + (generated for) api
├── apps/
│   ├── web/                 # Next.js 15 + Tailwind + shadcn/ui + Framer Motion
│   ├── api/                 # FastAPI gateway (thin: auth, upload, jobs, downloads)
│   └── worker/              # Python pipeline (restore → OCR → VL → reconstruct)
└── infra/                   # init scripts, model download, ops helpers
```

---

## Milestone M0 — Foundation (the runnable shell)  ← FIRST TASK

Goal: everything boots with `docker compose up`, even if endpoints are stubs.

- [x] `git init`, `.gitignore`, `.env.example`, root `README.md`
- [x] pnpm workspace root (`package.json`, `pnpm-workspace.yaml`)
- [x] `prisma/schema.prisma` — full schema (users, documents, processing_jobs, exports, subscriptions) — **applied to live Postgres 18 (`docres`); 5 tables verified**
- [x] `packages/shared-types` — OCR result, document structure, job status enums — **`tsc` typecheck passes**
- [x] `apps/api` — FastAPI skeleton: health, settings, CORS, structured logging, error handler — **boots; `/health` 200 verified (Python 3.14 venv)**
- [x] `apps/worker` — Python pipeline skeleton: queue consumer + no-op stage interfaces
- [x] `apps/web` — Next.js 15 skeleton: landing + Tailwind + theme + Framer Motion — **`next build` green; dev server serves :3000 verified**
- [x] `docker-compose.yml` — postgres, redis, minio, api, worker, web
- [x] Health checks green across the stack — **Postgres (native) + schema; Redis (docker) PONG; MinIO (docker) :9000 200 + bucket `docres`; API /health 200; web :3000 200**

> **M0 COMPLETE.** Runtime topology: Postgres native on :5432; Redis + MinIO via `docker compose up -d redis minio minio-init`; api/web run natively for fast iteration.

**Definition of done:** `docker compose up` → web on :3000, api `/health` 200, worker connects to redis, postgres + minio reachable.

### Open blockers (M0 → M1)
- **Docker engine won't start: WSL not installed.** Fix (admin PowerShell): `wsl --install` → reboot → reopen Docker Desktop. Unblocks Redis + MinIO + one-command stack.
- **Python is 3.14, repo targets 3.12.** API runs fine on 3.14. The worker's AI stack (paddleocr/paddlepaddle, opencv, numpy) may lack 3.14 wheels — install **Python 3.12** for the worker venv before M1 (`winget install Python.Python.3.12`).

---

## Milestone M1 — Vertical slice (happy path, no AI smarts yet)

Goal: prove the full pipe end-to-end on one document type with deterministic stages.

### M1.1 — async pipe + image restoration (DONE ✅, verified end-to-end)
- [x] Object storage client (put/get + presigned download) — MinIO/S3 (`app/storage.py`, `worker/storage.py`)
- [x] `POST /upload` → magic-byte MIME sniff + size limit → store file, create `document` + `processing_job`
- [x] `POST /process/:id` → enqueue job (Redis)
- [x] Worker stage 1 — **Image restoration** (OpenCV):
  - [x] grayscale path
  - [x] denoise (Non-Local Means)
  - [x] shadow removal (background division)
  - [x] contrast normalization (CLAHE) + white-point flatten
  - [x] document edge detection → perspective correction (4-point warp)
  - [x] deskew (projection-profile search — robust across OpenCV versions)
  - [ ] auto-orient (EXIF) + auto-crop — deferred to M1.2
- [x] Worker stage 4 — **Reconstruction (basic)**: restored page → clean PDF (Pillow)
- [x] `GET /document/:id` (status + progress + exports), `GET /download/pdf/:id` (presigned redirect)
- [x] Real async run verified: skewed/noisy/shadowed photo → deskewed clean PDF (visual before/after confirmed)

### M1.2 — OCR + text-based reconstruction (code-complete, pending live verify)
- [x] Worker stage 2 — **OCR** (PaddleOCR): text + boxes + confidence, geometry preserved (`worker/pipeline/ocr.py`; lazy import, degrades to pass-through if paddle is unavailable so the job still completes)
- [x] OCR-driven background removal — whiten everything outside the (dilated) text mask to pure white (`whiten_background`)
- [x] **Searchable PDF**: restored image + invisible, per-line OCR text layer, horizontally scaled to its box (`reconstruct.searchable_pdf`, reportlab); falls back to image-only PDF when OCR is empty
- [ ] ordered text blocks → **semantic HTML → PDF/DOCX** — deferred to M2 (rich, structure-aware reconstruction)
- [x] Web: upload (drag-drop/click) → live stage tracker (poll `GET /document/:id`) → result + PDF download (`apps/web/app/_components/Uploader.tsx`)

**Definition of done:** upload a skewed phone photo → get a clean, readable PDF back. **(M1.1 met for image-PDF; M1.2 adds the searchable text layer + web UI — code-complete; OCR text layer needs a live run in the Docker worker to confirm.)**

---

## Milestone M2 — Document Intelligence (the magic)

Goal: from "text on a page" to "typed, structured document".

- [ ] Stand up **Qwen2.5-VL 7B** self-hosted (vLLM serving, GPU; quantized fallback)
- [ ] VL provider interface in worker (so model is swappable / mockable in tests)
- [ ] Stage 3 — **Document understanding**: OCR + image → structured JSON
  - [ ] doc-type detection: contract, invoice, act, certificate, passport, ID, form, commercial offer
  - [ ] hierarchy: title → sections → headings → paragraphs
  - [ ] tables (cells, spans), key–value pairs, signatures, stamps
  - [ ] **grounding:** every extracted field references an OCR box + confidence (anti-hallucination)
- [ ] Metadata extraction + document summary
- [ ] Stage 4+ — **Reconstruction (rich)**: structure-aware HTML/CSS templates per doc type
- [ ] DOCX export (`python-docx`) + JSON export
- [ ] `GET /download/docx/:id`, `GET /download/json/:id`
- [ ] Web: structured result view (sections, tables, confidence flags), all download formats

**Definition of done:** upload an invoice photo → typed JSON with line items, a clean DOCX, a PDF, and a summary; low-confidence fields flagged.

---

## Milestone M3 — Frontend UX (world-class)

Goal: the experience feels magical. Apple-simple, Linear-polished, Stripe-clear, Vercel-aesthetic.

- [ ] Design system: tokens, typography, motion language (Framer Motion)
- [ ] Landing (hero with before/after reveal, the "bad photo → source file" moment)
- [ ] Dashboard (document history, status, search)
- [ ] Upload (drag-drop, paste, camera, multi-file, instant preview)
- [ ] Processing (live stage progress: restoring → reading → understanding → rebuilding)
- [ ] Results (split before/after, structured view, edit-before-export, downloads)
- [ ] Pricing + Settings
- [ ] Empty states, error states, optimistic UI, a11y pass

**Definition of done:** a first-time user completes upload→download without instructions and says "wow".

---

## Milestone M4 — Hardening, security, monetization

- [ ] **Auth:** sessions, protected routes, org/workspace model
- [ ] **Security (assume hostile users):**
  - [ ] MIME sniffing (content, not extension) + allowlist
  - [ ] upload size + page-count limits, zip/PDF bomb guards
  - [ ] sandbox the document parsers
  - [ ] antivirus hook (ClamAV)
  - [ ] strip/normalize EXIF + metadata
  - [ ] rate limiting (per-IP + per-user)
  - [ ] encryption at rest, short retention, audit log (PII: passports/IDs)
- [ ] **Performance:** result caching, OCR/inference batching, memory caps, autoscaling workers
- [ ] **Billing/plans:** Free (10 docs/mo), Pro (unlimited), Business (API + bulk), Enterprise (private deploy)
- [ ] **Testing:**
  - [ ] unit (each pipeline stage)
  - [ ] integration (upload→download)
  - [ ] E2E (Playwright)
  - [ ] fixture corpus: blurry, rotated, dark, tables, multilingual
  - [ ] target: **95%+ successful processing** on the corpus
- [ ] **Observability:** structured logs, traces, per-stage timing, error tracking
- [ ] CI/CD pipeline

**Definition of done:** can onboard a paying user safely; corpus passes 95%+; CI green.

---

## API surface (target)

| Method | Path | Purpose |
|---|---|---|
| POST | `/upload` | Store file, create document + job |
| POST | `/process/:id` | Enqueue processing |
| GET | `/document/:id` | Status + structured result |
| GET | `/download/pdf/:id` | Clean PDF |
| GET | `/download/docx/:id` | Editable DOCX |
| GET | `/download/json/:id` | Structured JSON |

## Risk register (live)

| Risk | Severity | Mitigation |
|---|---|---|
| GPU cost & VL latency | High | Batch, cache, text-only fast path for simple docs, quantization |
| VL hallucination on legal/ID docs | High | Ground every field to OCR box + confidence; flag low confidence; never auto-trust |
| Hostile uploads (bombs, polyglots, EXIF exploits) | High | MIME sniff, size caps, sandbox parsers, AV hook, strip metadata |
| PII / GDPR (passports, IDs) | High | Encrypt at rest, short retention, region pinning, audit log |
| Scope creep (13 phases) | Medium | Strict vertical slices; each milestone independently shippable |

---

## Current status

- **Active milestone:** M1.2 — OCR + searchable PDF + web UI (**code-complete**, pending live OCR run).
- **M0 DONE.** **M1.1 DONE** (verified end-to-end: upload → Redis → worker OpenCV restore → PDF → presigned download; visual before/after confirmed).
- **M1.2 implemented:** PaddleOCR stage (text+boxes+confidence, geometry preserved), text-mask background whitening, searchable PDF (image + invisible text layer via reportlab), and the web upload→poll→download flow. Worker modules byte-compile + `ruff` clean; web `tsc --noEmit` green.
- **Running locally now:** web :3000, api :8000, worker (Redis consumer), Postgres :5432, Redis + MinIO (docker).
- **Next action:** bring up the Docker worker (`paddleocr` + `reportlab` now in `apps/worker/pyproject.toml`) and run a real photo through it to confirm the OCR text layer is selectable and the whitened background looks clean; then start M2 (Qwen2.5-VL understanding + rich HTML/DOCX/JSON reconstruction).
- **Tooling note:** the worker AI stack (PaddleOCR) runs in the Docker worker image (python:3.12-slim) — native Windows + Python 3.14 lacks reliable wheels for paddle. The OCR stage degrades to a pass-through if paddle can't load, so the API/worker still run natively for non-OCR iteration.
