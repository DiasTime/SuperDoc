# Graph Report - .  (2026-06-16)

## Corpus Check
- Corpus is ~8,995 words - fits in a single context window. You may not need a graph.

## Summary
- 369 nodes · 483 edges · 30 communities (22 shown, 8 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 50 edges (avg confidence: 0.77)
- Token cost: 97,241 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Job Lifecycle & Orchestration|Job Lifecycle & Orchestration]]
- [[_COMMUNITY_Image Restoration (OpenCV)|Image Restoration (OpenCV)]]
- [[_COMMUNITY_Web Upload UI & Flow|Web Upload UI & Flow]]
- [[_COMMUNITY_API Gateway & Logging|API Gateway & Logging]]
- [[_COMMUNITY_Pipeline Stage Framework|Pipeline Stage Framework]]
- [[_COMMUNITY_Web Dependencies|Web Dependencies]]
- [[_COMMUNITY_API Config  DB  Queue|API Config / DB / Queue]]
- [[_COMMUNITY_Web TS Config|Web TS Config]]
- [[_COMMUNITY_Root Project Config (Prisma)|Root Project Config (Prisma)]]
- [[_COMMUNITY_Worker Postgres DB|Worker Postgres DB]]
- [[_COMMUNITY_Settings & Worker Entry|Settings & Worker Entry]]
- [[_COMMUNITY_OCR (PaddleOCR)|OCR (PaddleOCR)]]
- [[_COMMUNITY_Shared-Types Package|Shared-Types Package]]
- [[_COMMUNITY_Shared-Types TS Config|Shared-Types TS Config]]
- [[_COMMUNITY_PDF Reconstruction|PDF Reconstruction]]
- [[_COMMUNITY_API Object Storage (S3MinIO)|API Object Storage (S3/MinIO)]]
- [[_COMMUNITY_Web Root Layout|Web Root Layout]]
- [[_COMMUNITY_Claude Settings|Claude Settings]]
- [[_COMMUNITY_Export Download Path|Export Download Path]]
- [[_COMMUNITY_Document Fetch Endpoint|Document Fetch Endpoint]]
- [[_COMMUNITY_Model Download Script|Model Download Script]]
- [[_COMMUNITY_App Logging Init|App Logging Init]]
- [[_COMMUNITY_Next.js Config|Next.js Config]]
- [[_COMMUNITY_Tailwind Config|Tailwind Config]]
- [[_COMMUNITY_Monorepo Tooling|Monorepo Tooling]]

## God Nodes (most connected - your core abstractions)
1. `compilerOptions` - 16 edges
2. `restore()` - 13 edges
3. `Stage` - 11 edges
4. `compilerOptions` - 11 edges
5. `PipelineContext` - 9 edges
6. `run_ocr()` - 9 edges
7. `whiten_background()` - 9 edges
8. `_bad_photo()` - 8 edges
9. `_conn()` - 8 edges
10. `searchable_pdf()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Four-stage pipeline (restore/OCR/understand/reconstruct)` --conceptually_related_to--> `build_default_pipeline`  [INFERRED]
  PLAN.md → apps/worker/worker/pipeline/stages.py
- `Reconstruction fidelity (readability > aesthetics > exact)` --rationale_for--> `Reconstruction stage`  [INFERRED]
  PLAN.md → apps/worker/worker/pipeline/stages.py
- `PaddleOCR engine choice` --rationale_for--> `run_ocr (PaddleOCR)`  [INFERRED]
  PLAN.md → apps/worker/worker/pipeline/ocr.py
- `Assume hostile users (MIME sniff, limits)` --rationale_for--> `sniff_image_type`  [INFERRED]
  PLAN.md → apps/api/app/security.py
- `Async pipeline (queue + workers)` --rationale_for--> `enqueue (Redis producer)`  [INFERRED]
  PLAN.md → apps/api/app/queue.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Four-stage reconstruction pipeline** — stages_imagerestoration, stages_ocr, stages_documentunderstanding, stages_reconstruction [EXTRACTED 1.00]
- **Upload to enqueue handoff** — main_upload, db_create_document_and_job, storage_put_bytes, queue_enqueue [INFERRED 0.85]
- **Worker job status lifecycle** — main_process_job, db_start_job, db_set_status, db_complete_job, db_fail_job [EXTRACTED 1.00]
- **Upload -> process -> poll document flow** — _components_uploader_start, _components_uploader_poll, src_index_uploadresponse, src_index_documentresponse [INFERRED 0.85]
- **Job stage progress tracker** — src_index_jobstatus, src_index_job_stages, _components_uploader_stageindex, app_page_home [INFERRED 0.75]

## Communities (30 total, 8 thin omitted)

### Community 0 - "Job Lifecycle & Orchestration"
Cohesion: 0.05
Nodes (52): bytes, str, PipelineContext, Stage (abstract), add_export (worker), complete_job (worker), create_document_and_job (api), fail_job (worker) (+44 more)

