"""
Pact CONSUMER Tests — BooksCatalogue
=====================================
These tests verify that BooksCatalogue (consumer) correctly integrates
with CoursesCatalogue (provider) by defining a contract.

HOW IT WORKS:
─────────────
  Step 1 — Define the contract:
            Tell Pact what HTTP request the consumer will make
            and what response it expects from the provider.

  Step 2 — Start Pact mock server:
            'with pact': starts a real HTTP server on port 9999.
            This mock server is preloaded with the contract you defined in Step 1.
            It knows: "when GET /allCourseDetails arrives → respond with mock data"
            The real CoursesCatalogue service does NOT need to be running.

  Step 3 — Patch BASE_URL in courses_client.py:
            'with patch(BASE_URL, pact.uri)' temporarily replaces:
                BASE_URL = "http://localhost:8181"  (real provider)
            with:
                BASE_URL = "http://localhost:9999"  (Pact mock server)
            Now when app.py internally calls get_all_courses() or
            get_course_by_name(), those HTTP calls go to the mock server.
            app.py code is NEVER changed — only BASE_URL is redirected.
            When 'with patch' block exits, BASE_URL goes back to the original.

  Step 4 — Call the actual consumer service endpoint (via TestClient):
            'client.get("/getProductPrices")' calls the real app.py endpoint.
            Internally app.py calls courses_client.py → hits mock server.
            This is correct — we test the real consumer code end-to-end,
            not the HTTP client (courses_client.py) in isolation.

  Step 5 — 'with pact': block exits:
            Mock server stops.
            Pact checks all registered interactions were actually called.
            If yes, → writes contract to pacts/BooksCatalogue-CoursesCatalogue.json

  Step 6 — Assert consumer behaviour:
            Verify the consumer endpoint produced correct output.

WHY TestClient?
───────────────
  FastAPI's TestClient lets us call our own service endpoints in tests
  without starting a real server. It simulates real HTTP requests to app.py.

WHY patch BASE_URL instead of passing mock URL to app.py?
──────────────────────────────────────────────────────────
  app.py should never know about Pact or mock servers.
  By patching BASE_URL in courses_client.py, the mock server is
  transparently injected — app.py code stays exactly as it is in production.

IMPORTANT — ONLY INCLUDE FIELDS THE CONSUMER ACTUALLY USES:
─────────────────────────────────────────────────────────────
  The contract must only include fields this consumer reads in its code.
  If app.py only does c["price"], only "price" goes in the contract.
  Provider can return 10 other fields — Pact ignores them, tests still pass.
  This is the core principle of Consumer-Driven Contract Testing:
    - Each consumer owns its own contract
    - Provider is only responsible for satisfying each consumer's specific needs
    - Unused fields are invisible to this consumer's contract — other consumers
      can catch changes to those fields via their own contracts
"""

from unittest.mock import patch
from fastapi.testclient import TestClient
from pactman import Consumer, Provider, EachLike, Like

# Import the actual consumer app — we test real endpoints, not helper functions
from books_service.app import app

# TestClient simulates HTTP calls to our consumer service (app.py).
# It triggers the startup event automatically, which seeds the books DB.
# No real server is started — TestClient handles everything in memory.

client = TestClient(app)

# ── Pact setup ─────────────────────────────────────────────────────────────────
# Consumer("BooksCatalogue")  → name of this service (consumer)
# Provider("CoursesCatalogue") → name of the service we depend on (provider)
# pact_dir → folder where the contract JSON file will be saved after tests passed
# port     → port number on which Pact mock server will run during tests
PACT_DIR  = "pacts"
MOCK_PORT = 9999

