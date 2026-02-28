"""Pydantic models for SentinelSlice API."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SetupRequest(BaseModel):
    openai_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"


class SliceIngestRequest(BaseModel):
    state_summary: str = Field(..., description="Compressed operational fingerprint text")
    domain: str = Field(..., description="Service/cluster domain (e.g. k8s-prod, ecommerce-api)")
    resolution: str = Field(..., description="How this incident was resolved")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str
    domain: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class AnalyzeRequest(BaseModel):
    symptoms: str = Field(..., description="Current anomaly description")
    domain: str
    top_k: int = Field(default=3, ge=1, le=10)


class ApiResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None
