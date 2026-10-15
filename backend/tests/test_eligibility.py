import pytest
from app.eligibility import evaluate
from app.schemas import Rule


@pytest.mark.parametrize(
    ("grade", "status"),
    [
        ("A", "eligible"),
        ("B", "eligible"),
        ("C", "eligible"),
        ("D", "blocked"),
        ("F", "blocked"),
        ("W", "blocked"),
        ("P", "blocked"),
        ("IP", "conditional"),
        (None, "blocked"),
    ],
)
def test_minimum_grade(grade, status):
    assert evaluate(Rule(kind="course", course="CSCI 1301"), {"CSCI 1301": grade}).status == status


def test_pass_is_explicit():
    assert evaluate(Rule(kind="course", course="X", minimum="P"), {"X": "P"}).status == "eligible"


@pytest.mark.parametrize(("kind", "expected"), [("all", "blocked"), ("any", "eligible")])
def test_nested_and_or(kind, expected):
    rule = Rule.model_validate(
        {
            "kind": kind,
            "rules": [
                {"kind": "course", "course": "A"},
                {
                    "kind": "any",
                    "rules": [{"kind": "course", "course": "B"}, {"kind": "course", "course": "C"}],
                },
            ],
        }
    )
    assert evaluate(rule, {"A": "B", "B": "F", "C": "D"}).status == expected


def test_review_cannot_be_assumed_satisfied():
    assert evaluate(Rule(kind="review", note="Permission required"), {}).status == "review"


def test_or_conditional_over_review_and_and_review_over_conditional():
    rules = [Rule(kind="course", course="A"), Rule(kind="review")]
    assert evaluate(Rule(kind="any", rules=rules), {"A": "IP"}).status == "conditional"
    assert evaluate(Rule(kind="all", rules=rules), {"A": "IP"}).status == "review"
