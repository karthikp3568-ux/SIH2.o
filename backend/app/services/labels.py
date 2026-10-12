"""Human-readable labels for profile facts.

The conversation screen shows what each answer added ("+ Pump repair",
"+ 10th standard"). The wording is produced here, from the profile delta, so
the client renders the server's understanding rather than inferring its own.
"""

from __future__ import annotations

from typing import Any

from ..core.enums import EDUCATION_LABEL

GOAL_LABEL = {
    "job": "Goal: a job",
    "apprenticeship": "Goal: apprenticeship",
    "training": "Goal: training",
    "self_employment": "Goal: self-employment",
    "higher_income": "Goal: higher income",
    "undecided": "Goal: undecided",
}

MOBILITY_LABEL = {
    "low": "Travel: stays near home",
    "medium": "Travel: nearby town",
    "high": "Travel: can go far",
}

INTEREST_LABEL = {
    "mechanical": "Likes mechanical work",
    "electrical": "Likes electrical work",
    "agriculture": "Likes farming",
    "enterprise": "Likes business",
    "computers": "Likes computers",
    "driving": "Likes driving",
    "tailoring": "Likes tailoring",
    "construction": "Likes construction",
}


def _value(fact: Any) -> Any:
    return fact.get("value") if isinstance(fact, dict) else None


def describe_new_facts(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    """Facts present in `after` and not in `before`, as {slot, label}."""
    out: list[dict[str, str]] = []

    def add(slot: str, label: str) -> None:
        if label and {"slot": slot, "label": label} not in out:
            out.append({"slot": slot, "label": label})

    known = {o.get("value") for o in before.get("occupations", [])}
    for occupation in after.get("occupations", []):
        if occupation.get("value") not in known:
            add("occupation", str(occupation["value"]).split(" / ")[0])

    known = {o.get("value") for o in before.get("previous_occupations", [])}
    for occupation in after.get("previous_occupations", []):
        if occupation.get("value") not in known:
            add("occupation", f"Previously: {str(occupation['value']).split(' / ')[0]}")

    known = {s.get("code") for s in before.get("skills", [])}
    for skill in after.get("skills", []):
        if skill.get("code") not in known and not skill.get("is_category"):
            add("skills", str(skill.get("name")))

    if _value(after.get("education")) != _value(before.get("education")) and after.get("education"):
        value = str(_value(after["education"]))
        add("education", after["education"].get("label") or EDUCATION_LABEL.get(value, value))

    experience = after.get("experience_years")
    if experience and experience != before.get("experience_years"):
        years = experience.get("value")
        label = experience.get("label") or (f"{years:g} years’ experience" if isinstance(years, (int, float)) else "")
        add("experience", label)

    known = {g.get("value") for g in before.get("goals", [])}
    for goal in after.get("goals", []):
        if goal.get("value") not in known:
            add("goal", GOAL_LABEL.get(str(goal["value"]), str(goal["value"])))

    if _value(after.get("mobility")) != _value(before.get("mobility")) and after.get("mobility"):
        add("mobility", MOBILITY_LABEL.get(str(_value(after["mobility"])), ""))

    known = {i.get("value") for i in before.get("interests", [])}
    for interest in after.get("interests", []):
        if interest.get("value") not in known:
            add("interests", interest.get("label") or INTEREST_LABEL.get(str(interest["value"]), str(interest["value"])))

    location = after.get("location") or {}
    if location != (before.get("location") or {}) and location.get("source") == "conversation":
        add("location", location.get("district") or location.get("pincode") or "Location")
    return out
