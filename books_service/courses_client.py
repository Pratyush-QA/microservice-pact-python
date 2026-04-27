"""
Courses Service HTTP Client
============================
This module makes all HTTP calls from BooksCatalogue to CoursesCatalogue.
It is the ONLY place in the consumer service that communicates with the provider.

BASE_URL is looked up at call time (not at import time) so that in Pact
consumer tests, patching BASE_URL redirects all calls to the mock server.
The actual app.py code never changes — only BASE_URL is patched in tests.
"""

import requests

# Provider service URL.
# In Pact consumer tests, this is patched to pact.uri (mock server URL).
# In production, this would come from an environment variable.
BASE_URL = "http://localhost:8181"


def get_all_courses(base_url=None):
    """
    Calls GET /allCourseDetails on the Courses service.
    Returns: [{course_name, id, price, category}, ...]

    base_url is only passed directly in Pact tests.
    In production (called from app.py), base_url is None so BASE_URL is used.
    BASE_URL is patched in Pact tests to point at the mock server.
    """
    url = base_url or BASE_URL      # looks up BASE_URL at call time — patch works
    response = requests.get(f"{url}/allCourseDetails")
    response.raise_for_status()
    return response.json()


def get_course_by_name(name: str, base_url=None):
    """
    Calls GET /getCourseByName/{name} on the Courses service.
    Returns: {course_name, id, price, category}
    Returns None if the course does not exist (404).

    base_url is only passed directly in Pact tests.
    In production (called from app.py), base_url is None so BASE_URL is used.
    BASE_URL is patched in Pact tests to point at the mock server.
    """
    url = base_url or BASE_URL      # looks up BASE_URL at call time — patch works
    response = requests.get(f"{url}/getCourseByName/{name}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()
