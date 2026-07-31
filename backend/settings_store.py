"""Application settings: LLM keys, provider/model, GitHub token, savings assumptions."""
from __future__ import annotations

import os

from core.config import DEFAULT_ASSUMPTIONS, derived_rates
from db import app_settings, utcnow

SETTINGS_ID = "app"

PROVIDER_MODELS = {
    "anthropic": ["claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-4-6", "claude-opus-4-6"],
    "gemini": ["gemini-3.1-pro-preview", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-2.5-pro"],
    "openai": ["gpt-5.4", "gpt-5.5", "gpt-5.4-mini"],
}

DEFAULTS = {
    "_id": SETTINGS_ID,
    "llm_provider": "anthropic",
    "llm_model": "claude-opus-4-7",
    "use_platform_key": True,
    "anthropic_api_key": "",
    "gemini_api_key": "",
    "openai_api_key": "",
    "github_token": "",
    "bitbucket_token": "",
    "auto_draft_count": 5,
    "assumptions": dict(DEFAULT_ASSUMPTIONS),
}

ASSUMPTION_FIELDS = {
    "tokens_per_report_credit": (1, 100_000_000),
    "vendor_credits_per_dollar": (0.0001, 1_000_000),
    "input_tokens_per_vendor_credit": (1, 100_000_000),
    "output_tokens_per_vendor_credit": (1, 100_000_000),
    "agent_runs_per_month": (1, 1_000_000),
    "output_token_share": (0.0, 1.0),
    "variance_pct": (0.0, 0.9),
}


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:6]}{'*' * 8}{value[-4:]}"


async def get_settings() -> dict:
    doc = await app_settings.find_one({"_id": SETTINGS_ID})
    if not doc:
        doc = dict(DEFAULTS)
        doc["updated_at"] = utcnow()
        await app_settings.insert_one(dict(doc))
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in doc.items() if v is not None})
    assumptions = dict(DEFAULT_ASSUMPTIONS)
    assumptions.update(doc.get("assumptions") or {})
    assumptions.update(derived_rates(assumptions))
    merged["assumptions"] = assumptions
    return merged


async def update_settings(patch: dict) -> dict:
    current = await get_settings()
    update = {}
    for key in ("llm_provider", "llm_model", "use_platform_key", "auto_draft_count"):
        if key in patch and patch[key] is not None:
            update[key] = patch[key]
    if update.get("llm_provider") and update.get("llm_provider") not in PROVIDER_MODELS:
        raise ValueError(f"Unknown provider '{update['llm_provider']}'")
    if "auto_draft_count" in update:
        update["auto_draft_count"] = max(0, min(25, int(update["auto_draft_count"])))
    for key in ("anthropic_api_key", "gemini_api_key", "openai_api_key", "github_token", "bitbucket_token"):
        if key in patch and patch[key] is not None:
            update[key] = str(patch[key]).strip()
    if "assumptions" in patch and isinstance(patch["assumptions"], dict):
        assumptions = dict(current["assumptions"])
        for key, (lo, hi) in ASSUMPTION_FIELDS.items():
            if key in patch["assumptions"] and patch["assumptions"][key] is not None:
                val = float(patch["assumptions"][key])
                if not (lo <= val <= hi):
                    raise ValueError(f"{key} must be between {lo} and {hi}")
                assumptions[key] = int(val) if float(val).is_integer() and key not in (
                    "output_token_share", "variance_pct", "vendor_credits_per_dollar") else val
        for key in ("rates_last_refreshed", "rates_source"):
            if key in patch["assumptions"]:
                assumptions[key] = patch["assumptions"][key]
        assumptions.pop("input_dollars_per_million", None)
        assumptions.pop("output_dollars_per_million", None)
        update["assumptions"] = assumptions
    update["updated_at"] = utcnow()
    await app_settings.update_one({"_id": SETTINGS_ID}, {"$set": update}, upsert=True)
    return await get_settings()


async def reset_assumptions() -> dict:
    await app_settings.update_one(
        {"_id": SETTINGS_ID},
        {"$set": {"assumptions": dict(DEFAULT_ASSUMPTIONS), "updated_at": utcnow()}},
        upsert=True,
    )
    return await get_settings()


def public_settings(s: dict) -> dict:
    return {
        "llm_provider": s["llm_provider"],
        "llm_model": s["llm_model"],
        "use_platform_key": bool(s["use_platform_key"]),
        "platform_key_available": bool(os.environ.get("EMERGENT_LLM_KEY")),
        "auto_draft_count": s["auto_draft_count"],
        "provider_models": PROVIDER_MODELS,
        "keys": {
            "anthropic": {"has_key": bool(s["anthropic_api_key"]), "masked": _mask(s["anthropic_api_key"])},
            "gemini": {"has_key": bool(s["gemini_api_key"]), "masked": _mask(s["gemini_api_key"])},
            "openai": {"has_key": bool(s["openai_api_key"]), "masked": _mask(s["openai_api_key"])},
            "github": {"has_key": bool(s["github_token"]), "masked": _mask(s["github_token"])},
            "bitbucket": {"has_key": bool(s["bitbucket_token"]), "masked": _mask(s["bitbucket_token"])},
        },
        "assumptions": s["assumptions"],
        "assumption_bounds": {k: {"min": v[0], "max": v[1]} for k, v in ASSUMPTION_FIELDS.items()},
    }


def resolve_llm_credentials(s: dict) -> tuple:
    """Return (api_key, provider, model, key_source). Raises if no usable key."""
    provider = s.get("llm_provider") or "anthropic"
    model = s.get("llm_model") or PROVIDER_MODELS[provider][0]
    own_key = (s.get(f"{provider}_api_key") or "").strip()
    if not s.get("use_platform_key") and own_key:
        return own_key, provider, model, f"your own {provider} key"
    platform = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if platform:
        return platform, provider, model, "platform managed universal key"
    if own_key:
        return own_key, provider, model, f"your own {provider} key"
    raise RuntimeError(
        "No LLM key is available. Add your own Anthropic or Gemini key in Settings."
    )