pact = Consumer("BooksCatalogue").has_pact_with(
    Provider("CoursesCatalogue"),
    pact_dir=PACT_DIR,
    port=MOCK_PORT,
)


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: /getProductPrices — consumer combines book prices + course prices
# ─────────────────────────────────────────────────────────────────────────────
def test_all_courses_price_sum():
    """
    Tests the /getProductPrices endpoint of BooksCatalogue.

    Full call chain during this test:
      TestClient.get("/getProductPrices")
           ↓
      app.py: get_product_prices()         ← real consumer business logic runs
           ↓
      courses_client.get_all_courses()     ← real HTTP client function runs
           ↓
      requests.get("localhost:9999/allCourseDetails")  ← hits Pact mock server
           ↓
      Mock server returns 3 items with price=10 each   ← mock data from contract
           ↓
      app.py: sum = 10+10+10 = 30
      app.py: return {booksPrice: 250, coursesPrice: 30}
    """

    # ── CONTRACT DEFINITION ───────────────────────────────────────────────────
    # This tells Pact what interaction to expect.
    # Nothing runs here — this is pure registration/configuration.
    #
    # .given()          → the state the provider DB must be in before this call
    # .upon_receiving() → human-readable description of this interaction
    # .with_request()   → the exact HTTP request our consumer will make
    # .will_respond_with() → the mock response Pact server will return
    #
    # EachLike({...}, minimum=3):
    #   → response is an array
    #   → every item in the array looks like the object inside
    #   → there are at least 3 items
    #
    # Like("Selenium"), Like(10):
    #   → match by TYPE only, not exact value
    #   → Like("Selenium") = any string is fine
    #   → Like(10)         = any integer is fine (real price could be 23, 66 etc.)
    # app.py get_product_prices() only does: sum(c["price"] for c in courses)
    # It reads ONLY "price" from each course object — nothing else.
    # So the contract only defines "price". Provider can add/rename/remove
    # any other field freely — this consumer's tests will not be affected.
    (
        pact.given("courses exist")
            .upon_receiving("getting all courses details")
            .with_request("GET", "/allCourseDetails")
            .will_respond_with(
                200,
                body=EachLike(
                    {
                        "price": Like(10),   # only field this consumer uses
                    },
                    minimum=3               # at least 3 items in the array
                )
            )
    )

    # ── MOCK SERVER START ─────────────────────────────────────────────────────
    # 'with pact:' does three things:
    #   ON ENTER → starts Pact HTTP mock server on port 9999
    #              mock server is preloaded with the interaction defined above
    #              it knows: GET /allCourseDetails → respond with mock data
    #   DURING   → mock server is live and waiting for requests
    #   ON EXIT  → stops mock server
    #              verifies the registered interaction was actually called
    #              writes pacts/BooksCatalogue-CoursesCatalogue.json
    with pact:

        # ── BASE_URL REDIRECT ─────────────────────────────────────────────────
        # 'with patch(...)' temporarily replaces BASE_URL inside courses_client.py
        #
        # Before patch:  BASE_URL = "http://localhost:8181"  (real provider)
        # During patch:  BASE_URL = "http://localhost:9999"  (Pact mock server)
        # After patch:   BASE_URL = "http://localhost:8181"  (restored automatically)
        #
        # pact.uri = "http://localhost:9999" (the running mock server address)
        #
        # Effect: when app.py calls get_all_courses() with no arguments,
        # courses_client does: url = None or BASE_URL = "http://localhost:9999"
        # So the HTTP call goes to mock server instead of real provider.
        # app.py never knows — it just calls get_all_courses() as normal.
        with patch("books_service.courses_client.BASE_URL", pact.uri):

            # ── CALL REAL CONSUMER ENDPOINT ───────────────────────────────────
            # client.get("/getProductPrices") calls app.py's real endpoint.
            # app.py internally calls get_all_courses() → courses_client.py
            # courses_client.py makes HTTP call → lands on Pact mock server
            # responds with 3 items of price=10
            # app.py sums them up and returns the combined result
            response = client.get("/getProductPrices")

    # ── ASSERTIONS ────────────────────────────────────────────────────────────
    # Verify the consumer endpoint produced the correct output.
    # booksPrice = 250 (hardcoded in app.py)
    # coursesPrice = 30 (3 items × price=10 from mock)
    assert response.status_code == 200
    result = response.json()
    assert result["booksPrice"]   == 250
    assert result["coursesPrice"] == 30


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: /getProductDetails/{name} — consumer combines book + course details
# ─────────────────────────────────────────────────────────────────────────────
def test_get_product_details_course_exists():
    """
    Tests the /getProductDetails/Appium endpoint of BooksCatalogue.
    Appium book exists in books DB (seeded on startup by TestClient).
    Appium course exists in provider — mock returns price=44, category="mobile".

    Full call chain during this test:
      TestClient.get("/getProductDetails/Appium")
           ↓
      app.py: reads Appium from books.db (local DB — no mock needed here)
           ↓
      courses_client.get_course_by_name("Appium")  ← real HTTP client runs
           ↓
      requests.get("localhost:9999/getCourseByName/Appium")  ← hits mock
           ↓
      Mock server returns {price:44, category:"mobile"}
           ↓
      app.py combines: book data + price + category
      app.py returns {product:{...}, price:44, category:"mobile"}
    """

    # ── CONTRACT DEFINITION ───────────────────────────────────────────────────
    # Single course object response (not an array like Test 1).
    # app.py get_product_details() reads: course["price"] and course["category"]
    # ONLY those 2 fields go in the contract.
    # Provider also returns course_name and id — but this consumer doesn't use
    # them, so they are NOT in this contract. If provider renames course_name,
    # this consumer is unaffected. Another consumer that uses course_name
    # will catch that change via its own contract.
    (
        pact.given("Course Appium exist")
            .upon_receiving("Get the Appium course details")
            .with_request("GET", "/getCourseByName/Appium")
            .will_respond_with(
                200,
                body={
                    "price":    Like(44),       # consumer uses course["price"]
                    "category": Like("mobile"), # consumer uses course["category"]
                }
            )
    )

    # ── MOCK SERVER START + BASE_URL REDIRECT + CALL REAL ENDPOINT ───────────
    # Same pattern as Test 1:
    #   with pact         → mock server starts on port 9999
    #   with patch(...)   → BASE_URL redirected to mock server
    #   client.get(...)   → calls real app.py endpoint which hits mock internally
    with pact:
        with patch("books_service.courses_client.BASE_URL", pact.uri):
            response = client.get("/getProductDetails/Appium")

    # ── ASSERTIONS ────────────────────────────────────────────────────────────
    # Verify consumer combined book data (local DB) + course data (mock server)
    assert response.status_code == 200
    result = response.json()
    assert "product"  in result
    assert result["product"]["book_name"] == "Appium"   # from books.db (local)
    assert result["price"]    == 44                      # from Pact mock server
    assert result["category"] == "mobile"                # from Pact mock server


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: /getProductDetails/{name} — course does NOT exist in provider (404)
# ─────────────────────────────────────────────────────────────────────────────
def test_get_product_details_course_not_exist():
    """
    Tests /getProductDetails/Appium when course is missing in provider.
    Appium book still exists locally, but the provider returns 404 for the course.

    Full call chain during this test:
      TestClient.get("/getProductDetails/Appium")
           ↓
      app.py: reads Appium from books.db (local DB — found)
           ↓
      courses_client.get_course_by_name("Appium")  ← real HTTP client runs
           ↓
      requests.get("localhost:9999/getCourseByName/Appium")  ← hits mock
           ↓
      Mock server returns 404
           ↓
      courses_client: 404 detected → returns None (graceful handling)
           ↓
      app.py: course is None → returns msg instead of price/category
      app.py: returns {product:{...}, msg:"...not available..."}
    """

    # ── CONTRACT DEFINITION ───────────────────────────────────────────────────
    # 404 response has no-body — provider simply returns the status code.
    # Consumer must handle this gracefully without crashing.
    (
        pact.given("Course Appium does not exist")
            .upon_receiving("Appium course Does not exist")
            .with_request("GET", "/getCourseByName/Appium")
            .will_respond_with(404)    # no-body needed for 404
    )

    # ── MOCK SERVER START + BASE_URL REDIRECT + CALL REAL ENDPOINT ───────────
    with pact:
        with patch("books_service.courses_client.BASE_URL", pact.uri):
            response = client.get("/getProductDetails/Appium")

    # ── ASSERTIONS ────────────────────────────────────────────────────────────
    # Consumer returns book data + message when course is not found.
    # No price or category in response since the course was missing.
    assert response.status_code == 200
    result = response.json()
    assert "product"   in result                         # book data still returned
    assert result["product"]["book_name"] == "Appium"   # from books.db (local)
    assert "msg"       in result                         # friendly message shown
    assert "price"     not in result                     # no price — course missing
    assert "category"  not in result                     # no category — course missing
