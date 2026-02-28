"""
ElasticService — All Elasticsearch operations for SentinelSlice.
Handles index creation (BBQ), ingest pipeline, hybrid RRF search, CRUD.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from elasticsearch import Elasticsearch, NotFoundError

logger = logging.getLogger(__name__)

DEMO_SLICES = [
    {
        "domain": "k8s-controlplane",
        "state_summary": (
            "Cluster: prod-us-east-1. etcd write latency spiking to 800ms. "
            "API server request queue growing. Pod scheduling failures increasing. "
            "Node heartbeat timeouts observed. Control plane CPU at 92%."
        ),
        "resolution": (
            "1. Scaled etcd from 3 to 5 nodes. "
            "2. Increased etcd heap to 8GB. "
            "3. Disabled a misbehaving MutatingWebhook that was adding 400ms per request. "
            "4. Restarted kube-scheduler after clearing stale lease. "
            "Resolution time: 34 minutes."
        ),
        "metadata": {"severity": "critical", "incident_id": "K8S-INC-001", "duration_min": 34},
    },
    {
        "domain": "ecommerce-api",
        "state_summary": (
            "Service: checkout-api prod. P99 latency degraded from 120ms to 3.4s. "
            "Database connection pool exhausted. Redis hit rate dropped to 12%. "
            "Payment webhook timeouts increasing. Cart abandonment rate spiking."
        ),
        "resolution": (
            "1. Increased DB connection pool from 50 to 200. "
            "2. Identified N+1 query in cart pricing service, patched with eager loading. "
            "3. Warmed Redis cache with top 1000 SKUs. "
            "4. Scaled checkout pods from 4 to 12. "
            "Resolution time: 22 minutes."
        ),
        "metadata": {"severity": "high", "incident_id": "ECO-INC-007", "duration_min": 22},
    },
    {
        "domain": "ml-inference",
        "state_summary": (
            "GPU cluster: inference-us-west. Model serving latency up 5x. "
            "CUDA out-of-memory errors on 3/8 nodes. Batch queue depth growing. "
            "Throughput dropped from 2000 to 180 RPS. Driver version mismatch detected."
        ),
        "resolution": (
            "1. Rolled back CUDA driver from 12.3 to 12.1 on affected nodes. "
            "2. Reduced batch size from 64 to 32 for stability. "
            "3. Drained and rescheduled pods on healthy nodes. "
            "4. Enabled dynamic batching with max_queue_delay=50ms. "
            "Resolution time: 45 minutes."
        ),
        "metadata": {"severity": "high", "incident_id": "ML-INC-003", "duration_min": 45},
    },
    {
        "domain": "data-pipeline",
        "state_summary": (
            "Kafka cluster lag growing on topic user-events. Consumer group lag at 2.1M messages. "
            "Flink job restarting every 8 minutes due to checkpoint timeout. "
            "S3 sink backpressure. Downstream analytics dashboards stale by 4 hours."
        ),
        "resolution": (
            "1. Increased Kafka partition count from 12 to 48. "
            "2. Scaled Flink taskmanagers from 6 to 20. "
            "3. Increased checkpoint interval to 10 min and timeout to 20 min. "
            "4. Temporary S3 multipart upload parallelism increase to catch up. "
            "Resolution time: 67 minutes."
        ),
        "metadata": {"severity": "medium", "incident_id": "PIPE-INC-012", "duration_min": 67},
    },
    {
        "domain": "k8s-controlplane",
        "state_summary": (
            "Cluster: prod-eu-west-2. Node disk pressure on 4/10 worker nodes. "
            "ImagePullBackOff errors cluster-wide. Eviction threshold breached. "
            "Log volumes consuming 94% of ephemeral storage. DaemonSet pods pending."
        ),
        "resolution": (
            "1. Emergency log rotation on affected nodes via DaemonSet Job. "
            "2. Deployed node-problem-detector with disk pressure alerting. "
            "3. Migrated log shipping to Vector agent with compression. "
            "4. Increased PVC size for log volumes from 50Gi to 200Gi. "
            "Resolution time: 18 minutes."
        ),
        "metadata": {"severity": "high", "incident_id": "K8S-INC-009", "duration_min": 18},
    },
    {
        "domain": "ecommerce-api",
        "state_summary": (
            "CDN edge: Flash sale traffic surge. Origin error rate at 34%. "
            "Rate limiter misconfigured after deploy. Authenticated users getting 429s. "
            "Origin CPU at 100%. Cache bypass headers inadvertently set in last deploy."
        ),
        "resolution": (
            "1. Hotfix deploy: removed cache-bypass headers. "
            "2. Raised rate limiter thresholds for authenticated tier. "
            "3. Enabled CDN request coalescing for product API. "
            "4. Scaled origin from 8 to 32 pods for flash sale duration. "
            "Resolution time: 11 minutes."
        ),
        "metadata": {"severity": "critical", "incident_id": "ECO-INC-019", "duration_min": 11},
    },
    {
        "domain": "network-5g",
        "state_summary": (
            "5G network slice: eMBB-slice-3. Throughput degradation 60%. "
            "RAN scheduler congestion at 3 gNodeBs. UE handover failures increasing. "
            "Core network AMF CPU spike. NSSF slice selection failures."
        ),
        "resolution": (
            "1. Rebalanced UE load across gNodeBs via ANR parameter update. "
            "2. Scaled AMF instances from 2 to 6 in Kubernetes. "
            "3. Updated NSSF routing policy to deprioritize congested cells. "
            "4. Triggered proactive handover for 2000 UEs in high-density sector. "
            "Resolution time: 28 minutes."
        ),
        "metadata": {"severity": "critical", "incident_id": "5G-INC-004", "duration_min": 28},
    },
    {
        "domain": "ml-inference",
        "state_summary": (
            "Recommendation engine latency degraded. Feature store read timeout after model update. "
            "Feature drift detected: 3 features returning NaN. A/B test control group impacted. "
            "Fallback to popularity-based ranking activated automatically."
        ),
        "resolution": (
            "1. Rolled back model version from v2.4.1 to v2.3.8. "
            "2. Fixed feature pipeline: added null-check for sparse user features. "
            "3. Backfilled missing feature values using 7-day rolling median. "
            "4. Validated new model in shadow mode for 48h before re-promoting. "
            "Resolution time: 55 minutes."
        ),
        "metadata": {"severity": "medium", "incident_id": "ML-INC-011", "duration_min": 55},
    },
]


class ElasticService:
    INFERENCE_ID = "openai-sre-embeddings"
    PIPELINE_ID = "slice-seeding-pipeline"

    def __init__(self, cloud_url: str, api_key: str, index_name: str):
        self.index_name = index_name
        if cloud_url and api_key:
            self.es = Elasticsearch(cloud_url, api_key=api_key)
        else:
            # Fallback to local for development
            self.es = Elasticsearch("http://localhost:9200")
        logger.info("Elasticsearch client initialized.")

    def ping(self) -> bool:
        try:
            return self.es.ping()
        except Exception:
            return False

    # ── Inference endpoint ────────────────────────────────────────────────────
    def configure_inference(self, inference_id: str, openai_api_key: str, model_id: str):
        self.es.inference.put(
            task_type="text_embedding",
            inference_id=inference_id,
            body={
                "service": "openai",
                "service_settings": {
                    "api_key": openai_api_key,
                    "model_id": model_id,
                },
            },
        )
        logger.info(f"Inference endpoint '{inference_id}' configured.")

    # ── BBQ Index ─────────────────────────────────────────────────────────────
    def create_bbq_index(self):
        if self.es.indices.exists(index=self.index_name):
            logger.info(f"Index '{self.index_name}' already exists.")
            return
        mappings = {
            "mappings": {
                "properties": {
                    "state_summary": {
                        "type": "semantic_text",
                        "inference_id": self.INFERENCE_ID,
                    },
                    "state_vector": {
                        "type": "dense_vector",
                        "dims": 1536,
                        "index": True,
                        "similarity": "cosine",
                        "index_options": {"type": "bbq_hnsw"},
                    },
                    "domain": {"type": "keyword"},
                    "resolution": {"type": "text"},
                    "metadata": {"type": "object", "dynamic": True},
                    "ingested_at": {"type": "date"},
                }
            }
        }
        self.es.indices.create(index=self.index_name, body=mappings)
        logger.info(f"BBQ index '{self.index_name}' created.")

    # ── Ingest Pipeline ───────────────────────────────────────────────────────
    def setup_ingest_pipeline(self):
        self.es.ingest.put_pipeline(
            id=self.PIPELINE_ID,
            body={
                "description": "Seeds real-time slices with embeddings via OpenAI",
                "processors": [
                    {
                        "inference": {
                            "model_id": self.INFERENCE_ID,
                            "input_output": [
                                {"input_field": "raw_logs", "output_field": "state_vector"}
                            ],
                        }
                    },
                    {
                        "set": {
                            "field": "ingested_at",
                            "value": "{{{_ingest.timestamp}}}",
                        }
                    },
                ],
            },
        )
        logger.info(f"Ingest pipeline '{self.PIPELINE_ID}' configured.")

    # ── Ingest a Slice ────────────────────────────────────────────────────────
    def ingest_slice(
        self,
        state_summary: str,
        domain: str,
        resolution: str,
        metadata: Optional[Dict] = None,
    ) -> str:
        doc_id = str(uuid.uuid4())
        doc = {
            "state_summary": state_summary,
            "domain": domain,
            "resolution": resolution,
            "metadata": metadata or {},
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        }
        self.es.index(index=self.index_name, id=doc_id, body=doc)
        logger.info(f"Slice ingested: {doc_id}")
        return doc_id

    # ── Seed Demo Data ────────────────────────────────────────────────────────
    def seed_demo_slices(self) -> int:
        for s in DEMO_SLICES:
            self.ingest_slice(
                state_summary=s["state_summary"],
                domain=s["domain"],
                resolution=s["resolution"],
                metadata=s["metadata"],
            )
        return len(DEMO_SLICES)

    # ── Hybrid RRF Search ─────────────────────────────────────────────────────
    def hybrid_search(
        self,
        query_text: str,
        domain: Optional[str] = None,
        top_k: int = 5,
    ) -> Dict:
        filters = []
        if domain:
            filters.append({"term": {"domain": domain}})

        lexical_query: Dict[str, Any] = {"match": {"state_summary": query_text}}
        if filters:
            lexical_query = {
                "bool": {
                    "must": [{"match": {"state_summary": query_text}}],
                    "filter": filters,
                }
            }

        semantic_retriever: Dict[str, Any] = {
            "semantic": {
                "field": "state_summary",
                "query": query_text,
            }
        }
        if filters:
            semantic_retriever["semantic"]["filter"] = filters

        search_body = {
            "retriever": {
                "rrf": {
                    "retrievers": [
                        {"standard": {"query": lexical_query}},
                        semantic_retriever,
                    ],
                    "rank_window_size": top_k * 3,
                    "rank_constant": 60,
                }
            },
            "size": top_k,
        }
        return self.es.search(index=self.index_name, body=search_body)

    # ── List Slices ───────────────────────────────────────────────────────────
    def list_slices(self, domain: Optional[str] = None, size: int = 20) -> List[Dict]:
        query: Dict[str, Any] = {"match_all": {}}
        if domain:
            query = {"term": {"domain": domain}}
        resp = self.es.search(
            index=self.index_name,
            body={
                "query": query,
                "sort": [{"ingested_at": {"order": "desc"}}],
                "size": size,
            },
        )
        return [
            {
                "id": h["_id"],
                "state_summary": h["_source"].get("state_summary", ""),
                "domain": h["_source"].get("domain", ""),
                "resolution": h["_source"].get("resolution", ""),
                "metadata": h["_source"].get("metadata", {}),
                "ingested_at": h["_source"].get("ingested_at", ""),
            }
            for h in resp["hits"]["hits"]
        ]

    # ── Delete ────────────────────────────────────────────────────────────────
    def delete_slice(self, slice_id: str):
        self.es.delete(index=self.index_name, id=slice_id)

    # ── Stats ─────────────────────────────────────────────────────────────────
    def get_stats(self) -> Dict:
        count_resp = self.es.count(index=self.index_name)
        agg_resp = self.es.search(
            index=self.index_name,
            body={
                "size": 0,
                "aggs": {
                    "by_domain": {"terms": {"field": "domain", "size": 20}},
                },
            },
        )
        domains = [
            {"domain": b["key"], "count": b["doc_count"]}
            for b in agg_resp["aggregations"]["by_domain"]["buckets"]
        ]
        return {"total_slices": count_resp["count"], "by_domain": domains}
