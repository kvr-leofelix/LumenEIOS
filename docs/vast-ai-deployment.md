# Deploying LumenEIOS on a Vast.ai GPU instance

This runs the whole app on one rented GPU machine:
- the FastAPI backend, port 8000
- one Qwen2.5-VL 3B AWQ model for worksheet OCR, Question Studio Beta, and the assistant
- the built frontend, port 3000

Commands run from the repo's `apps/lumeneios` folder unless noted.

> **Status:**
> - **Checked locally:** requirement files resolve for Linux x86_64 (Python 3.11 and 3.12), the backend test suite passes on a clean install, and the frontend builds.
> - **Not yet run on a real Vast.ai machine:** expect to adjust small details.

## 1. Rent the instance

| Setting | Choose |
|---|---|
| Template | A PyTorch / CUDA 12.8 image, e.g. `pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime`, or any Ubuntu + CUDA 12.8 image |
| GPU | 16 GB VRAM or more (RTX 4080/4090, A4000, L4). all three features share the same model |
| Driver | NVIDIA driver 570 or newer (shown on the offer; needed for CUDA 12.8) |
| Disk | 60 GB or more (PyTorch, the shared model, and app data) |
| Ports | Add `-p 8000:8000 -p 3000:3000` to the Docker options |

After it starts, open the instance's **IP & ports** panel. Vast maps 8000 and 3000 to random public ports, for example `203.0.113.7:41234 -> 8000`. Below, `PUBLIC_IP`, `API_PORT` and `WEB_PORT` mean those public values.

## 2. Get the code

The repo is private, so use a GitHub token or a deploy key:

```bash
git clone --branch main https://github.com/kvr-leofelix/arena.git   # always deploy main
cd arena/apps/lumeneios
nvidia-smi            # must list the GPU and a driver >= 570
```

## 3. Install the backend

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
pip install -r backend/requirements-ocr.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # expect 2.11.0+cu128 True
```

Install the OCR requirements **after** torch. The `triton==3.6.0` pin matches torch 2.11.0.

## 4. Cache the shared model

```bash
python -c 'from huggingface_hub import snapshot_download; snapshot_download("Qwen/Qwen2.5-VL-3B-Instruct-AWQ")'
```

## 5. Create `.env` — required before going public

Create `apps/lumeneios/.env`. The backend reads it from the folder you start it in.

```bash
APP_ENV=production
DEBUG=false
DEMO_MODE=false
SECRET_KEY=<paste output of: python -c "import secrets; print(secrets.token_urlsafe(48))">
BACKEND_CORS_ORIGINS=["http://PUBLIC_IP:WEB_PORT"]
QWEN_VL_MODEL_ID=Qwen/Qwen2.5-VL-3B-Instruct-AWQ
HF_TOKEN=
```

Why each line matters:

| Setting | If left at the code default |
|---|---|
| `APP_ENV=production` | Disables the team root login even when a development password is configured |
| `SECRET_KEY` | The default key is in the public code, so anyone could forge login tokens |
| `DEMO_MODE=false` | `true` lets requests with no login act as admin |
| `DEBUG=false` | Debug output can leak internals |
| `BACKEND_CORS_ORIGINS` | Default allows only localhost, so the browser blocks the deployed frontend. It must be a JSON list |

Also, `infrastructure/docker-compose.yml` sets `DEMO_MODE=true` and the public default secrets. Don't use it as-is on a public machine.

## 6. Start the backend

```bash
source .venv/bin/activate
nohup uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
curl http://127.0.0.1:8000/health
```

The database defaults to SQLite (`lumeneios.db` in this folder) and uploads to `storage_uploads/`. Both live on the instance's disk, so **they are lost when the instance is destroyed**. Back them up, or set `DATABASE_URL` to an external PostgreSQL.

## 7. Build and serve the frontend

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs
npm ci
VITE_API_URL=http://PUBLIC_IP:API_PORT/api/v1 VITE_DEMO_MODE=false npm run build
nohup npx vite preview --host 0.0.0.0 --port 3000 > frontend.log 2>&1 &
```

`VITE_API_URL` is baked in at build time. Rebuild if the public IP or port changes, for example after a restart.

Open `http://PUBLIC_IP:WEB_PORT`.

## 8. Check the GPU pipeline

```bash
RUN_QWEN_GPU_TEST=1 python -m pytest backend/tests/test_qwen_gpu_smoke.py -q   # loads the real 3B model
tail -f backend.log
```

The first OCR request downloads about 3 GB of Qwen weights from Hugging Face. Expect a long wait, then roughly 4 s per page.

## Known limits

- **HTTP only, no TLS.** Put it behind a reverse proxy with HTTPS before real student data goes on it.
- **One page at a time.** OCR runs one page at a time on the GPU, so large batches are slow (see `ocr-gpu-deployment.md`).
- **Students can call OCR preview.** `/ocr/extract-preview` now allows the `student` role, so any student account can use GPU time.
