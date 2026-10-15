"""
small, explicit academic rule evaluator; no database or HTTP dependencies
"""

from dataclasses import dataclass

from .schemas import Rule

# numerical values used to compare letter grades
GRADE_POINTS = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0, "W": -1}

#stores prereq eligibility results
@dataclass(frozen=True)
class Eligibility:
    status: str
    reasons: list[str]

    # converts the result into a dictionary
    def as_dict(self):
        return {"status": self.status, "reasons": self.reasons}


# evaluates whether a student satisfies a prereq rule
def evaluate(rule: Rule | None, history: dict[str, str]) -> Eligibility:
    # no prereqs means the student is eligble
    if rule is None:
        return Eligibility("eligible", ["No prerequisites."])

    # some requirements need manual review
    if rule.kind == "review":
        return Eligibility("review", [rule.note or "Advisor review is required."])

    # check whether a specific course req is satisfied
    if rule.kind == "course":
        grade = history.get(rule.course)
        label = f"{rule.course} with {rule.minimum} or better"

        # in-progress courses are conditionally eligible
        if grade == "IP":
            return Eligibility("conditional", [f"{rule.course} is in progress; {rule.minimum} is required."])

        # passing grades satisfy pass-only requirements
        if rule.minimum == "P":
            passed = grade == "P" or GRADE_POINTS.get(grade, -1) >= 1
        else:
            # compare the student's grade against min required grade
            passed = grade != "P" and GRADE_POINTS.get(grade, -1) >= GRADE_POINTS[rule.minimum]
        return Eligibility(
            "eligible" if passed else "blocked", [f"{'Satisfied' if passed else 'Requires'}: {label}."]
        )

    # recursively evaluate nested prereq rules
    children = [evaluate(child, history) for child in rule.rules]
    # for OR, one fulfilled branch is sufficient even when another needs review.
    # for AND, a definite failure takes precedence over an unsupported rule.
    if rule.kind == "any":
        status = next(
            (
                s
                for s in ["eligible", "conditional", "review", "blocked"]
                if any(c.status == s for c in children)
            ),
            "blocked",
        )
    else:
        status = next(
            (
                s
                for s in ["blocked", "review", "conditional", "eligible"]
                if any(c.status == s for c in children)
            ),
            "eligible",
        )
    
    # combine results and explanations from all child rules
    join = "All required" if rule.kind == "all" else "One required"
    return Eligibility(status, [join + ":"] + [r for c in children for r in c.reasons])


# checks whether a grade counts as a completed course
def completed(grade: str | None) -> bool:
    return grade == "P" or GRADE_POINTS.get(grade, -1) >= 1
