# 🤖 Internal Agent Service

> Local-first internal company assistant — built with **FastAPI** and local **Ollama** LLMs, with guaranteed Persian responses, streaming, and professional structured logging.

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.138-009688?logo=fastapi&logoColor=white">
  <img alt="Ollama" src="https://img.shields.io/badge/Ollama-local%20LLM-black?logo=ollama&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green">
</p>

<p align="center">
  <b>🌐 Language / زبان:</b>
  <a href="#-english">English</a> ·
  <a href="#-فارسی">فارسی</a>
</p>

---

## 🇬🇧 English

### ✨ Features

| Feature | Description |
|---------|-------------|
| 🧠 **Multiple specialized agents** | `general` · `hr` · `crm` · `finance`, each with its own system prompt |
| 🇮🇷 **Always Persian responses** | Replies in Persian regardless of the input language |
| 🔒 **Fully local (offline)** | No external API or internet required; data never leaves your machine |
| ⚡ **Streaming** | Dedicated endpoint for token-by-token responses and lower perceived latency |
| 📊 **Structured logging** | JSONL logs with `request_id`, latency, token usage, and automatic file rotation |
| 🛠️ **Custom system prompt** | Override an agent's behavior per request |
| 🚀 **Automatic warm-up** | Model is preloaded on startup so the first request is fast |

### 🏗️ Architecture

```
┌──────────────┐      HTTP       ┌─────────────────────┐      OpenAI-compatible      ┌──────────────┐
│  Client / UI │  ───────────▶   │   FastAPI (app.py)  │  ────────────────────────▶  │    Ollama    │
│   (curl/web) │  ◀───────────   │  middleware + agents│  ◀────────────────────────  │ (local LLM)  │
└──────────────┘                 └─────────┬───────────┘                             └──────────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  logging_config  │
                                  │  app.log /       │
                                  │  llm.jsonl       │
                                  └──────────────────┘
```

### 📋 Prerequisites

