"""
AgentService — Three-agent RAG loop for incident remediation.

Agents:
  1. Retrieval Agent  — hybrid RRF search against memory bank
  2. Analysis Agent   — pattern synthesis from retrieved slices
  3. Action Agent     — generates step-by-step runbook
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from services.elastic_service import ElasticService

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self, elastic_svc: ElasticService, openai_api_key: str):
        self.es_svc = elastic_svc
        self.ai = AsyncOpenAI(api_key=openai_api_key)

    async def analyze_and_remediate(
        self,
        symptoms: str,
        domain: str,
        top_k: int = 3,
    ) -> Dict[str, Any]:
        timeline = []

        # ── Agent 1: Retrieval ────────────────────────────────────────────────
        t0 = time.perf_counter()
        search_results = self.es_svc.hybrid_search(
            query_text=symptoms,
            domain=domain,
            top_k=top_k,
        )
        hits = search_results["hits"]["hits"]
        retrieval_time = round(time.perf_counter() - t0, 2)
        scores = [round(h["_score"], 2) for h in hits]
        timeline.append(
            {
                "agent": "Retrieval Agent",
                "duration_s": retrieval_time,
                "detail": f"Found {len(hits)} matches via RRF (scores: {scores})",
            }
        )

        if not hits:
            return {
                "runbook": "No historical matches found. This may be a novel incident — escalate to on-call engineer.",
                "matches": [],
                "timeline": timeline,
                "pattern": "No pattern detected.",
            }

        # Build context string
        context_parts = []
        matches = []
        for i, h in enumerate(hits):
            src = h["_source"]
            summary = src.get("state_summary", "")
            resolution = src.get("resolution", "")
            metadata = src.get("metadata", {})
            context_parts.append(
                f"[Match {i+1}] Incident {metadata.get('incident_id', 'UNKNOWN')} "
                f"(similarity={round(h['_score'], 2)})\n"
                f"State: {summary}\n"
                f"Resolution: {resolution}"
            )
            matches.append(
                {
                    "rank": i + 1,
                    "score": round(h["_score"], 2),
                    "incident_id": metadata.get("incident_id", h["_id"]),
                    "state_summary": summary,
                    "resolution": resolution,
                    "domain": src.get("domain", ""),
                    "severity": metadata.get("severity", "unknown"),
                }
            )

        context = "\n\n".join(context_parts)

        # ── Agent 2: Analysis ─────────────────────────────────────────────────
        t1 = time.perf_counter()
        analysis_prompt = f"""You are an expert SRE analyst. Given the current symptoms and historical matches, identify the root cause pattern.

Current symptoms:
{symptoms}

Historical similar incidents:
{context}

In 2-3 sentences, identify the root cause pattern you see across these incidents and how it relates to the current situation. Be specific and technical."""

        analysis_resp = await self.ai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": analysis_prompt}],
            max_tokens=300,
        )
        pattern = analysis_resp.choices[0].message.content.strip()
        analysis_time = round(time.perf_counter() - t1, 2)
        timeline.append(
            {
                "agent": "Analysis Agent",
                "duration_s": analysis_time,
                "detail": "Root cause pattern synthesized from historical matches.",
            }
        )

        # ── Agent 3: Action ───────────────────────────────────────────────────
        t2 = time.perf_counter()
        action_prompt = f"""You are a senior SRE writing an emergency runbook. Use ONLY the historical resolutions provided to suggest remediation steps for the current incident.

Current symptoms:
{symptoms}

Root cause pattern:
{pattern}

Historical resolutions:
{context}

Generate a numbered 5-7 step remediation runbook. Each step should be:
- Specific and actionable (include actual commands or config changes where relevant)
- Ordered by priority (most critical first)
- Based strictly on the historical resolutions above

Format each step as:
Step N: [Action Title]
[Detailed description with specific commands/values]"""

        action_resp = await self.ai.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": action_prompt}],
            max_tokens=800,
        )
        runbook = action_resp.choices[0].message.content.strip()
        action_time = round(time.perf_counter() - t2, 2)
        timeline.append(
            {
                "agent": "Action Agent",
                "duration_s": action_time,
                "detail": f"Generated {len(runbook.splitlines())} line runbook.",
            }
        )

        total_time = round(retrieval_time + analysis_time + action_time, 2)

        return {
            "runbook": runbook,
            "pattern": pattern,
            "matches": matches,
            "timeline": timeline,
            "total_time_s": total_time,
            "domain": domain,
        }
