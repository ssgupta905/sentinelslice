# SentinelSlice

> **Operational memory bank with agentic incident remediation.**  
> Combines Elasticsearch's native semantic search (BBQ-HNSW vectors, RRF) with a 3-agent LLM workflow to detect, match, and remediate infrastructure incidents in under 4 seconds.

---

## Architecture

```
Raw Logs / Symptoms
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Backend                                            │
│                                                             │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │  Elastic    │   │  Inference   │   │  Agent         │  │
│  │  Service    │   │  Service     │   │  Service       │  │
│  │             │   │              │   │                │  │
│  │  BBQ-HNSW   │   │  Open Inf.   │   │  ① Retrieval  │  │
│  │  RRF Hybrid │   │  API config  │   │  ② Analysis   │  │
│  │  Ingest     │   │              │   │  ③ Action      │  │
│  │  Pipeline   │   │              │   │                │  │
│  └─────────────┘   └──────────────┘   └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
       │                                        │
       ▼                                        ▼
Elasticsearch Cloud                         OpenAI GPT-4o
(BBQ vectors, BM25,                     (Pattern analysis,
 semantic_text)                          Runbook generation)
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend (HTML/CSS/JS)                                     │
│  • Analyze Incident → 3-agent RAG → Runbook                │
│  • Memory Bank (search, browse, delete slices)             │
│  • Ingest new slices / seed demo data                      │
│  • Setup & infrastructure initialization                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
sentinelslice/
├── backend/
│   ├── main.py                  # FastAPI app + all routes
│   ├── models.py                # Pydantic request/response models
│   ├── requirements.txt
│   ├── .env.example             # Copy to .env and fill credentials
│   └── services/
│       ├── elastic_service.py   # All Elasticsearch operations
│       ├── inference_service.py # Inference endpoint lifecycle
│       └── agent_service.py     # 3-agent agentic RAG loop
│
├── frontend/
│   └── index.html               # Single-file SPA (HTML + CSS + JS)
│
├── scripts/
│   └── start.sh                 # Quick-start script
│
└── README.md
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- [Elastic Cloud](https://cloud.elastic.co) account (free trial available)
- [OpenAI API key](https://platform.openai.com)

### 2. Configure Environment

```bash
cd backend
cp .env.example .env
```

Edit `.env`:

```env
ELASTIC_CLOUD_URL=https://your-cluster-id.es.us-east-1.aws.elastic-cloud.com
ELASTIC_API_KEY=your_elastic_api_key_here
OPENAI_API_KEY=sk-your_openai_api_key_here
SENTINEL_INDEX=sentinel-slices
```

### 3. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Start the Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

API docs available at: `http://localhost:8000/docs`

### 5. Open the Frontend

Simply open `frontend/index.html` in your browser, or serve it:

```bash
cd frontend
python -m http.server 3000
# then open http://localhost:3000
```

### 6. Initialize Infrastructure

In the **Setup** tab of the UI:
1. Set your Backend API URL (`http://localhost:8000`)
2. Enter your OpenAI API Key
3. Click **Initialize Infrastructure** — this creates the BBQ index, inference endpoint, and ingest pipeline in Elastic Cloud.

### 7. Seed Demo Data

In the **Ingest** tab, click **Seed Demo Data** to load 8 pre-built incident slices covering:
- Kubernetes control plane issues
- E-commerce API degradation  
- ML inference failures
- Data pipeline lag
- 5G network slice problems

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Connectivity check |
| `POST` | `/api/setup` | Initialize Elastic infra |
| `POST` | `/api/slices/ingest` | Add a new slice |
| `POST` | `/api/slices/seed` | Load demo data |
| `GET` | `/api/slices` | List slices (optional `?domain=`) |
| `POST` | `/api/slices/search` | Hybrid RRF search |
| `DELETE` | `/api/slices/{id}` | Remove a slice |
| `POST` | `/api/analyze` | Full agentic RAG analysis |
| `GET` | `/api/stats` | Index stats + domain breakdown |

### Analyze Request

```json
POST /api/analyze
{
  "symptoms": "API server is feeling sluggish, seeing latency spikes and webhook timeouts",
  "domain": "k8s-controlplane",
  "top_k": 3
}
```

### Analyze Response

```json
{
  "success": true,
  "data": {
    "runbook": "Step 1: ...\nStep 2: ...",
    "pattern": "Root cause pattern identified...",
    "matches": [
      { "rank": 1, "score": 0.91, "incident_id": "K8S-INC-001", ... }
    ],
    "timeline": [
      { "agent": "Retrieval Agent", "duration_s": 0.8, "detail": "Found 3 matches via RRF" },
      { "agent": "Analysis Agent", "duration_s": 1.2, "detail": "..." },
      { "agent": "Action Agent", "duration_s": 1.1, "detail": "..." }
    ],
    "total_time_s": 3.1
  }
}
```

---

## Key Technologies

| Component | Technology | Why |
|-----------|------------|-----|
| Vector Index | `bbq_hnsw` | 32× size reduction vs float32, ~95% memory savings |
| Text Field | `semantic_text` | Auto-chunking + embedding via Elastic |
| Search | Reciprocal Rank Fusion (RRF) | Combines lexical BM25 + semantic vector results |
| Embeddings | OpenAI `text-embedding-3-small` | Via Elastic Open Inference API (native) |
| Agent LLM | `gpt-4o` | Reasoning + runbook generation |
| Backend | FastAPI + Python | Async, typed, auto-docs |

---

## Use Cases

SentinelSlice is domain-agnostic. The same architecture works for:

- **SRE / DevOps**: Kubernetes, cloud infrastructure, microservices
- **Telecom**: 5G network slices, RAN issues, core network degradation  
- **E-commerce**: Checkout API failures, CDN issues, flash sale overloads
- **ML/Data**: Model serving degradation, pipeline lag, feature store failures
- **Security**: Anomaly pattern matching against historical threat signatures
- **IoT**: Device fleet operational pattern matching

---

## How Slices Work

A **slice** is a 3–10 minute compressed operational fingerprint:

```
Cluster: prod-us-east-1
Node CPU saturation rising
Pod rescheduling increasing  
API latency drifting
Autoscaler lagging
```

Rather than alerting on generic thresholds, SentinelSlice:
1. **Embeds** the current system state into a 1536-dim vector
2. **Searches** the memory bank for semantically similar past incidents
3. **Generates** a grounded runbook using only your team's historical resolutions

---

## Configuration

### Changing the Embedding Model

Update `setup-model` in the frontend Setup tab, or set `embedding_model` in the setup API call. Supported: `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`.

### Custom Domains

Add any service/cluster identifier as a domain. The system is fully namespace-agnostic.

### Index Settings

The default index name is `sentinel-slices`. Override via the `SENTINEL_INDEX` env var.

---

## License

MIT