- **Python** 3.10 or newer
- **[Ollama](https://ollama.com)** installed and running
- At least one downloaded model (default: `qwen2.5:3b`)

### 🚀 Getting Started

**1. Pull a model and run Ollama**
```bash
ollama serve            # usually runs automatically
ollama pull qwen2.5:3b  # default lightweight & fast model
```

**2. Install dependencies**
```bash
cd llm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**3. Run the service**
```bash
uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

The service starts at **http://localhost:8001** and interactive Swagger docs are available at:

> 📚 **http://localhost:8001/docs**

### 🔌 API

#### `GET /` — Health check
```json
{ "status": "ok", "service": "internal-agent" }
```

#### `POST /chat` — Standard chat

**Request body:**
```json
{
  "message": "What are the company working hours?",
  "agent_name": "hr",
  "system_prompt": null
}
```

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `message` | string | ✅ | The user message |
| `agent_name` | string | ❌ | One of `general` / `hr` / `crm` / `finance` (default: `general`) |
| `system_prompt` | string | ❌ | If set, overrides the agent's default prompt |

**Example:**
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "How many sick-leave days are allowed?", "agent_name": "hr"}'
```

**Response:**
```json
{ "response": "According to company policy, ..." }
```

> Every response includes an `X-Request-ID` header for log correlation.

#### `POST /chat/stream` — Streaming response

Same body as `/chat`, but the response is streamed as raw text, token by token.

```bash
curl -N -X POST http://localhost:8001/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Say one sentence about leave policy", "agent_name": "hr"}'
```

### 🤝 Agents

| Name | Specialty |
|------|-----------|
| `general` | General company assistant |
| `hr` | Human resources, leave, employee policies |
| `crm` | Customer information and relations |
| `finance` | Accounting and financial matters |

All agents are forced to answer **in Persian only**.

### ⚙️ Configuration (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible Ollama API URL |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Model to use |
| `MAX_TOKENS` | `512` | Max response length (controls speed) |
| `TEMPERATURE` | `0.3` | Response creativity |
| `OLLAMA_KEEP_ALIVE` | `30m` | How long the model stays in RAM (`-1` = forever) |
| `LLM_REQUEST_TIMEOUT` | `120` | Model call timeout (seconds) |
| `LOG_DIR` | `logs` | Log files directory |
| `LOG_LEVEL` | `INFO` | Log level |
| `LOG_MAX_BYTES` | `10485760` | Max size per log file (10MB) |
| `LOG_BACKUP_COUNT` | `5` | Number of rotated log backups |

**Override example:**
```bash
OLLAMA_MODEL=qwen2.5:7b MAX_TOKENS=1024 uvicorn app:app --port 8001
```

### 📊 Logs

All events are recorded under `logs/`:

| File | Content |
|------|---------|
| `logs/app.log` | HTTP events (request start/end, errors) as JSON |
| `logs/llm.jsonl` | Full model interactions: prompt, response, latency, token usage, errors |

**Sample `llm.jsonl` record:**
```json
{
  "timestamp": "2026-06-21T04:48:13Z",
  "level": "INFO",
  "request_id": "f8d895a1...",
  "event": "llm_response",
  "agent_name": "hr",
  "model": "qwen2.5:3b",
  "latency_ms": 16690.37,
  "usage": { "prompt_tokens": 41, "completion_tokens": 16, "total_tokens": 57 }
}
```

> On errors, the `error_type`, error message, and full **traceback** are written to both the log and the console.

### ⚡ Performance Tips

Running LLMs on **CPU** is slow; speed mostly depends on hardware.

- ✅ A **smaller model** has the biggest impact (`qwen2.5:3b` instead of `gemma2:9b`).
- ✅ Use the **`/chat/stream`** endpoint for a better user experience.
- ✅ Keep `MAX_TOKENS` as low as practical.
- ✅ `OLLAMA_KEEP_ALIVE` keeps the model in RAM and avoids reload cost.
- 💡 For high performance, a **GPU with enough VRAM** (e.g. RTX 3060 12GB) is recommended.

### 🖥️ Recommended Hardware

LLM inference speed depends mostly on the **GPU and its VRAM** — not the CPU. The model must fit entirely in VRAM to run fast.

| Tier | GPU | RAM | Suitable for |
|------|-----|-----|--------------|
| 💰 **Budget (best value)** | RTX 3060 12GB / RTX 4060 Ti 16GB | 32GB + NVMe SSD | Models up to 14B smoothly, 7–8B very fast. Ideal for this internal service. |
| ⚙️ **Mid-range (small production)** | RTX 4090 / 5090 24GB (or 4080 Super 16GB) | 64GB | 32B comfortably, 70B with heavy quantization; multiple concurrent users. |
| 🏢 **Professional / multi-user** | RTX A6000 / 6000 Ada 48GB (or 2× 24GB) | 64GB+ | Full-quality 70B models. |
| 🍎 **Mac (compact, low-power)** | Apple M-series, 64GB+ unified memory | — | Great for LLMs thanks to unified memory; can run 70B (slower than RTX). |

**Don't want to buy hardware?**
- ☁️ **Rented GPU cloud** (RunPod, Vast.ai, Lambda): rent an A10/L4/A100 hourly and run Ollama there — cost-effective for variable load.
- 🌐 **Cloud API**: if data privacy is not a concern, a cheap hosted API gives the fastest results with zero hardware.

> **Recommendation for this project:** for a Persian internal company assistant, expensive hardware is not required —
> **RTX 3060 12GB or 4060 Ti 16GB + 32GB RAM + NVMe SSD** is more than enough.

### 📁 Project Structure

```
llm/
├── app.py              # FastAPI app, agents and endpoints
├── logging_config.py   # Structured logging (JSONL + console)
├── requirements.txt    # Project dependencies
├── logs/               # Log files (auto-created)
│   ├── app.log
│   └── llm.jsonl
└── README.md
```

### 📝 License

MIT

---

## 🇮🇷 فارسی

> سرویس دستیار هوشمند داخلی شرکت — مبتنی بر **FastAPI** و مدل‌های زبانی محلی **Ollama**، با پاسخ‌دهی کاملاً فارسی، استریمینگ و سیستم لاگ حرفه‌ای.

### ✨ امکانات

| ویژگی | توضیح |
|------|-------|
| 🧠 **چند Agent تخصصی** | `general` · `hr` · `crm` · `finance` با system prompt اختصاصی |
| 🇮🇷 **پاسخ همیشه فارسی** | فارغ از زبان ورودی کاربر، پاسخ تضمینی به فارسی |
| 🔒 **کاملاً محلی (Offline)** | بدون نیاز به API خارجی یا اینترنت؛ داده‌ها از سیستم خارج نمی‌شوند |
| ⚡ **استریمینگ** | endpoint جداگانه برای پاسخ توکن‌به‌توکن و کاهش تأخیر محسوس |
| 📊 **لاگ ساختاریافته** | JSONL با `request_id`، latency، مصرف توکن و چرخش خودکار فایل |
| 🛠️ **system prompt سفارشی** | امکان override کردن رفتار agent در هر درخواست |
| 🚀 **Warm-up خودکار** | بارگذاری مدل هنگام استارت برای سرعت اولین درخواست |

### 🏗️ معماری

```
┌──────────────┐      HTTP       ┌─────────────────────┐      OpenAI-compatible      ┌──────────────┐
│  Client / UI │  ───────────▶   │   FastAPI (app.py)  │  ────────────────────────▶  │    Ollama    │
│   (curl/web) │  ◀───────────   │  middleware + agents│  ◀────────────────────────  │ (local LLM)  │
└──────────────┘                 └─────────┬───────────┘                             └──────────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  logging_config  │
                                  │  app.log /       │
                                  │  llm.jsonl       │
                                  └──────────────────┘
