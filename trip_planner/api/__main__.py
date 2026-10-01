import uvicorn

from trip_planner.config import get_settings

settings = get_settings()
uvicorn.run("trip_planner.api.app:app", host=settings.host, port=settings.port)
