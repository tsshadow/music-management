"""Expose analyzer API routes within the Scrobbler application."""
from services.analyzer_service.analyzer.api.router import router
__all__ = ['router']
from services.common.api.jobs import router