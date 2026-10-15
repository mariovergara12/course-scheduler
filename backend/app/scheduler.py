from datetime import timedelta
from itertools import combinations
from time import perf_counter

from schemas import Meeting, Preferences, Section

# maximum number of section candidates the search can explore
MAX_NODES = 100_000

def share_date(a: Meeting, b: Meeting, day: int) -> bool:
    #find the overlapping date range between two meetings
    first, last = max(a.start_date, b.start_date), min(a.end_date, b.end_date)

    # check whether the specified weekday occurs within that range
    # this prevents conflicts between classes held in differnet parts of the semester
    return first + timedelta(days=(day - first.weekday()) % 7) <= last

def meeting_conflict(a: Meeting, b: Meeting, travel: int = 0) -> bool:
    # add travel time when meetings are on differnt campuses
    buffer = travel if a.campus != b.campus and "Online" not in (a.campus, b.campus) else 0

    # two meetings conflict if their times ovelap (including travel),
    # they share a weekday and their date ranges overlap on that weekday
    return (
        a.start < b.end + buffer
        and b.start < a.end + buffer
        and any(share_date(a, b, day) for day in set(a.days) & set(b.days))
    )


def conflicts(a: Section, b: Section, travel: int = 0) -> bool:
    # compare every meeting in section A against every meeting in section B
    # returns True immediately if any pair conflicts
    return any(meeting_conflict(x, y, travel) for x in a.meetings for y in b.meetings)


def allowed(section: Section, pref: Preferences) -> bool:
    #reject closed, cancelled, or full sections
    if section.status != "open" or section.seats <= 0:
        return False

    # check for conflicts within the section itsef (like lecture and lab)
    # combinations() generates every unique pair of meetings
    if any(meeting_conflict(a, b, pref.travel_minutes) for a, b, in combinations(section.meetings, 2)):
        return False

    for m in section.meetings:
        # reject meetings outside the student's preferred hours
        if m.start < pref.earliest or m.end > pref.latest:
            return False

        # reject meetings overlapping the student's blocked times
        for block in pref.unavailable:
            if block.day in m.days and m.start < block.end and block.start < m.end:
                return False

    return True


def daily_meetings(sections: list[Section], day: int) -> list[Meeting]:
    # collect all meetings occuring on a given weekday
    # sort chronologically by start time
    return sorted([m for s in sections for m in s.meetings if day in m.days], key=lambda m: m.start)


def study_windows(sections: list[Section], friend: list[Section], pref: Preferences) -> list[dict]:
    """
    meant to find recurring free periods when both students are on the same campus.
    all weekly meetings block time even for partial-term sections.
    this intentionally underestimates availability to avoid false suggestions
    """
    windows = []

    # checkc mon through fri (0-4)
    for day in range(5):
        own, other = daily_meetings(sections, day), daily_meetings(friend, day)

        # both students must have classes that day
        if not own or not other:
            continue

        # identify physical campuses each student visits that day
        own_campuses = {m.campus for m in own} - {"Online"}
        friend_campuses = {m.campus for m in other} - {"Online"}

        # only suggest study time when both students use the same single campus
        # mixed-campus days are skipped because exact locations are unknown
        if len(own_campuses) != 1 or own_campuses != friend_campuses:
            continue

        # find the date range shared by all meetings from both students
        first, last = max(m.start_date for m in own + other), min(m.end_date for m in own + other)
        
        # move the first occurrence of this weekday within that range
        first += timedelta(days=(day - first.weekday()) % 7)

        if first > last:
            continue

        # limit study suggestions to 9 am - 5 pm and the student's preferences
        start, end = max(540, pref.earliest), min(1020, pref.latest)

        # treat all scheduled classes as occupied time intervals
        intervals = [(m.start, m.end) for m in own + other]

        # include the student's unavailable preiods
        intervals += [(u.start, u.end) for u in pref.unavailable if u.day == day]

        # restrict study windows to the period when both students
        # are expected to be on campus based on their class schedules
        start = max(start, own[0].start, other[0].start) 
        end = min(end, max(m.end for m in own), max(m.end for m in other))

        # cursor tracks the end of the last occupied interval
        cursor = start

        # sort occupied intervals and add a sentinel flag to check the final gap
        for a, b in sorted(intervals) + [(end, end)]:

            # keep each interval within the allowed study window
            a, b = max(start, min(a, end)), max(start, min(b,end))

            # record free periods lasting at least 30 min
            if a - cursor >= 30:
                windows.append(
                    {
                        "day": day,
                        "start": cursor,
                        "end": a,
                        "campus": next(iter(own_campuses)),
                        "start_date": first.isoformat(),
                        "end_date": last.isoformat(),
                    }
                )

            # move past the occupied interval without moving backward
            cursor = max(cursor, b)

    return windows

