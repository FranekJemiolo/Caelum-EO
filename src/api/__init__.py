"""FastAPI Application and Services for Project Caelum-EO.

Exposes REST and GeoJSON endpoints for detection exploration, zone aggregation,
high-priority triage hotlist, and human-in-the-loop (HITL) review workflows.
"""

from src.api.main import app

__all__ = ["app"]
