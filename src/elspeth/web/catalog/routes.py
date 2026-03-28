"""Catalog API routes — read-only plugin browsing."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from elspeth.web.catalog.protocol import CatalogService
from elspeth.web.catalog.schemas import PluginSchemaInfo, PluginSummary

catalog_router = APIRouter(tags=["catalog"])

# Map plural REST path segments to singular protocol values (Seam C, M3 fix).
# The CatalogService protocol uses singular ("source", "transform", "sink").
# REST paths use plural ("sources", "transforms", "sinks").
# Translation is a REST presentation concern — does not leak into service layer.
_PLURAL_TO_SINGULAR = {"sources": "source", "transforms": "transform", "sinks": "sink"}


def _get_catalog(request: Request) -> CatalogService:
    """Extract CatalogService from app state."""
    catalog: CatalogService = request.app.state.catalog_service
    return catalog


@catalog_router.get("/sources", response_model=list[PluginSummary])
def list_sources(request: Request) -> list[PluginSummary]:
    """List all registered source plugins."""
    return _get_catalog(request).list_sources()


@catalog_router.get("/transforms", response_model=list[PluginSummary])
def list_transforms(request: Request) -> list[PluginSummary]:
    """List all registered transform plugins."""
    return _get_catalog(request).list_transforms()


@catalog_router.get("/sinks", response_model=list[PluginSummary])
def list_sinks(request: Request) -> list[PluginSummary]:
    """List all registered sink plugins."""
    return _get_catalog(request).list_sinks()


@catalog_router.get("/{plugin_type}/{name}/schema", response_model=PluginSchemaInfo)
def get_schema(plugin_type: str, name: str, request: Request) -> PluginSchemaInfo:
    """Get full JSON schema for a plugin's configuration."""
    singular = _PLURAL_TO_SINGULAR.get(plugin_type)
    if singular is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown plugin type: {plugin_type}. Must be one of: {sorted(_PLURAL_TO_SINGULAR)}",
        )
    try:
        return _get_catalog(request).get_schema(singular, name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
