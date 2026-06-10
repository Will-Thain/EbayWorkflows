"""Backward-compat shim — use ebay_workflows.persistence.session."""
from ebay_workflows.persistence.session import build_engine, build_session_factory

__all__ = ["build_engine", "build_session_factory"]
