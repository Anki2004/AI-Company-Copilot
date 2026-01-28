from fastapi import APIRouter
from . import goals, tools, search, workflows

api_router = APIRouter()
api_router.include_router(goals.router)
api_router.include_router(workflows.router)
api_router.include_router(search.router)
api_router.include_router(tools.router)

