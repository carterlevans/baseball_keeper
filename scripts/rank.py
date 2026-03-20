"""
Computes a ranking score for each player.

Formula:
    base = career_war
    if age < 28 and years_in_mlb < 6 and career_war > 0:
        projected = career_war * (28 / max(age, 20))
        base = min(projected, career_war + 30)   # cap the boost
    score = base * games_seen
"""

from __future__ import annotations
from datetime import date
from typing import Optional


def compute_age(birth_year: int) -> int:
    return date.today().year - birth_year


def ranking_score(
    career_war: float,
    peak_war: float,
    games_seen: int,
    birth_year: Optional[int],
    years_in_mlb: Optional[int],
) -> float:
    base = career_war

    if birth_year and years_in_mlb is not None:
        age = compute_age(birth_year)
        if age < 28 and years_in_mlb < 6 and career_war > 0:
            projected = career_war * (28 / max(age, 20))
            base = min(projected, career_war + 30)

    return round(base * games_seen, 2)
