"""LLM-as-judge: grades one finished trip against the request that produced it."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from trip_planner.llm import get_llm


class Criterion(BaseModel):
    score: int = Field(ge=1, le=5)
    rationale: str = Field(description="One sentence.")


class JudgeScore(BaseModel):
    fit_to_request: Criterion
    geography_and_sequencing: Criterion
    specificity: Criterion
    pacing: Criterion
    honesty: Criterion
    overall: int = Field(ge=1, le=5)
    biggest_problem: str = Field(description="The single most important flaw, a few words.")


RUBRIC = """You are a strict, experienced travel editor grading a trip plan produced by an
AI planner. Grade only what is in the plan and the planner's final message.

Score each criterion 1-5 (5 = a professional travel agent would send it as is,
3 = usable but with clear flaws, 1 = wrong or useless), with a one-sentence rationale:

- fit_to_request: dates, party, destinations, budget, interests and every stated
  constraint (diet, mobility, kids, pace, arrival time) are honored.
- geography_and_sequencing: each day stays in a sensible area, stops are ordered to
  avoid backtracking, travel times are realistic, multi-city transfers make sense.
- specificity: named, real, currently existing places and restaurants, not generic
  filler like "local restaurant" or "explore the old town".
- pacing: amount per day matches the requested pace and the party (kids, elderly,
  jet lag, late arrival); meals and rest are allowed for.
- honesty: assumptions (e.g. a budget that was not given) are stated; no invented
  prices, opening hours or facts presented as certain; problems are admitted.

Then give overall (1-5, your holistic judgment, not an average) and biggest_problem."""


def compact_trip(trip: dict) -> dict:
    """Drop ids, urls and opening hours; they cost tokens and don't help grading."""
    drop = {"id", "place_id", "maps_url", "website", "booking_url", "hours", "types", "version"}

    def clean(x):
        if isinstance(x, dict):
            return {
                k: clean(v) for k, v in x.items() if k not in drop and v not in (None, "", [])
            }
        if isinstance(x, list):
            return [clean(v) for v in x]
        if isinstance(x, float):
            return round(x, 3)
        return x

    return clean(trip)


async def judge(case: dict, trip: dict, final_text: str) -> JudgeScore:
    llm = get_llm("judge").with_structured_output(JudgeScore, method="json_schema")
    user = (
        f"## Request\n{case['message']}\n\n"
        f"## Follow-up answers available to the planner\n{json.dumps(case['followups'])}\n\n"
        f"## Planner's final message\n{final_text or '(none)'}\n\n"
        f"## Trip JSON\n{json.dumps(compact_trip(trip), separators=(',', ':'), default=str)}"
    )
    return await llm.ainvoke([("system", RUBRIC), ("user", user)])