```

### 📋 پیش‌نیازها

- **Python** نسخهٔ ۳.۱۰ یا بالاتر
- **[Ollama](https://ollama.com)** نصب‌شده و در حال اجرا
- حداقل یک مدل دانلودشده (پیش‌فرض: `qwen2.5:3b`)

### 🚀 راه‌اندازی

**۱. دریافت مدل و اجرای Ollama**
```bash
ollama serve            # معمولاً به‌صورت خودکار اجرا است
ollama pull qwen2.5:3b  # مدل پیش‌فرض، سبک و سریع
```

**۲. نصب وابستگی‌ها**
```bash
cd llm
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**۳. اجرای سرویس**
```bash
uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

سرویس روی **http://localhost:8001** بالا می‌آید و مستندات تعاملی Swagger در آدرس زیر در دسترس است:

> 📚 **http://localhost:8001/docs**

### 🔌 API

#### `GET /` — بررسی سلامت
```json
{ "status": "ok", "service": "internal-agent" }
```

#### `POST /chat` — گفت‌وگوی معمولی

**بدنهٔ درخواست:**
```json
{
  "message": "ساعت کاری شرکت چطور است؟",
  "agent_name": "hr",
  "system_prompt": null
}
```

| فیلد | نوع | اجباری | توضیح |
|------|-----|:------:|-------|
| `message` | string | ✅ | پیام کاربر |
| `agent_name` | string | ❌ | یکی از `general` / `hr` / `crm` / `finance` (پیش‌فرض: `general`) |
| `system_prompt` | string | ❌ | در صورت مقداردهی، جایگزین prompt پیش‌فرض agent می‌شود |

**نمونه:**
```bash
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "مرخصی استعلاجی چند روز است؟", "agent_name": "hr"}'
```

**پاسخ:**
```json
{ "response": "بر اساس مقررات شرکت، ..." }
```

> هر پاسخ دارای هدر `X-Request-ID` برای ردیابی در لاگ‌هاست.

#### `POST /chat/stream` — پاسخ استریمی

ساختار بدنه دقیقاً مثل `/chat` است، اما پاسخ به‌صورت متن خام و توکن‌به‌توکن ارسال می‌شود.

```bash
curl -N -X POST http://localhost:8001/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "یک جمله درباره مرخصی بگو", "agent_name": "hr"}'
```

### 🤝 Agentها

| نام | تخصص |
|-----|------|
| `general` | دستیار عمومی شرکت |
| `hr` | منابع انسانی، مرخصی، مقررات کارکنان |
| `crm` | اطلاعات و امور مشتریان |
| `finance` | حسابداری و امور مالی |

همهٔ agentها به‌صورت اجباری **فقط به فارسی** پاسخ می‌دهند.

### ⚙️ پیکربندی (متغیرهای محیطی)

| متغیر | پیش‌فرض | توضیح |
|-------|---------|-------|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1` | آدرس API سازگار با OpenAI در Ollama |
| `OLLAMA_MODEL` | `qwen2.5:3b` | مدل مورد استفاده |
| `MAX_TOKENS` | `512` | حداکثر طول پاسخ (کنترل سرعت) |
| `TEMPERATURE` | `0.3` | میزان خلاقیت پاسخ |
| `OLLAMA_KEEP_ALIVE` | `30m` | مدت ماندگاری مدل در رم (`-1` = همیشه) |
| `LLM_REQUEST_TIMEOUT` | `120` | timeout فراخوانی مدل (ثانیه) |
| `LOG_DIR` | `logs` | پوشهٔ فایل‌های لاگ |
| `LOG_LEVEL` | `INFO` | سطح لاگ |
| `LOG_MAX_BYTES` | `10485760` | حداکثر حجم هر فایل لاگ (۱۰MB) |
| `LOG_BACKUP_COUNT` | `5` | تعداد نسخه‌های پشتیبان لاگ |

**نمونهٔ override:**
```bash
OLLAMA_MODEL=qwen2.5:7b MAX_TOKENS=1024 uvicorn app:app --port 8001
```

