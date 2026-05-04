"""
Auto-publish Pact contract to PactFlow after consumer tests pass.
=================================================================
This conftest.py runs automatically when pytest finishes the consumer
test session. If all tests passed AND PACT_BROKER_TOKEN are set, it
publishes the generated contract JSON to PactFlow automatically.

WHY conftest.py and not a fixture?
  Pytest_sessionfinish is a hook that runs AFTER all tests complete.
  It gives us the final exit status (0 = all passed, 1 = some failed).
  We only publish when tests actually passed — no point publishing a
  broken contract.

HOW it works:
  1. Pytest runs all tests in tests/consumer/
  2. Pactman writes contract to pacts/BooksCatalogue-CoursesCatalogue-pact.json
  3. Pytest_sessionfinish fires
  4. If exitstatus == 0 (all passed) → publish to PactFlow automatically
  5. If exitstatus != 0 (some failed) → skip publish, print warning

RESULT:
  Before: pytest tests/consumer/ -v then python scripts/publish_pact.py
  After:  pytest tests/consumer/ -v (publish happens automatically)
"""

import json
import os
import requests


PACT_BROKER_URL  = "https://deepintent.pactflow.io"
PACT_FILE        = "pacts/BooksCatalogue-CoursesCatalogue-pact.json"


def pytest_sessionfinish(session, exitstatus):
    """
    Called by pytest automatically after the entire test session ends.

    Exitstatus:
      0 → all tests passed
      1 → some tests failed
      2 → interrupted
      3 → internal error

    We only publish when exitstatus == 0 — contract is only valid
    when all consumer tests have passed.
    """

    # Only publish if all consumer tests passed
    if exitstatus != 0:
        print(
            f"\n[PactFlow] Skipping publish — tests did not all pass "
            f"(exitstatus={exitstatus}). Fix failing tests first."
        )
        return

    # Only publish if token is set
    token = os.environ.get("PACT_BROKER_TOKEN")
    if not token:
        print(
            "\n[PactFlow] Skipping auto-publish — PACT_BROKER_TOKEN not set.\n"
            "  Set it with: $env:PACT_BROKER_TOKEN = 'your-token'\n"
            "  Or run manually: python scripts/publish_pact.py"
        )
        return

    # Only publish if a pact file was generated
    if not os.path.exists(PACT_FILE):
        print(
            f"\n[PactFlow] Skipping auto-publish — pact file not found: {PACT_FILE}"
        )
        return

    # ── Publish to PactFlow ───────────────────────────────────────────────────
    with open(PACT_FILE) as f:
        pact = json.load(f)

    consumer = pact["consumer"]["name"]   # "BooksCatalogue"
    provider = pact["provider"]["name"]   # "CoursesCatalogue"
    version  = os.environ.get("CONSUMER_VERSION", "1.0.2")
    branch   = os.environ.get("CONSUMER_BRANCH", "main")

    url = (
        f"{PACT_BROKER_URL}/pacts/provider/{provider}"
        f"/consumer/{consumer}/version/{version}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    print(f"\n[PactFlow] Auto-publishing contract...")
    print(f"  Consumer : {consumer}")
    print(f"  Provider : {provider}")
    print(f"  Version  : {version}")
    print(f"  Branch   : {branch}")

    response = requests.put(url, json=pact, headers=headers)

    if response.status_code not in (200, 201):
        print(f"[PactFlow] ❌ Publish failed — HTTP {response.status_code}")
        print(f"  Response: {response.text}")
        return

    print(f"[PactFlow] ✅ Contract published successfully!")

    # ── Set branch on version — use PUT (create/update) not PATCH ────────────
    # PUT /pacticipants/{consumer}/versions/{version} is the correct REST
    # "create or update" endpoint. PATCH was returning 200 but ignoring branch.
    branch_url = f"{PACT_BROKER_URL}/pacticipants/{consumer}/versions/{version}"
    branch_res = requests.put(
        branch_url,
        json={"branch": branch},
        headers=headers,
    )
    if branch_res.status_code in (200, 201):
        print(f"[PactFlow] ✅ Version branch set to '{branch}' (HTTP {branch_res.status_code})")
    else:
        print(f"[PactFlow] ⚠ Branch PUT failed: HTTP {branch_res.status_code} — {branch_res.text[:300]}")

    # ── Set mainBranch on pacticipant (one-time, idempotent) ─────────────────
    # Tells PactFlow which branch is "main" so the Applications dashboard
    # can display "main branch version: 1.0.1" instead of "not found".
    for participant in [consumer, provider]:
        mb_url = f"{PACT_BROKER_URL}/pacticipants/{participant}"
        mb_res = requests.patch(
            mb_url,
            json={"mainBranch": branch},
            headers={**headers, "Content-Type": "application/merge-patch+json"},
        )
        if mb_res.status_code in (200, 201):
            print(f"[PactFlow] ✅ mainBranch='{branch}' for {participant}")
        else:
            print(f"[PactFlow] ⚠ mainBranch failed for {participant}: HTTP {mb_res.status_code} — {mb_res.text[:300]}")

    print(
        f"  View at: {PACT_BROKER_URL}/pacts/provider/"
        f"{provider}/consumer/{consumer}/latest"
    )
