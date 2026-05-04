"""
Auto-publish Pact contract to PactFlow after consumer tests pass.
=================================================================
This conftest.py runs automatically when pytest finishes the consumer
test session. If all tests passed AND PACT_BROKER_TOKEN is set, it
publishes the generated contract JSON to PactFlow automatically.

HOW it works:
  1. pytest runs all tests in tests/consumer/
  2. pactman writes contract to pacts/BooksCatalogue-CoursesCatalogue-pact.json
  3. pytest_sessionfinish hook fires after all tests complete
  4. If exitstatus == 0 (all passed) → publish to PactFlow + set branch
  5. If exitstatus != 0 (some failed) → skip publish, print warning
"""

import json
import os
import requests


PACT_BROKER_URL = "https://deepintent.pactflow.io"
PACT_FILE       = "pacts/BooksCatalogue-CoursesCatalogue-pact.json"


def pytest_sessionfinish(session, exitstatus):
    """
    Called by pytest automatically after the entire test session ends.

    exitstatus:
      0 → all tests passed  → publish contract
      non-0 → tests failed  → skip publish
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
        print(f"\n[PactFlow] Skipping auto-publish — pact file not found: {PACT_FILE}")
        return

    # ── Load pact JSON ────────────────────────────────────────────────────────
    with open(PACT_FILE) as f:
        pact = json.load(f)

    consumer = pact["consumer"]["name"]                        # "BooksCatalogue"
    provider = pact["provider"]["name"]                        # "CoursesCatalogue"
    version  = os.environ.get("CONSUMER_VERSION", "1.0.3")
    branch   = os.environ.get("CONSUMER_BRANCH", "main")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    print(f"\n[PactFlow] Auto-publishing contract...")
    print(f"  Consumer : {consumer}")
    print(f"  Provider : {provider}")
    print(f"  Version  : {version}")
    print(f"  Branch   : {branch}")

    # ── Step 1: Publish contract to PactFlow ──────────────────────────────────
    url = f"{PACT_BROKER_URL}/pacts/provider/{provider}/consumer/{consumer}/version/{version}"
    response = requests.put(url, json=pact, headers=headers)

    if response.status_code not in (200, 201):
        print(f"[PactFlow] ❌ Publish failed — HTTP {response.status_code}")
        print(f"  Response: {response.text}")
        return

    print(f"[PactFlow] ✅ Contract published successfully!")

    # ── Step 2: Associate consumer version with branch ────────────────────────
    # Uses the Pact Broker branches API — URL structure creates the association.
    branch_url = f"{PACT_BROKER_URL}/pacticipants/{consumer}/branches/{branch}/versions/{version}"
    branch_res = requests.put(branch_url, headers=headers)
    if branch_res.status_code in (200, 201):
        print(f"[PactFlow] ✅ Version {version} associated with branch '{branch}'")
    else:
        print(f"[PactFlow] ⚠ Branch association failed: HTTP {branch_res.status_code} — {branch_res.text[:300]}")

    # ── Step 3: Set mainBranch on both pacticipants ───────────────────────────
    # Tells PactFlow which branch is "main" so the Applications dashboard
    # shows "main branch version: {version}" instead of "not found".
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
            print(f"[PactFlow] ⚠ mainBranch failed for {participant}: HTTP {mb_res.status_code}")

    print(f"  View at: {PACT_BROKER_URL}/pacts/provider/{provider}/consumer/{consumer}/latest")
