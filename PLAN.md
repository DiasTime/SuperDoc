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

| Decision                | Choice                                                               | Rationale                                                                                               |
| -------------------------| ----------------------------------------------------------------------| ---------------------------------------------------------------------------------------------------------|
| AI vision model         | **Qwen-VL** (Ollama dev · vLLM prod)                                 | Self-hosted for full control + privacy (passports/IDs/contracts). Behind an OpenAI-compatible `VLProvider` so it's swappable: local Ollama (`ollama pull qwen2.5vl`) for dev, vLLM on a GPU box (~16GB+ VRAM) at scale. |
| OCR engine              | PaddleOCR                                                            | Strong multilingual OCR with box + confidence output.                                                   |
| Pipeline execution      | **Async** (queue + workers)                                          | 7B VL inference is seconds–minutes/page; never block an HTTP request.                                   |
| Reconstruction fidelity | readability > aesthetics > exact replication                         | Pixel-perfect = months. Semantic HTML→PDF = days and looks professional.                                |
| Repo shape              | **Monorepo** (pnpm workspaces + Python uv)                           | Shared types across front/back, one `docker compose up`.                                                |
| Storage                 | PostgreSQL (metadata) + S3-compatible object store (files/artifacts) | Don't store blobs in Postgres. MinIO locally, S3 in prod.                                               |

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
- [x] Worker stage 1 — **Image restoration** (OpenCV, `worker/pipeline/restoration.py`):
  - [x] **page detection** — HSV-saturation mask (white paper vs. coloured desk) + largest connected component + 4 extreme corners → perspective warp + crop; Canny fallback
  - [x] **deskew** (projection-profile search — robust across OpenCV versions)
  - [x] edge-preserving **denoise** (bilateral) + local contrast (CLAHE) + unsharp
  - [x] **white-balance** (per-channel illumination flatten + white-point lift) so grey/dim scans go truly white
  - [x] **border-band cleanup** — whiten neutral grey background the crop included (low-saturation only, never colour content)
  - [x] **three output modes** (`RESTORE_MODE`): **`color`** (default — keeps stamps/signatures/photos), `gray`, `binary`; working res up to `RESTORE_MAX_SIDE=3500`
  - [ ] auto-orient (EXIF); robust crop when page ≈ background colour (needs AI doc-segmentation — see M2 note)
- [x] Worker stage 4 — **Reconstruction (basic)**: restored page → clean PDF (Pillow)
- [x] `GET /document/:id` (status + progress + exports), `GET /download/pdf/:id` (presigned redirect)
- [x] Real async run verified: skewed/noisy/shadowed photo → deskewed clean PDF (visual before/after confirmed)

### M1.2 — OCR + text-based reconstruction (DONE ✅, verified live in the Docker worker)
- [x] Worker stage 2 — **OCR** (PaddleOCR): text + boxes + confidence, geometry preserved (`worker/pipeline/ocr.py`; lazy import, degrades to pass-through if paddle is unavailable so the job still completes)
- [x] **Searchable PDF**: restored image + invisible, per-line OCR text layer, horizontally scaled to its box (`reconstruct.searchable_pdf`, reportlab); falls back to image-only PDF when OCR is empty
- [x] **Verified live** — Docker worker reads a real page → selectable text layer (e.g. 2255 chars extracted), confirmed via `pypdf` round-trip
- [~] `whiten_background` (OCR-driven mask whitening) — **removed from the pipeline**: it shredded photos/maps (light areas outside text boxes blew to noisy white). Restoration now flattens the background, so the clean restored page goes straight under the text layer. (Function kept + tested for reference.)
- [ ] ordered text blocks → **semantic HTML → PDF/DOCX** — deferred to M2 (rich, structure-aware reconstruction)
- [x] Web: upload (drag-drop/click) → live stage tracker (poll `GET /document/:id`) → result + PDF download (`apps/web/app/_components/Uploader.tsx`)

**Definition of done:** upload a skewed phone photo → get a clean, readable PDF back. **MET** — verified end-to-end through the Docker worker (clean colour scan + selectable text).

---

## Milestone M2 — Document Intelligence (the magic)

Goal: from "text on a page" to "typed, structured document".

