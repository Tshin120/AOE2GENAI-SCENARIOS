"""
API Configuration for AoE2 Scenario Generator
Store your OpenRouter API key and other settings here.

Model selection
---------------
Every generated scenario records the EXACT model string used into its
metadata sidecar (see provenance.py), so runs stay reproducible. Callers may
pass either a friendly key from MODEL_REGISTRY (e.g. "sonnet-5") or a raw
OpenRouter slug to ScenarioConfig.model / the --model CLI flag;
resolve_model() maps a friendly key to its pinned slug and passes any
unrecognised string through unchanged.
"""

# OpenRouter API Configuration
# Load from environment variable only
import os

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ---------------------------------------------------------------------------
# Model registry
#
# Frontier entries were originally pinned to dated snapshots captured
# 2026-07-17. Re-verified against the live list on 2026-08-09: only the Sonnet
# snapshot is still served; the dated Opus 4.8 and Fable 5 slugs now return
# "not a valid model ID" (400). Those two are therefore pinned to the undated
# aliases, which do resolve. Verify a slug before a run with:
#
#     curl -H "Authorization: Bearer $OPENROUTER_API_KEY" \
#          https://openrouter.ai/api/v1/models | grep anthropic
#
# Legacy entries are retained VERBATIM for reproducibility of earlier
# experiment runs. OpenRouter no longer serves the 2024 snapshots, so these
# will 404 if selected today - they exist so historical provenance records
# still resolve to a human-readable model name, not for new runs.
# ---------------------------------------------------------------------------
MODEL_REGISTRY = {
    # --- Current frontier (verified against the live list 2026-08-09) ---
    "sonnet-5": "anthropic/claude-sonnet-5-20260630",   # dated pin still served
    "opus-5":   "anthropic/claude-opus-5",              # most capable; used as fidelity judge
    "opus-4.8": "anthropic/claude-opus-4.8",            # dated pin retired by OpenRouter
    "fable-5":  "anthropic/claude-fable-5",             # dated pin retired by OpenRouter
    # --- Legacy (retained for reproducibility; no longer served by OpenRouter) ---
    "claude-3.5-sonnet": "anthropic/claude-3.5-sonnet",
    "claude-3-opus":     "anthropic/claude-3-opus",
    "gpt-4":             "openai/gpt-4",
    "llama-3.1-70b":     "meta-llama/llama-3.1-70b-instruct",
    "gemini-pro":        "google/gemini-pro",
}

# API Settings
# Default is the current-frontier Claude Sonnet snapshot.
DEFAULT_MODEL = MODEL_REGISTRY["sonnet-5"]
DEFAULT_TEMPERATURE = 0.7          # default unchanged from the original generator
DEFAULT_MAX_TOKENS = 32000         # raised from 16000 so large multi-trigger scenarios are not truncated
REQUEST_TIMEOUT = 600              # raised from 180 to accommodate the larger max_tokens

# Alternative models you can use (friendly keys into MODEL_REGISTRY).
# Kept for backwards compatibility; prefer resolve_model() / MODEL_REGISTRY.
ALTERNATIVE_MODELS = [
    "opus-4.8",
    "fable-5",
    "gpt-4",
    "claude-3-opus",
    "llama-3.1-70b",
    "gemini-pro",
]

# Output settings
DEFAULT_OUTPUT_DIR = "scenarios"
AOE2_SCENARIO_PATH = "C:/Users/USER001/Games/Age of Empires 2 DE/76561198844555824/resources/_common/scenario"


def resolve_model(name):
    """Resolve a friendly registry key to its pinned slug.

    A raw slug (anything not in MODEL_REGISTRY) is passed through unchanged, so
    callers can supply an exact OpenRouter slug directly. None resolves to the
    default model.
    """
    if not name:
        return DEFAULT_MODEL
    return MODEL_REGISTRY.get(name, name)


def get_api_key():
    """Get the API key from this configuration file"""
    return OPENROUTER_API_KEY


def get_api_settings():
    """Get all API settings"""
    return {
        "api_key": OPENROUTER_API_KEY,
        "model": DEFAULT_MODEL,
        "temperature": DEFAULT_TEMPERATURE,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "timeout": REQUEST_TIMEOUT,
    }
