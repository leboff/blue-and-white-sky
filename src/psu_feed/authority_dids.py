"""
Authority accounts: beat reporters, official accounts, etc.
These DIDs get a fixed 2.0x multiplier so their posts rank higher.

Source of truth is data/settings.json (see settings.py). This module re-exports getters.
"""

from .settings import get_authority_accounts, get_authority_dids

__all__ = ["get_authority_accounts", "get_authority_dids"]
