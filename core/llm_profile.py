"""Compat shim — prefer ``from core.llm import …`` or ``core.llm.profile``."""

from __future__ import annotations

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

__all__ = [
    "OpenAICompatibleConnection",
    "expand_openrouter_nested",
    "is_local_openai_compatible_provider",
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
