# infra

Ops helpers and the GPU-only AI serving layer.

## Self-hosting Qwen2.5-VL 7B (M2)

The vision model is **self-hosted** (locked decision — see `PLAN.md`). It runs as
a separate service because it requires an NVIDIA GPU (~16GB+ VRAM for the 7B model;
use AWQ/GPTQ quantization to fit smaller cards).

Recommended serving: **vLLM** with an OpenAI-compatible endpoint, so the worker
talks to it via the standard `openai` client (`VL_ENDPOINT`).

```bash
# download weights into ./models (gitignored)
bash infra/download_model.sh

# bring the whole stack up WITH the GPU model
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up
```

`docker-compose.gpu.yml` (added in M2) defines the `vllm` service with
`deploy.resources.reservations.devices` pinned to the NVIDIA runtime.