### 📊 لاگ‌ها

تمام رویدادها در پوشهٔ `logs/` ثبت می‌شوند:

| فایل | محتوا |
|------|-------|
| `logs/app.log` | رویدادهای HTTP (شروع/پایان درخواست، خطاها) به‌صورت JSON |
| `logs/llm.jsonl` | تعامل کامل با مدل: prompt، پاسخ، latency، مصرف توکن، خطاها |

**نمونهٔ رکورد `llm.jsonl`:**
```json
{
  "timestamp": "2026-06-21T04:48:13Z",
  "level": "INFO",
  "request_id": "f8d895a1...",
  "event": "llm_response",
  "agent_name": "hr",
  "model": "qwen2.5:3b",
  "latency_ms": 16690.37,
  "usage": { "prompt_tokens": 41, "completion_tokens": 16, "total_tokens": 57 }
}
```

> در حالت خطا، علاوه بر `error_type` و متن خطا، **traceback کامل** هم در لاگ و کنسول نمایش داده می‌شود.

### ⚡ نکات کارایی

اجرای مدل‌های زبانی روی **CPU** کند است؛ سرعت عمدتاً به سخت‌افزار وابسته است.

- ✅ **مدل کوچک‌تر** بزرگ‌ترین تأثیر را دارد (`qwen2.5:3b` به‌جای `gemma2:9b`).
- ✅ از endpoint **`/chat/stream`** برای تجربهٔ کاربری بهتر استفاده کنید.
- ✅ `MAX_TOKENS` را تا حد لازم پایین نگه دارید.
- ✅ `OLLAMA_KEEP_ALIVE` مدل را در رم نگه می‌دارد و بارگذاری مجدد را حذف می‌کند.
- 💡 برای کارایی بالا، یک **GPU با VRAM کافی** (مثل RTX 3060 12GB) توصیه می‌شود.

### 🖥️ سخت‌افزار پیشنهادی

سرعت استنتاج مدل عمدتاً به **GPU و مقدار VRAM** آن بستگی دارد، نه CPU. مدل باید کامل در VRAM جا شود تا سریع اجرا گردد.

| سطح | GPU | RAM | مناسب برای |
|-----|-----|-----|-----------|
| 💰 **اقتصادی (بهترین قیمت/کارایی)** | RTX 3060 12GB / RTX 4060 Ti 16GB | ۳۲GB + SSD NVMe | مدل‌های تا ۱۴B روان و ۷–۸B خیلی سریع. ایده‌آل برای این سرویس داخلی. |
| ⚙️ **میان‌رده (تولید کوچک)** | RTX 4090 / 5090 24GB (یا 4080 Super 16GB) | ۶۴GB | مدل‌های ۳۲B راحت و ۷۰B با کوانت سنگین؛ چند کاربر هم‌زمان. |
| 🏢 **حرفه‌ای / چند کاربر** | RTX A6000 / 6000 Ada 48GB (یا دو کارت ۲۴GB) | ۶۴GB+ | مدل‌های ۷۰B با کیفیت کامل. |
| 🍎 **مک (جمع‌وجور و کم‌مصرف)** | Apple M-series با ۶۴GB+ حافظهٔ یکپارچه | — | به‌خاطر unified memory برای LLM عالی؛ می‌تواند ۷۰B را اجرا کند (کندتر از RTX). |

**نمی‌خواهید سخت‌افزار بخرید؟**
- ☁️ **سرور ابری GPU اجاره‌ای** (RunPod، Vast.ai، Lambda): یک کارت A10/L4/A100 ساعتی اجاره کنید و Ollama را همان‌جا اجرا کنید — برای بار متغیر مقرون‌به‌صرفه است.
- 🌐 **API ابری**: اگر حریم خصوصی داده مانع نیست، یک API ارزان سریع‌ترین نتیجه را بدون هیچ سخت‌افزاری می‌دهد.

> **جمع‌بندی برای این پروژه:** برای یک «دستیار داخلی شرکت» فارسی، نیازی به سخت‌افزار گران نیست —
> **RTX 3060 12GB یا 4060 Ti 16GB + 32GB RAM + SSD NVMe** کاملاً کافی است.

### 📁 ساختار پروژه

```
llm/
├── app.py              # اپلیکیشن FastAPI، agentها و endpointها
├── logging_config.py   # سیستم لاگ ساختاریافته (JSONL + کنسول)
├── requirements.txt    # وابستگی‌های پروژه
├── logs/               # فایل‌های لاگ (خودکار ساخته می‌شود)
│   ├── app.log
│   └── llm.jsonl
└── README.md
```

### 📝 License

MIT
# dastyar
