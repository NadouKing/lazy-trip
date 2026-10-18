"""Local day-trip toolkit. Maps and weather stay with the official Amap MCP."""

from .maps import map_tasks, route_tasks
from .planner import plan
from .render import render_html
from .request import validate_candidates, validate_request

__all__ = [
    "map_tasks", "route_tasks", "plan", "render_html", "validate_candidates", "validate_request"
]
__version__ = "0.1.0"
