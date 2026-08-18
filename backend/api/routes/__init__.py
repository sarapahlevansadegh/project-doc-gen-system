from fastapi import APIRouter

api_router = APIRouter()

from api.routes.auth import auth_router  # noqa: E402
from api.routes.devices import devices_router  # noqa: E402
from api.routes.documents import documents_router  # noqa: E402
from api.routes.health import health_router  # noqa: E402
from api.routes.rag import rag_router  # noqa: E402
from api.routes.settings import settings_router  # noqa: E402
from api.routes.ws import ws_router  # noqa: E402

api_router.include_router(health_router)
api_router.include_router(rag_router)
api_router.include_router(devices_router)
api_router.include_router(settings_router)
api_router.include_router(documents_router)
api_router.include_router(ws_router)
# `/auth/*` is the documented API. Keep the original unprefixed paths out of
# the schema for one release so existing frontend deployments can migrate.
api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(auth_router, include_in_schema=False)
