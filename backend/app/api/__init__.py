"""HTTP API layer.

``api_router`` bundles every feature router; ``main.create_app`` mounts it once under
``settings.api_prefix``. To add an endpoint group, create a module with a ``router`` and
register it in ``_PROTECTED_ROUTERS`` (needs sign-in) or ``_PUBLIC_ROUTERS`` below.
"""
from fastapi import APIRouter, Depends
from ..core.security import require_admin, require_user
from . import analytics, assistant, auth, documents, health, imports, knowledge, registry, troubleshooting, users

# Open to everyone: the health probes and the sign-in endpoints themselves.
_PUBLIC_ROUTERS = (health.router, auth.router)

# Everything else needs a signed-in user (see core/security.require_user).
_PROTECTED_ROUTERS = (
    registry.router,
    imports.router,
    analytics.router,
    documents.router,
    knowledge.router,
    assistant.router,
    troubleshooting.router,
)

# Administrators only.
_ADMIN_ROUTERS = (users.router,)

api_router = APIRouter()
for _router in _PUBLIC_ROUTERS:
    api_router.include_router(_router)
for _router in _PROTECTED_ROUTERS:
    api_router.include_router(_router, dependencies=[Depends(require_user)])
for _router in _ADMIN_ROUTERS:
    api_router.include_router(_router, dependencies=[Depends(require_admin)])

__all__ = ["api_router"]