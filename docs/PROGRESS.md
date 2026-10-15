# Course Scheduler — Development Progress

**Last Updated:** October 14, 2026

## What I've Done So Far

I've been working on the backend of our course scheduler, focusing on the logic that will eventually allow students to find courses they're eligible for and generate schedules based on their preferences.

### 1. Project Setup
- Set up the Python project and its dependencies.
- Configured pytest for testing and Ruff for checking code quality.
- Created a virtual environment to keep dependencies organized.
- Updated `.gitignore` to prevent unnecessary files from being uploaded to GitHub.

### 2. Course Data Models (`schemas.py`)
- Created the data structures that represent courses, class sections, meeting times, prerequisites, and scheduling preferences.
- Added validation to make sure the data follows the expected format.
- Set up prerequisite rules that can handle multiple course requirements.

### 3. Course Eligibility (`eligibility.py`)
- Implemented the logic for determining whether a student meets a course's prerequisites.
- Added support for checking completed courses and minimum grade requirements.
- Implemented AND/OR prerequisite conditions. For example, a course might require both Calculus I and Programming I, or allow either of two courses.
- Added handling for courses that are currently in progress or require further review.

### 4. Scheduling Algorithm (`scheduler.py`)
- Implemented the core scheduling logic.
- Added functionality to detect time conflicts between classes.
- Created logic for generating possible schedules and ranking them based on student preferences.
- Added functionality to identify potential study windows when two friends are on the same campus.
- Included limits to prevent the algorithm from searching through too many combinations.

### 5. Testing
- Created `test_eligibility.py` and `test_scheduler.py`.
- Tested prerequisite requirements, grade rules, schedule conflicts, and scheduling behavior.
- Fixed several issues discovered during testing, including prerequisite validation and Python imports.
- **All 37 tests are currently passing.**

## What We Should Do Next

### Step 1: Database
**File:** `backend/app/database.py`

We need to set up how our application stores information, including student accounts, completed courses, course data, and saved schedules.

### Step 2: Sample Course Data
**File:** `scripts/create_demo_data.py`

Create a small collection of realistic courses, prerequisites, and sections so we can test the application without depending on live university data.

### Step 3: Importing Data
**Files:** `backend/app/importer.py`, `backend/app/seed.py`

Implement the logic for loading course information into the database and setting up sample student accounts.

### Step 4: Authentication and API
**Files:** `backend/app/auth.py`, `backend/app/api.py`, `backend/app/main.py`

Connect the backend components so the frontend can request eligible courses, generate schedules, save plans, and access student information.

We'll also need to implement calendar export and additional backend tests.

### Step 5: Frontend
Once the backend is connected, we can start building the interface where students will be able to:

- Enter their major, minor, and completed courses.
- Select scheduling preferences.
- Generate and compare schedules.
- View their schedules on a weekly calendar.
- Save their preferred schedules.
- Add friends and find opportunities to study or spend time together.

## Current Status

The core scheduling and prerequisite logic has been implemented and tested. We don't have a complete working application yet, but the main algorithms are in place.

**Our next priority should be connecting these components to a database and testing them with realistic course information.** After that, we can work toward getting the backend and frontend communicating with each other.
