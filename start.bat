@echo off
REM ===========================================================================
REM  Document Resurrection AI  -  start the full local stack
REM
REM  Brings up:
REM    Redis + MinIO        (Docker:  redis, minio, minio-init)
REM    Worker  OCR + VL     (Docker:  docres-worker-ocr)
REM    API     FastAPI :8000 (native, own window)
REM    Web     Next.js :3000 (native, own window)
REM
REM  Assumed already running as host services (auto-start on Windows):
REM    Postgres :5432   |   Ollama :11434 (model qwen2.5vl:3b)
REM ===========================================================================
setlocal
cd /d "%~dp0"

echo.
echo === Checking Docker ===
docker info >nul 2>&1
if errorlevel 1 (
  echo   ERROR: Docker does not appear to be running.
  echo   Start Docker Desktop, then run this script again.
  echo.
  pause
  exit /b 1
)
echo   Docker OK.

echo.
echo === [1/4] Infra: Redis + MinIO (creates the superdoc_default network) ===
docker compose up -d redis minio minio-init
if errorlevel 1 (
  echo   ERROR: failed to start infra containers.
  pause
  exit /b 1
)

echo.
echo === [2/4] Worker: OCR + VL pipeline ===
docker image inspect docres-worker >nul 2>&1
if errorlevel 1 (
  echo   Worker image not found - building it once ^(this can take a few minutes^)...
  docker build -t docres-worker apps\worker
  if errorlevel 1 (
    echo   ERROR: worker image build failed.
    pause
    exit /b 1
  )
)
REM Recreate the container fresh (the PaddleOCR model cache lives in the
REM docres_paddle volume, so nothing is lost by removing the container).
docker rm -f docres-worker-ocr >nul 2>&1
docker run -d --name docres-worker-ocr --network superdoc_default --add-host host.docker.internal:host-gateway --env-file .env.worker -v docres_paddle:/root/.paddleocr docres-worker
if errorlevel 1 (
  echo   ERROR: failed to start the worker container.
  pause
  exit /b 1
)
echo   Worker started.

echo.
echo === [3/4] API gateway: FastAPI on :8000 (new window) ===
start "DocRes API :8000" cmd /k "apps\api\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps\api --host 0.0.0.0 --port 8000"

echo.
echo === [4/4] Web: Next.js on :3000 (new window) ===
REM pnpm isn't on PATH here; run the web package's own dev script via npm.
start "DocRes Web :3000" cmd /k "cd /d apps\web && npm run dev"

echo.
echo === Waiting for the stack to come up... ===
REM give API/Web a few seconds to boot before opening the browser
timeout /t 6 /nobreak >nul

echo.
echo ===========================================================================
echo   Stack is starting:
echo     Web    ^> http://localhost:3000
echo     API    ^> http://localhost:8000/docs   (health: /health)
echo     MinIO  ^> http://localhost:9001         (minioadmin / minioadmin)
echo.
echo   Host services (must be running):
echo     Postgres :5432   |   Ollama :11434 (qwen2.5vl:3b)
echo.
echo   API and Web each run in their own window - close those to stop them.
echo   Worker + infra run in Docker (docker ps to view, docker stop to halt).
echo ===========================================================================
echo.
start "" http://localhost:3000
endlocal
