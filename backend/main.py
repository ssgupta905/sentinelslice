"""
SentinelSlice — FastAPI Backend
Agentic RAG incident intelligence powered by Elasticsearch + OpenAI
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.elastic_service import ElasticService
from services.inference_service import InferenceService
from services.agent_service import AgentService
from models import (
    SliceIngestRequest,
    AnalyzeRequest,
    SearchRequest,
    SetupRequest,
    ApiResponse,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Globals ──────────────────────────────────────────────────────────────────
elastic_svc: ElasticService = None
inference_svc: InferenceService = None
agent_svc: AgentService = None

INDEX_NAME = os.getenv("SENTINEL_INDEX", "sentinel-slices")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global elastic_svc, inference_svc, agent_svc
    logger.info("Starting SentinelSlice services …")
    elastic_svc = ElasticService(
        cloud_url=os.getenv("ELASTIC_CLOUD_URL"),
        api_key=os.getenv("ELASTIC_API_KEY"),
        index_name=INDEX_NAME,
    )
    inference_svc = InferenceService(elastic_svc)
    agent_svc = AgentService(
        elastic_svc=elastic_svc,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )
    yield
    logger.info("Shutting down …")


app = FastAPI(
    title="SentinelSlice API",
    description="Operational memory bank with agentic incident remediation",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    es_ok = elastic_svc.ping() if elastic_svc else False
    return {"status": "ok" if es_ok else "degraded", "elasticsearch": es_ok}


# ── Setup / Initialization ───────────────────────────────────────────────────
@app.post("/api/setup", response_model=ApiResponse)
async def setup(req: SetupRequest):
    """Initialize Elasticsearch inference endpoint, BBQ index, and ingest pipeline."""
    try:
        inference_svc.configure_inference(
            inference_id="openai-sre-embeddings",
            openai_api_key=req.openai_api_key or os.getenv("OPENAI_API_KEY"),
            model_id=req.embedding_model,
        )
        elastic_svc.create_bbq_index()
        elastic_svc.setup_ingest_pipeline()
        return ApiResponse(success=True, message="SentinelSlice infrastructure ready.")
    except Exception as e:
        logger.exception("Setup failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Ingest Slice ─────────────────────────────────────────────────────────────
@app.post("/api/slices/ingest", response_model=ApiResponse)
async def ingest_slice(req: SliceIngestRequest):
    """Ingest a new operational slice into the memory bank."""
    try:
        doc_id = elastic_svc.ingest_slice(
            state_summary=req.state_summary,
            domain=req.domain,
            resolution=req.resolution,
            metadata=req.metadata,
        )
        return ApiResponse(success=True, message=f"Slice ingested with id={doc_id}", data={"id": doc_id})
    except Exception as e:
        logger.exception("Ingest failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Batch Seed ───────────────────────────────────────────────────────────────
@app.post("/api/slices/seed", response_model=ApiResponse)
async def seed_demo_data():
    """Seed the index with realistic demo incident slices."""
    try:
        count = elastic_svc.seed_demo_slices()
        return ApiResponse(success=True, message=f"Seeded {count} demo slices.")
    except Exception as e:
        logger.exception("Seed failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Search ────────────────────────────────────────────────────────────────────
@app.post("/api/slices/search", response_model=ApiResponse)
async def search_slices(req: SearchRequest):
    """Hybrid RRF search across the operational memory bank."""
    try:
        results = elastic_svc.hybrid_search(
            query_text=req.query,
            domain=req.domain,
            top_k=req.top_k,
        )
        hits = [
            {
                "id": h["_id"],
                "score": h["_score"],
                "state_summary": h["_source"].get("state_summary", ""),
                "domain": h["_source"].get("domain", ""),
                "resolution": h["_source"].get("resolution", ""),
                "metadata": h["_source"].get("metadata", {}),
            }
            for h in results["hits"]["hits"]
        ]
        return ApiResponse(success=True, data={"hits": hits, "total": len(hits)})
    except Exception as e:
        logger.exception("Search failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Analyze & Remediate ───────────────────────────────────────────────────────
@app.post("/api/analyze", response_model=ApiResponse)
async def analyze(req: AnalyzeRequest):
    """Full agentic RAG loop: retrieve similar slices → synthesize runbook."""
    try:
        result = await agent_svc.analyze_and_remediate(
            symptoms=req.symptoms,
            domain=req.domain,
            top_k=req.top_k,
        )
        return ApiResponse(success=True, data=result)
    except Exception as e:
        logger.exception("Analysis failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── List Slices ───────────────────────────────────────────────────────────────
@app.get("/api/slices", response_model=ApiResponse)
async def list_slices(domain: str = None, size: int = 20):
    """List recent slices in the memory bank."""
    try:
        slices = elastic_svc.list_slices(domain=domain, size=size)
        return ApiResponse(success=True, data={"slices": slices})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Delete Slice ──────────────────────────────────────────────────────────────
@app.delete("/api/slices/{slice_id}", response_model=ApiResponse)
async def delete_slice(slice_id: str):
    try:
        elastic_svc.delete_slice(slice_id)
        return ApiResponse(success=True, message=f"Slice {slice_id} deleted.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Stats ─────────────────────────────────────────────────────────────────────
@app.get("/api/stats", response_model=ApiResponse)
async def stats():
    try:
        data = elastic_svc.get_stats()
        return ApiResponse(success=True, data=data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
