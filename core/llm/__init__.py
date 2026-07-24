"""
LLM connection helpers: OpenAI-compatible profiles, retries, OpenRouter usage.

Canonical imports live here. Flat ``core.llm_profile`` / ``core.llm_retry`` /
``core.openrouter_balance`` remain as thin compat shims.
"""

from __future__ import annotations

from core.llm.openrouter_balance import fetch_openrouter_key_usage
from core.llm.profile import (
    OpenAICompatibleConnection,
    expand_openrouter_nested,
    is_local_openai_compatible_provider,
    merge_llm_tuning_options,
    merged_vision_pipeline,
    resolve_openai_compatible_connection,
    resolved_brain_model,
    resolved_brain_model_deep,
    resolved_memory_model,
    resolved_primary_model,
    resolved_talk_model,
    resolved_vision_model_id,
)
from core.llm.retry import ainvoke_with_rate_limit_backoff, is_retryable_llm_error

__all__ = [
    "OpenAICompatibleConnection",
    "ainvoke_with_rate_limit_backoff",
    "expand_openrouter_nested",
    "fetch_openrouter_key_usage",
    "is_local_openai_compatible_provider",
    "is_retryable_llm_error",
    "merge_llm_tuning_options",
    "merged_vision_pipeline",
    "resolve_openai_compatible_connection",
    "resolved_brain_model",
    "resolved_brain_model_deep",
    "resolved_memory_model",
    "resolved_primary_model",
    "resolved_talk_model",
    "resolved_vision_model_id",
]
