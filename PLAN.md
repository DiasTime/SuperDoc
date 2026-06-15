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

- [ ] Object storage client (presigned upload + artifact put/get) — MinIO/S3
- [ ] `POST /upload` → store file, create `document` + `processing_job`
- [ ] `POST /process/:id` → enqueue job
- [ ] Worker stage 1 — **Image restoration** (OpenCV):
  - [ ] auto-orient (EXIF) + grayscale path
  - [ ] denoise (Non-Local Means / bilateral)
  - [ ] shadow removal (background division)
  - [ ] brightness/contrast normalization (CLAHE)
  - [ ] document edge detection → perspective correction (4-point warp)
  - [ ] auto-crop + deskew (Hough / min-area-rect)
- [ ] Worker stage 2 — **OCR** (PaddleOCR): text + bounding boxes + confidence, geometry preserved
- [ ] Worker stage 4 — **Reconstruction (basic)**: ordered text blocks → semantic HTML → PDF
- [ ] `GET /document/:id` (status + result), `GET /download/pdf/:id`
- [ ] Web: upload form, processing/poll screen, result + PDF download

**Definition of done:** upload a skewed phone photo → get a clean, readable PDF back.

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

- **Active milestone:** M0 — Foundation (≈95% done)
- **Verified live:** Postgres 18 + schema (5 tables); FastAPI `/health` 200; Next.js web on :3000; shared-types typecheck; git initialized.
- **Remaining for M0:** Redis + MinIO via `docker compose up` (blocked on WSL install).
- **Next action:** install WSL (`wsl --install`, admin, reboot) + Python 3.12 → `docker compose up` → begin M1 (upload → restore → OCR → PDF).
