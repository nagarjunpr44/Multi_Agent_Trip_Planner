"""Data tools: plain async functions over external APIs.

They know nothing about LLMs or LangGraph; trip_planner.agent wraps them as tools.
Every function returns compact, normalized data (models from trip.models or small
dicts) and raises ToolError with a short, LLM-readable message on failure.
"""


class ToolError(Exception):
    """A tool failed in a way the planner should be told about (bad input, no key, API down)."""
