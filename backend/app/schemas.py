"""
data models for the course scheduler API

these models will define the structure of data entering and leaving
the app, including courses, sections, schedules, and users

pydantic handles validation to ensure incoming data follows
the expected structure before it reaches the business lgoic

the same models are used for API requests and imported snapshots
"""
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# supported course grades
Grade = Literal ["A", "B", "C", "D", "F", "P", "IP", "W"]

# Supported course grades
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

# defines course prereq requirements
class Rule(StrictModel):
    kind: Literal ["course", "all", "any", "review"]
    course: str | None = None
    minimum: Literal["A", "B", "C", "D", "P"] = "C"
    rules: list["Rule"] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=400)
    
    @model_validator(mode="after")
    def valid_tree(self):
        # course rules require a course code
        if self.kind == "course" and not self.rules:
            raise ValueError("AND/OR rules need childre")
        return self

# represents a scheduled class meeting
class Meeting(StrictModel):
    days: list[int] = Field(min_length=1, max_length=7)
    start: int = Field(ge=0, lt=1440)
    end: int = Field(gt=0, le=1440)
    start_date: date
    end_date: date
    campus: Literal["Edinburg", "Brownsville", "Online"] = "Edinburg"
    location: str = Field(default="", max_length=120)
    kind: Literal["Lecture", "Lab", "Seminar"] = "Lecture"

    @model_validator(mode="after")
    def valid_interval(self):
        # ensure meeting times and dates are valid
        if self.end <= self.start or self.end_date < self.start_date:
            raise ValueError("Meeting ends must follow starts; overnight meetings are unsupported")

        # check for duplicate or invalid weekdays (0 = monday, 6 = sunday)
        if len(set(self.days)) != len(self.days) or any(d not in range(7) for d in self.days):
            raise ValueError("Days must be distinct weekdays 0 (Monday) through 6 (Sunday)")
        return self

# course information from the actual univesity catalog 
class Course(StrictModel):
    code: str = Field(pattern=r"^[A-Z]{2,5} \d{4}$")
    title: str = Field(min_length=1, max_length=150)
    credits: int = Field(ge=1, le=6)
    category: str = Field(min_length=1, max_length=80)
    description: str = Field(max_length=1000)
    prerequisite: Rule | None = None
    recommended: bool = False


# represents a specific section of the course
class Section(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    course_code: str
    number: str = Field(min_length=1, max_length=20)
    instructor: str = Field(min_length=1, max_length=100)
    seats: int = Field(ge=0, le=1000)
    status: Literal["open", "closed", "cancelled"] = "open"
    modality: Literal["In person", "Online", "Hybrid"] = "In person"
    meetings: list[Meeting] = Field(default_factory=list, max_length=12)
    linked_lab: bool = False

    @model_validator(mode="after")
    def complete_bundle(self):
        # in person and hybrid sections MUST have meeting times 
        if self.modality != "Online" and not self.meetings:
            raise ValueError("In-person/hybrid sections need meeting information")

        # linked labs must be included in the section's meetings
        if self.linked_lab and not any(m.kind == "Lab" for m in self.meetings):
            raise ValueError("A linked lab must be imported in the same atomic section bundle")
        return self


# stores a validated copy of course and section data
class Snapshot(StrictModel):
    term: str = Field(pattern=r"^(Fall|Spring|Summer) \d{4}$")
    catalog_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    source_url: str = Field(pattern=r"^https://", max_length=500)
    checked_at: datetime
    synthetic: bool
    label: str = Field(min_length=1, max_length=200)
    courses: list[Course] = Field(min_length=1, max_length=500)
    sections: list[Section] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def consistent_snapshot(self):
        codes = [c.code for c in self.courses]
        ids = [s.id for s in self.sections]

        # prevent duplicate courses or sections
        if len(set(codes)) != len(codes) or len(set(ids)) != len(ids):
            raise ValueError("Duplicate course codes or section IDs")

        # ensure every section belongs to an imported course
        if any(s.course_code not in codes for s in self.sections):
            raise ValueError("Every section must reference an imported course")
        
        # timestamp must include a timezone and cannot be in the future
        if self.checked_at.tzinfo is None or self.checked_at > datetime.now(timezone.utc):
            raise ValueError("Last-checked timestamp must be timezone-aware and not in the future")

        # recursively validate prereq references
        for course in self.courses:

            def check(rule):
                if not rule:
                    return
                if rule.kind == "course" and rule.course not in codes:
                    raise ValueError(f"Unknown prerequisite {rule.course}")
                for child in rule.rules:
                    check(child)

            check(course.prerequisite)
        return self


# defines times when a student cannot attend classes
class Unavailable(StrictModel):
    day: int = Field(ge=0, le=6)
    start: int = Field(ge=0, lt=1440)
    end: int = Field(gt=0, le=1440)

    @model_validator(mode="after")
    def valid_interval(self):
        # end time must be after start time
        if self.end <= self.start:
            raise ValueError("Unavailable time must end after it starts")
        return self


# student preferences used to generate and rank schedules 
class Preferences(StrictModel):
    earliest: int = Field(default=480, ge=0, lt=1440)
    latest: int = Field(default=1080, gt=0, le=1440)
    compact_days: bool = True
    avoid_gaps: bool = True
    time_of_day: Literal["any", "morning", "afternoon"] = "any"
    travel_minutes: int = Field(default=60, ge=0, le=180)
    unavailable: list[Unavailable] = Field(default_factory=list, max_length=35)
    allow_conditional: bool = False
    friend_plan_id: str | None = None
    friend_priority: Literal["study", "sections"] = "study"

    @model_validator(mode="after")
    def valid_hours(self):
        # ensure the preferred time window is valid 
        if self.latest <= self.earliest:
            raise ValueError("Latest class time must follow earliest class time")
        return self


# input received when a student requests generated schedules
class GenerateRequest(StrictModel):
    course_codes: list[str] = Field(min_length=1, max_length=8)
    preferences: Preferences = Field(default_factory=Preferences)

    @model_validator(mode="after")
    def unique_courses(self):
        # prevent selecting the same course multiple times
        if len(set(self.course_codes)) != len(self.course_codes):
            raise ValueError("Select each course only once")
        return self


# stores a student's completed or in-progress course
class ProgressInput(StrictModel):
    course_code: str
    grade: Grade


# basic student profile info
class ProfileInput(StrictModel):
    name: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    major: Literal["Computer Science"] = "Computer Science"
    catalog_year: Literal["2026-2027"] = "2026-2027"


# input for saving a schedule plan
class PlanInput(StrictModel):
    name: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    section_ids: list[str] = Field(min_length=1, max_length=8)
    preferences: Preferences = Field(default_factory=Preferences)


# input for sending a friend request
class FriendRequest(StrictModel):
    handle: str = Field(min_length=3, max_length=80)


# input for sharing a plan with a friend
class ShareInput(StrictModel):
    friend_id: str
