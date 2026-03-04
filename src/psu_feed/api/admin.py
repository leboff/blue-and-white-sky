"""Admin API: keywords and authority settings (JSON only)."""

from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from .. import settings as settings_module

router = APIRouter()


def _validate_did(did: str) -> bool:
    return isinstance(did, str) and did.strip().startswith("did:")


@router.get("/admin/settings")
async def admin_get_settings():
    """Return current keywords, negative_keywords, and authorities for the admin UI."""
    return {
        "keywords": settings_module.get_keywords(),
        "negative_keywords": settings_module.get_negative_keywords(),
        "authorities": settings_module.get_authorities(),
    }


@router.put("/admin/settings")
async def admin_put_settings(body: dict = Body(...)):
    """Validate and save settings from the admin UI."""
    keywords = body.get("keywords")
    negative_keywords = body.get("negative_keywords")
    authorities = body.get("authorities")
    if keywords is not None and not isinstance(keywords, list):
        raise HTTPException(400, "keywords must be a list")
    if negative_keywords is not None and not isinstance(negative_keywords, list):
        raise HTTPException(400, "negative_keywords must be a list")
    if authorities is not None and not isinstance(authorities, list):
        raise HTTPException(400, "authorities must be a list")
    if isinstance(keywords, list) and not all(isinstance(k, str) for k in keywords):
        raise HTTPException(400, "keywords must be strings")
    if isinstance(negative_keywords, list) and not all(isinstance(k, str) for k in negative_keywords):
        raise HTTPException(400, "negative_keywords must be strings")
    if isinstance(authorities, list):
        for a in authorities:
            if not isinstance(a, dict) or not _validate_did(a.get("did") or ""):
                raise HTTPException(400, "authorities must be list of {did, label} with valid did")
            if "label" not in a:
                a["label"] = a.get("did", "")
    data = {
        "keywords": keywords if keywords is not None else settings_module.get_keywords(),
        "negative_keywords": negative_keywords if negative_keywords is not None else settings_module.get_negative_keywords(),
        "authorities": authorities if authorities is not None else settings_module.get_authorities(),
    }
    settings_module.save_settings(data)
    return {"ok": True}