### Community 1 - "Image Restoration (OpenCV)"
Cohesion: 0.11
Nodes (32): bytes, ndarray, bytes, float, int, ndarray, _deskew(), _estimate_skew() (+24 more)

### Community 2 - "Web Upload UI & Flow"
Cohesion: 0.09
Nodes (28): Uploader.onFiles, Uploader.poll, Uploader.stageIndex, Uploader.start, Uploader (component), Home(), Phase, TRACKED (+20 more)

### Community 3 - "API Gateway & Logging"
Cohesion: 0.09
Nodes (25): configure_logging(), JsonFormatter, Structured JSON logging so logs are queryable in production., download(), get_document(), health(), process(), FastAPI gateway entrypoint.  Thin by design: auth, uploads, job CRUD, downloads. (+17 more)

### Community 4 - "Pipeline Stage Framework"
Cohesion: 0.13
Nodes (20): ABC, str, PipelineContext, Pipeline abstractions.  A job flows through an ordered list of Stages. Each stag, Carries state between stages for a single document., One step of the reconstruction pipeline., Transform the context. Must be idempotent where possible., Stage (+12 more)

### Community 5 - "Web Dependencies"
Cohesion: 0.09
Nodes (22): dependencies, @docres/shared-types, framer-motion, next, react, react-dom, devDependencies, autoprefixer (+14 more)

### Community 6 - "API Config / DB / Queue"
Cohesion: 0.15
Nodes (17): Centralized, validated settings loaded from environment., _conn(), create_document_and_job(), gen_id(), get_document(), get_export_key(), get_source_key(), Postgres access for the API (psycopg over the Prisma-owned schema). (+9 more)

### Community 7 - "Web TS Config"
Cohesion: 0.10
Nodes (19): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+11 more)

### Community 8 - "Root Project Config (Prisma)"
Cohesion: 0.12
Nodes (16): devDependencies, prisma, typescript, engines, node, name, packageManager, private (+8 more)

### Community 9 - "Worker Postgres DB"
Cohesion: 0.25
Nodes (15): Any, Connection, int, str, add_export(), complete_job(), _conn(), fail_job() (+7 more)

### Community 10 - "Settings & Worker Entry"
Cohesion: 0.15
Nodes (11): Settings, str, int, BaseSettings, Settings (api config), FrameType, Worker settings — mirrors the API where infra is shared., Settings (+3 more)

### Community 11 - "OCR (PaddleOCR)"
Cohesion: 0.22
Nodes (12): Any, bytes, float, int, str, _get_engine(), OCR engine (PaddleOCR) + text-mask background cleanup.  PaddleOCR is heavy (pull, Lazily construct a single PaddleOCR instance (model load is expensive). (+4 more)

### Community 12 - "Shared-Types Package"
Cohesion: 0.15
Nodes (12): devDependencies, typescript, exports, main, name, private, scripts, build (+4 more)

### Community 13 - "Shared-Types TS Config"
Cohesion: 0.15
Nodes (12): compilerOptions, declaration, esModuleInterop, forceConsistentCasingInFileNames, lib, module, moduleResolution, noEmit (+4 more)

### Community 14 - "PDF Reconstruction"
Cohesion: 0.27
Nodes (8): Any, bytes, str, image_to_pdf(), Reconstruction outputs.  M1.1: wrap the restored page image into a clean PDF (Pi, Image-only PDF (no text layer). Fallback when OCR produced nothing., Restored image + invisible, positioned OCR text → searchable PDF.      Boxes are, searchable_pdf()

### Community 15 - "API Object Storage (S3/MinIO)"
Cohesion: 0.28
Nodes (8): _client(), presigned_get(), put_bytes(), Object storage (MinIO/S3) access for the API., Time-limited download URL. Signed against the public endpoint so the     browser, bytes, int, str

### Community 18 - "Export Download Path"
Cohesion: 0.67
Nodes (3): get_export_key (api), download endpoint, presigned_get (api storage)

## Knowledge Gaps
- **135 isolated node(s):** `allow`, `str`, `Connection`, `int`, `Any` (+130 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `process_job()` connect `Pipeline Stage Framework` to `Settings & Worker Entry`?**
  _High betweenness centrality (0.175) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `restore()` (e.g. with `.run()` and `test_image_only_pdf_fallback()`) actually correct?**
  _`restore()` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `Stage` (e.g. with `DocumentUnderstanding` and `ImageRestoration`) actually correct?**
  _`Stage` has 5 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `PipelineContext` (e.g. with `DocumentUnderstanding` and `ImageRestoration`) actually correct?**
  _`PipelineContext` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `allow`, `str`, `Centralized, validated settings loaded from environment.` to the rest of the system?**
  _184 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Job Lifecycle & Orchestration` be split into smaller, more focused modules?**
  _Cohesion score 0.05152394775036284 - nodes in this community are weakly interconnected._
- **Should `Image Restoration (OpenCV)` be split into smaller, more focused modules?**
  _Cohesion score 0.11051693404634581 - nodes in this community are weakly interconnected._