def score(sections: list[Section], pref: Preferences, friend: list[Section] | None = None) -> dict:
    # metrics used to evaluate how well a schedule matches preferences
    days, gap_minutes, timing_penalty = 0, 0, 0

    for day in range(7):
        meetings = daily_meetings(sections, day)

        # count the number of weekdays containing classes
        if meetings:
            days += 1

        # calculate gaps between consecutive meetings
        # zip() pairs adjacent meetings; only count gaps when dates overlap
        gap_minutes += sum(
            max(0, b.start - a.end) for a, b in zip(meetings, meetings[1:]) if share_date(a, b, day)
        )

        # penalize classes that do not match the preferred time of day
        # 720 minutes = 12:00 PM; penalties increase per 30 minutes
        for m in meetings:
            if pref.time_of_day == "morning":
                timing_penalty += max(0, m.end - 720) / 30
            elif pref.time_of_day == "afternoon":
                timing_penalty += max(0, 720 - m.start) / 30

    # find available study periods shared with a friend
    windows = study_windows(sections, friend or [], pref)

    # total shared study time in minutes
    study_minutes = sum(w["end"] - w["start"] for w in windows)

    # count matching section IDs between the student and friend
    shared = len({s.id for s in sections} & {s.id for s in friend or []})

    # social bonus depends on whether the student prioritizes
    # studying together or enrolling in the same sections
    social = (
        (study_minutes / 30 * 3 + shared * 3)
        if pref.friend_priority == "study"
        else shared * 30 + study_minutes / 60
    )

    # apply penalties for class days and gaps when those preferences are enabled
    penalty = (days * 8 if pref.compact_days else 0) + (gap_minutes / 30 * 2 if pref.avoid_gaps else 0)

    # final score: base score - penalties + social bonus
    total = round(100 - penalty - timing_penalty + social, 2)

    # generate explanations for the schedule ranking
    reasons = [f"{days} class days", f"{gap_minutes} min between classes"]

    if pref.time_of_day != "any":
        reasons.append(f"{pref.time_of_day.capitalize()} preference considered")

    if friend:
        reasons.extend([f"{study_minutes} min of shared study time", f"{shared} shared sections"])

    return {
        "score": total,
        "days": days,
        "gap_minutes": gap_minutes,
        "study_minutes": study_minutes,
        "shared_sections": shared,
        "social_bonus": round(social, 2),
        "reasons": reasons,
        "study_windows": windows,
    }


def generate(
    options: dict[str, list[Section]],
    pref: Preferences,
    friend: list[Section] | None = None,
    max_nodes: int = MAX_NODES,
) -> dict:
    # start measuring execution time
    start = perf_counter()

    # HARD CONSTRAINTS:
    # remove sections that violate availability, time, or meeting requirements
    filtered = {code: [s for s in choices if allowed(s, pref)] for code, choices in options.items()}

    # find courses that have no valid sections remaining
    no_options = [code for code, choices in filtered.items() if not choices]

    # stop immediately if any requested course cannot be scheduled
    if no_options:
        return {
            "schedules": [],
            "nodes": 0,
            "valid_count": 0,
            "truncated": False,
            "elapsed_ms": 0,
            "messages": [f"No available sections satisfy your hard constraints for {c}." for c in no_options],
        }

    # search courses with the fewest section options first
    # this helps detect impossible schedules earlier and reduces wasted searching
    ordered = sorted(filtered, key=lambda code: (len(filtered[code]), code))

    # best: top three schedules found
    # nodes: number of section candidates attempted
    # valid_count: number of complete valid schedules found
    # truncated: whether the search stopped due to its limit
    best, nodes, valid_count, truncated = [], 0, 0, False

    # recursive backtracking algorithm for building schedules
    def visit(chosen: list[Section], index: int):
        nonlocal nodes, valid_count, truncated

        # BASE CASE:
        # all requested courses have been assigned compatible sections
        if index == len(ordered):
            valid_count += 1

            # SOFT CONSTRAINTS:
            # rank the complete schedule using student preferences
            metrics = score(chosen, pref, friend)

            # convert Pydantic sections into JSON-compatible dictionaries
            result = {
                "sections": [s.model_dump(mode="json") for s in sorted(chosen, key=lambda s: s.course_code)],
                **metrics,
            }

            # add the schedule and sort by highest score
            # section IDs provide a consistent tie-breaking order
            best.append(result)
            best.sort(key=lambda x: (-x["score"], tuple(s["id"] for s in x["sections"])))

            # retain only the three highest-ranked schedules
            del best[3:]
            return

        # RECURSIVE CASE:
        # try each available section for the current course
        for section in filtered[ordered[index]]:

            # stop searching when the maximum number of attempts is reached
            if nodes >= max_nodes:
                truncated = True
                return

            nodes += 1

            # only continue if this section does not conflict
            # with any previously selected section
            if not any(conflicts(section, other, pref.travel_minutes) for other in chosen):

                # choose this section and move to the next course
                # a new list is created, leaving the previous selection unchanged
                visit(chosen + [section], index + 1)

            # stop exploring additional branches if the limit was reached
            if truncated:
                return

    # begin searching with no selected sections, starting at course index 0
    visit([], 0)

    # return the best schedules and search statistics
    return {
        "schedules": best,
        "nodes": nodes,
        "valid_count": valid_count,
        "truncated": truncated,
        "elapsed_ms": round((perf_counter() - start) * 1000, 2),
        "messages": (
            ["Search limit reached. These are the best schedules found, not guaranteed global optima."]
            if truncated
            else []
        )
        + (
            ["No conflict-free combination exists. Try fewer courses or wider available hours."]
            if not best
            else []
        ),
    }


