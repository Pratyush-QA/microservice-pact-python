"""
Pact PROVIDER Tests — CoursesCatalogue
========================================
The provider (CoursesCatalogue) fetches the contract from the PactFlow cloud
broker and verifies that the REAL service satisfies every interaction.

HOW PACT PROVIDER TESTING WORKS (with cloud broker):
  1. Consumer tests run and generate the contract JSON locally.
  2. Consumer publishes the contract to PactFlow:
         python scripts/publish_pact.py
  3. This test starts the REAL Courses service (FastAPI on port 8181).
  4. A state server is started on port 8182 — it sets up the DB before each interaction.
  5. Pactman fetches ALL contracts for "CoursesCatalogue" from PactFlow and
     replays every interaction:
       - Calls the state server to set up DB (e.g., insert/delete Appium record)
       - Sends the exact request from the contract to the real service
       - Checks the real response matches what the consumer defined
  6. If all interactions pass → Provider satisfies the contract ✅
     If any fail → Provider is BROKEN for that consumer ❌

WHY CLOUD BROKER (PactFlow) instead of local JSON file?
  - Contract lives centrally — any teammate can run provider tests without
    needing the consumer to run first on the same machine
  - PactFlow UI shows the compatibility matrix (who depends on whom)
  - Works in CI/CD — provider pipeline fetches contract automatically
  - Supports versioning and tagging (e.g. "production", "main" branch)

HOW TO SET UP (one-time per machine):
  Set your PactFlow API token as an environment variable:
    Windows PowerShell:
      $env:PACT_BROKER_TOKEN = "your-read-write-token-here"
    Mac/Linux:
      export PACT_BROKER_TOKEN=your-read-write-token-here
  Token source: https://deepintent.pactflow.io → Settings → API Tokens

WHY STATE HANDLERS?
  Each interaction has a "given" condition. The real DB must be in the right
  state before each interaction is verified. State handlers set up (insert/delete)
  records before each interaction runs.

WHY A SEPARATE STATE SERVER (port 8182)?
  Pactman sends HTTP POST to this server before each interaction.
  The server calls the matching state handler function.
"""

import socket
import threading
import time
import sys
import os
import logging
import pytest
import requests
from functools import partial

# Make sure Python can find courses_service from the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from courses_service.app import app, SessionLocal, CourseModel
import uvicorn

# ── PactFlow Configuration ────────────────────────────────────────────────────
# URL of the cloud Pact Broker — not a secret, safe to hardcode
PACT_BROKER_URL = "https://deepintent.pactflow.io"

# API token — read from environment variable, NEVER hardcode
# Set it: $env:PACT_BROKER_TOKEN = "your-token"   (PowerShell)
#         export PACT_BROKER_TOKEN=your-token      (Mac/Linux)
PACT_BROKER_TOKEN = os.environ.get("PACT_BROKER_TOKEN")

# Provider name — must match exactly what the consumer declared in the pact
PROVIDER_NAME = "CoursesCatalogue"

PROVIDER_PORT = 8181   # Port where the real Courses service runs during tests


# ── Helper ────────────────────────────────────────────────────────────────────

