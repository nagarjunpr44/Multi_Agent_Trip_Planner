from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class CostLineItem(BaseModel):
    category: str
    description: str
    amount_usd: float
    per_person: bool = True


class BudgetTier(BaseModel):
    label: str  # budget | mid | luxury
    total_usd: float
    flights_usd: float
    hotels_usd: float
    activities_usd: float
    food_usd: float
    transport_usd: float
    misc_usd: float

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values: dict) -> dict:
        nullable_fields = (
            "total_usd",
            "flights_usd",
            "hotels_usd",
            "activities_usd",
            "food_usd",
            "transport_usd",
            "misc_usd",
        )
        for f in nullable_fields:
            if values.get(f) is None:
                values[f] = 0.0
        return values


class BudgetAnalysis(BaseModel):
    num_days: int
    num_travelers: int
    currency: str = "USD"
    budget: BudgetTier
    mid: BudgetTier
    luxury: BudgetTier
    recommended_tier: str = "mid"
    line_items: list[CostLineItem] = Field(default_factory=list)
    per_person_per_day_usd: float | None = None
    savings_tips: list[str] = Field(default_factory=list)
    cost_breakdown_note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_nulls(cls, values: dict) -> dict:
        for f in ("line_items", "savings_tips"):
            if values.get(f) is None:
                values[f] = []
        return values


class CostEstimate(BaseModel):
    """Quick estimate — used by individual agents before full budget analysis."""
    min_usd: float
    max_usd: float
    avg_usd: float
    currency: str = "USD"
    note: str | None = None