- [x] VL provider interface in worker — swappable / mockable (`worker/pipeline/vl.py`: `VLProvider` + `OpenAICompatVL`; `understand()` degrades to UNKNOWN if the endpoint is down; image downscaled + OCR text capped to fit the context window)
- [x] Serve via **Ollama** (dev) over the OpenAI-compatible API — **verified live** end-to-end in the Docker worker (`qwen2.5vl:3b`, ~150MB models pulled on first run)
- [ ] Stand up **vLLM** (GPU, quantized fallback) for prod throughput — same `VLProvider`, just a different `VL_ENDPOINT`
- [~] Stage 3 — **Document understanding**: OCR + image → structured JSON (`DocumentUnderstanding` stage live)
  - [x] doc-type detection: contract, invoice, act, certificate, passport, ID, form, commercial offer (returns UNKNOWN honestly when none fit)
  - [x] hierarchy: title → sections → headings → paragraphs
  - [x] tables, key–value pairs, signatures/stamps (basic — cells/spans simplified)
  - [ ] **grounding:** every field references an OCR box + confidence — fields carry confidence; box linkage still TODO
- [x] Metadata extraction + document **summary** (verified: real summaries on live docs)
- [ ] Stage 4+ — **Reconstruction (rich)**: structure-aware HTML/CSS templates per doc type
- [x] **JSON export** — structured `DocumentStructure` artifact (`reconstruct.structure_to_json`, registered in `exports`)
- [ ] DOCX export (`python-docx`)
- [x] `GET /download/json/:id` (served by the existing `/download/{fmt}` handler) · [ ] `GET /download/docx/:id`
- [x] API surfaces `structure` on `GET /document/:id`
- [ ] Web: structured result view (sections, tables, confidence flags), all download formats

> **AI doc-segmentation (deferred):** robust page detection when the paper ≈ background colour (e.g. white sheet on a white desk) is beyond classical CV. A deep document-segmentation model is the fix; tested Qwen-VL 3B for corner grounding — not precise enough. Workaround for now: shoot on a contrasting surface.

**Definition of done:** upload an invoice photo → typed JSON with line items, a clean DOCX, a PDF, and a summary; low-confidence fields flagged. **(JSON + colour PDF + summary done once a VL model is pulled; DOCX + rich HTML + box-grounding remain.)**

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

- **Active milestone:** M2 — Document understanding (in progress). Full pipe runs end-to-end in the Docker worker: **restore (colour) → OCR (PaddleOCR) → understand (Qwen-VL/Ollama) → reconstruct (searchable colour PDF + JSON)**.
- **M0 DONE. M1.1 DONE. M1.2 DONE** (verified live: clean colour scan + selectable text layer).
- **M2 so far:** swappable `VLProvider` (Ollama dev / vLLM prod) with graceful degrade; `DocumentUnderstanding` produces typed `DocumentStructure` (type, sections, key-values, signatures, metadata) + summary; structured JSON export; API surfaces `structure`. **Remaining:** DOCX export, rich structure-aware HTML reconstruction, box-grounding, vLLM prod path.
- **Restoration overhaul (this cycle):** HSV page detection + perspective crop + deskew, three output modes (**colour default**, gray, binary), white-balance, edge-preserving denoise, border-band cleanup. Colour mode keeps stamps/signatures/photos.
- **Running locally now:** web :3000, api :8000 (native); **Docker worker** `docres-worker-ocr` (OCR + VL); Postgres :5432 (native), Redis + MinIO (docker), Ollama :11434 (host, `qwen2.5vl:3b`).
- **Worker deps note:** PaddleOCR needs `paddlepaddle` + `setuptools` explicitly, and **`numpy<2`** (paddle 2.6 segfaults on numpy 2.x). Runs in the Docker image (python:3.12-slim); native Windows/Python 3.14 lacks paddle wheels, so OCR/VL degrade gracefully when run natively.
- **Docker worker wiring:** joins the `superdoc_default` compose network (reaches `redis`/`minio` by name) and uses `host.docker.internal` for native Postgres + Ollama; OCR models persisted in the `docres_paddle` volume.
- **Next action:** DOCX export + rich HTML reconstruction; box-grounding of extracted fields; stand up vLLM for the prod VL path.