def _port_in_use(port: int) -> bool:
    """
    Returns True if something is already listening on the given port.
    Used by fixtures to avoid trying to start a server on an occupied port.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


# ── Step 1: Server that runs the REAL Courses service ─────────────────────────
# We run the real FastAPI app in a background thread so pactman can send
# real HTTP requests to it during verification.

class ProviderServer(threading.Thread):
    """Runs the real Courses service in a background daemon thread."""

    def __init__(self, port: int):
        super().__init__(daemon=True)   # daemon=True means it stops when tests end
        self.port    = port
        config       = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self._server = uvicorn.Server(config)

    def run(self):
        self._server.run()

    def stop(self):
        self._server.should_exit = True


# ── Step 2: Provider State Handlers ──────────────────────────────────────────
# These functions prepare the database BEFORE each interaction is verified.
# Each function matches a "given(...)" condition defined in the consumer test.
#
# consumer said:  pact.given("courses exist")
# provider does:  state_courses_exist() → deletes all + inserts 3 courses
#
# consumer said:  pact.given("Course Appium exist")
# provider does:  state_appium_course_exist() → ensures Appium row is present
#
# consumer said:  pact.given("Course Appium does not exist")
# provider does:  state_appium_course_not_exist() → deletes Appium row

def state_courses_exist():
    """
    Called before verifying the /allCourseDetails interaction.
    Deletes all existing rows and reinserts 3 fresh courses.

    WHY delete-then-insert instead of "insert if empty"?
      Pactman has a bug: when verifying EachLike arrays, it applies the
      array's 'min' constraint as a string length check on individual fields.
      Short IDs like "2" or "12" (length < 3) fail this check with min=3.
      Fix: use IDs with at least 3 characters ("c02", "c03", "c12").
      Delete-then-insert ensures the DB always has the correct IDs,
      even if the running server was seeded with old data.
    """
    db = SessionLocal()
    try:
        db.query(CourseModel).delete()        # clear stale data first
        db.add_all([
            CourseModel(course_name="Microservices testing", id="c02", price=23, category="api"),
            CourseModel(course_name="Selenium",              id="c03", price=66, category="web"),
            CourseModel(course_name="Appium",                id="c12", price=13, category="mobile"),
        ])
        db.commit()
    finally:
        db.close()


def state_appium_course_exist():
    """
    Called before verifying the /getCourseByName/Appium (200) interaction.
    Ensures Appium exists in DB so the endpoint returns it (not 404).
    """
    db = SessionLocal()
    try:
        exists = db.query(CourseModel).filter(CourseModel.course_name == "Appium").first()
        if not exists:
            db.add(CourseModel(course_name="Appium", id="c12", price=13, category="mobile"))
            db.commit()
    finally:
        db.close()


def state_appium_course_not_exist():
    """
    Called before verifying the /getCourseByName/Appium (404) interaction.
    Deletes Appium from DB so the endpoint returns 404 — matching consumer's expectation.
    """
    db = SessionLocal()
    try:
        db.query(CourseModel).filter(CourseModel.course_name == "Appium").delete()
        db.commit()
    finally:
        db.close()


# Map: state name (from contract) → function to call
# pactman reads the "given" value from the contract and looks it up here
STATE_HANDLERS = {
    "courses exist":                state_courses_exist,
    "Course Appium exist":          state_appium_course_exist,
    "Course Appium does not exist": state_appium_course_not_exist,
}


# ── Step 3: State Server — receives state requests from pactman ───────────────
# pactman POSTs to this server before each interaction.
# This server calls the matching state handler to set up the DB.

from fastapi import FastAPI as _FastAPI, Request as _Request

state_app = _FastAPI()

@state_app.post("/_pact/provider_states")
async def provider_states(request: _Request):
    """
    pactman calls this before each interaction with a payload like:
        {"state": "Course Appium exist"}
    We look up the matching handler and call it to set up the DB.
    """
    body    = await request.json()
    state   = body.get("state", "")
    handler = STATE_HANDLERS.get(state)
    if handler:
        handler()    # set up the DB for this state
    return {"result": state}


# ── Step 4: Pytest Fixtures — start both servers before tests run ─────────────

@pytest.fixture(scope="module")
def provider_server():
    """
    Starts the real Courses service and waits until it responds.
    Scope="module" means it starts once for all tests in this file.

    If port 8181 is already in use (e.g. from a previous run or a manually
    started service), we skip starting a new one and use the existing server.
    """
    server = None

    if _port_in_use(PROVIDER_PORT):
        # The Port is already occupied — assume the Courses service is running there.
        print(f"\n[provider_server] Port {PROVIDER_PORT} already in use — using existing server.")
    else:
        # Port is free — start our own Courses service in a background thread.
        server = ProviderServer(PROVIDER_PORT)
        server.start()

    # Either way, poll until the server responds (up to 9 seconds)
    for _ in range(30):
        try:
            r = requests.get(f"http://127.0.0.1:{PROVIDER_PORT}/allCourseDetails", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.3)

    yield f"http://127.0.0.1:{PROVIDER_PORT}"

    # Only stop if we started it; don't kill an externally started server
    if server:
        server.stop()


@pytest.fixture(scope="module")
def state_server():
    """
    Starts the state-setup server on port 8182.
    Pactman will POST to this before each interaction.
    """
    class StateServer(threading.Thread):
        def __init__(self):
            super().__init__(daemon=True)
            cfg          = uvicorn.Config(state_app, host="127.0.0.1", port=8182, log_level="warning")
            self._server = uvicorn.Server(cfg)
        def run(self):
            self._server.run()
        def stop(self):
            self._server.should_exit = True

    srv = StateServer()
    srv.start()
    time.sleep(1)   # give it a moment to fully start
    yield "http://127.0.0.1:8182"
    srv.stop()


# ── Step 5: The actual Provider Verification Test ─────────────────────────────

def test_pact_provider(provider_server, state_server):
    """
    Fetches ALL consumer contracts for CoursesCatalogue from PactFlow
    and verifies the real service satisfies every interaction.

    Flow:
      pactman → PactFlow API → downloads contract JSON(s)
               → for each consumer (BooksCatalogue, ...):
                   → for each interaction in contract:
                       a. POST-state to state_server → DB set up
                       b. Send request to provider_server → real response
                       c. Compare real response vs. contract → PASS / FAIL

    BEFORE RUNNING THIS TEST:
      1. Run consumer tests:    pytest tests/consumer/ -v
      2. Publish to PactFlow:   python scripts/publish_pact.py
      3. Set token env var: $env:PACT_BROKER_TOKEN = "your-token"
      4. Run this test:         pytest tests/provider/ -v -s

    If this passes → consumer and provider are compatible ✅
    If this fails → provider changed something that breaks the consumer ❌
    """
    from pactman.verifier.broker_pact import BrokerPacts, PactBrokerConfig
    from pactman.verifier.result import CaptureResult

    # Validate token is set
    if not PACT_BROKER_TOKEN:
        raise EnvironmentError(
            "\n\nPACT_BROKER_TOKEN environment variable is not set.\n"
            "Set it before running provider tests:\n\n"
            "  Windows PowerShell:\n"
            "    $env:PACT_BROKER_TOKEN = 'your-read-write-token-here'\n\n"
            "  Mac/Linux:\n"
            "    export PACT_BROKER_TOKEN=your-read-write-token-here\n\n"
            "Get the token: https://deepintent.pactflow.io → Settings → API Tokens\n"
        )

    # PactBrokerConfig connects to PactFlow using the bearer token.
    # It fetches all consumer pacts published for the given provider.
    # Url = PactFlow account URL
    # token = bearer token from PactFlow (read from env var, never hardcoded)
    broker_config = PactBrokerConfig(
        url=PACT_BROKER_URL,
        token=PACT_BROKER_TOKEN,
    )

    # CaptureResult collects pass/fail info for each interaction.
    result_factory = partial(CaptureResult, level=logging.INFO)

    # BrokerPacts fetches ALL contracts where CoursesCatalogue is the provider.
    # If BooksCatalogue and another consumer both depend on CoursesCatalogue,
    # BOTH contracts are fetched and verified here automatically.
    # No hardcoded file paths — contracts come from PactFlow.
    pacts = BrokerPacts(PROVIDER_NAME, broker_config, result_factory).consumers()

    success = True
    for pact in pacts:
        print(f"\n  Verifying pact: {pact.consumer} → {pact.provider}")
        for interaction in pact.interactions:
            # For each interaction in the contract:
            #   a. Pactman POSTs {"state": "..."} to state_server → DB set up
            #   b. pactman sends the request to provider_server → real response
            #   c. Pactman compares real response vs contract spec → PASS/FAIL
            interaction.verify(
                provider_server,                        # "http://127.0.0.1:8181"
                f"{state_server}/_pact/provider_states", # "http://127.0.0.1:8182/..."
            )
            success = interaction.result.success and success

    assert success, (
        "Pact verification FAILED — provider does not satisfy the consumer contract.\n"
        f"Check the output above for which interactions failed.\n"
        f"View contract at: {PACT_BROKER_URL}"
    )
