# Microservice Pact Contract Testing — Python

> **Consumer-Driven Contract Testing** using [Pact](https://docs.pact.io/) + [PactFlow](https://pactflow.io) with FastAPI microservices in Python.

This project demonstrates the full Pact contract testing lifecycle — from consumer test → contract generation → publish to cloud broker → provider verification — mirroring what real SDET teams do in production environments.

---

## What This POC Demonstrates

```
┌─────────────────────────────────────────────────────────────────┐
│                    PACT CONTRACT TESTING FLOW                   │
│                                                                 │
│  ┌──────────────────┐   publishes contract   ┌───────────────┐ │
│  │  BooksCatalogue  │ ──────────────────────▶│   PactFlow    │ │
│  │   (Consumer)     │                        │ (Cloud Broker)│ │
│  │  FastAPI :8082   │                        │               │ │
│  └──────────────────┘                        └───────┬───────┘ │
│           │                                          │         │
│           │ calls at runtime                fetches  │         │
│           ▼                                contract  ▼         │
│  ┌──────────────────┐                      ┌──────────────────┐│
│  │ CoursesCatalogue │◀─────────────────────│  Provider Tests  ││
│  │   (Provider)     │   verifies against   │  (pactman verify)││
│  │  FastAPI :8181   │   real service       └──────────────────┘│
│  └──────────────────┘                                          │
└─────────────────────────────────────────────────────────────────┘
```

**Two real microservices:**
- **BooksCatalogue** (Consumer) — manages books, calls CoursesCatalogue for pricing
- **CoursesCatalogue** (Provider) — owns course data, exposes REST endpoints

**Tech Stack:**

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| Framework | FastAPI |
| Database | SQLite + SQLAlchemy |
| Pact Library | pactman 2.31.0 |
| Cloud Broker | PactFlow (https://deepintent.pactflow.io) |
| Test Runner | pytest |

---

## Project Structure

```
microservice-pact-python/
├── books_service/
│   ├── app.py              # Consumer microservice (FastAPI :8082)
│   └── courses_client.py   # HTTP client — calls CoursesCatalogue
│
├── courses_service/
│   └── app.py              # Provider microservice (FastAPI :8181)
│
├── tests/
│   ├── consumer/
│   │   ├── conftest.py             # ⭐ Auto-publishes contract to PactFlow after tests pass
│   │   └── test_pact_consumer.py  # ⭐ Defines the contract + consumer tests
│   └── provider/
│       └── test_pact_provider.py  # ⭐ Verifies provider against contract
│
├── scripts/
│   └── publish_pact.py     # Manual publish fallback (optional)
│
├── pacts/
│   └── BooksCatalogue-CoursesCatalogue-pact.json  # Generated contract
│
├── requirements.txt
└── pytest.ini
```

---

## Prerequisites

- Python 3.10+
- pip
- PactFlow account → [Sign up free](https://pactflow.io) → get your API token

---

## Setup (One-Time)

### 1. Clone the repository

```bash
git clone https://github.com/Pratyush-QA/microservice-pact-python.git
cd microservice-pact-python
```

### 2. Create virtual environment and install dependencies

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Mac/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Set your PactFlow API token

Get your token: **https://deepintent.pactflow.io → Settings → API Tokens → Read/Write Token**

```powershell
# Windows PowerShell
$env:PACT_BROKER_TOKEN = "your-token-here"

# Mac/Linux
export PACT_BROKER_TOKEN=your-token-here
```

> ⚠️ Never commit this token to git. Always use environment variables.

---

## Running the Tests — Step by Step

### Step 1: Run Consumer Tests _(auto-publishes contract to PactFlow)_

Defines what BooksCatalogue expects from CoursesCatalogue.
Generates the contract JSON locally and **automatically publishes it to PactFlow** — no separate publish command needed.

```bash
pytest tests/consumer/ -v
```

**Expected output:**
```
tests/consumer/test_pact_consumer.py::test_all_courses_price_sum             PASSED
tests/consumer/test_pact_consumer.py::test_get_product_details_course_exists PASSED
tests/consumer/test_pact_consumer.py::test_get_product_details_course_not_exist PASSED
3 passed

[PactFlow] Auto-publishing contract...
  Consumer : BooksCatalogue
  Provider : CoursesCatalogue
  Version  : 1.0.0
[PactFlow] ✅ Contract published successfully!
  View at: https://deepintent.pactflow.io/pacts/provider/CoursesCatalogue/consumer/BooksCatalogue/latest
```

**What happens internally:**
```
TestClient.get("/getProductPrices")
    → app.py: get_product_prices()           ← real consumer code runs
    → courses_client.get_all_courses()       ← real HTTP client runs
    → requests.get("localhost:9999/...")     ← hits Pact MOCK server
    → mock returns 3 items × price=10
    → app.py: sum = 30
    → assert coursesPrice == 30  ✅

After all tests pass → conftest.py pytest_sessionfinish hook fires
    → contract JSON published to PactFlow automatically ✅
```

Contract JSON written to: `pacts/BooksCatalogue-CoursesCatalogue-pact.json`

> 💡 **How auto-publish works:** `tests/consumer/conftest.py` uses pytest's `pytest_sessionfinish` hook.
> It runs after every test session and publishes only when all tests pass and `PACT_BROKER_TOKEN` is set.
> To publish manually (optional fallback): `python scripts/publish_pact.py`

View the contract at: **https://deepintent.pactflow.io**

---

### Step 2: Run Provider Tests

Fetches the contract from PactFlow and verifies the REAL CoursesCatalogue service satisfies it.

```bash
pytest tests/provider/ -v -s
```

**Expected output:**
```
tests/provider/test_pact_provider.py::test_pact_provider
  Consumer: BooksCatalogue
  Setting up provider state 'courses exist'               → PASSED ✅
  Setting up provider state 'Course Appium exist'         → PASSED ✅
  Setting up provider state 'Course Appium does not exist' → PASSED ✅
1 passed
```

**What happens internally:**
```
pactman fetches contract from PactFlow
    → For each interaction:
        POST http://127.0.0.1:8182/_pact/provider_states
            → state handler sets up DB (insert/delete records)
        GET  http://127.0.0.1:8181/allCourseDetails
            → real CoursesCatalogue service responds
        pactman compares real response vs contract
            → PASS ✅ (response matches type/structure defined by consumer)
```

---

### Step 3: (Optional) Run Both Services Manually

You can also run both services and hit the endpoints in a browser:

```bash
# Terminal 1 — Provider (CoursesCatalogue)
uvicorn courses_service.app:app --port 8181 --reload

# Terminal 2 — Consumer (BooksCatalogue)
uvicorn books_service.app:app --port 8082 --reload
```

**Available endpoints:**

| Service | Endpoint | Description |
|---|---|---|
| CoursesCatalogue | `GET /allCourseDetails` | All courses |
| CoursesCatalogue | `GET /getCourseByName/{name}` | Single course |
| BooksCatalogue | `GET /getProductPrices` | Books + courses total price |
| BooksCatalogue | `GET /getProductDetails/{name}` | Book + course combined |
| BooksCatalogue | `POST /addBook` | Add a new book |
| BooksCatalogue | `GET /getBooks/{id}` | Get book by ID |

---

## Key Concepts — What to Understand

### Consumer Test Structure

```python
# 1. Register the contract interaction (nothing runs yet)
pact.given("courses exist")                    # provider DB state needed
    .upon_receiving("getting all courses")     # human-readable description
    .with_request("GET", "/allCourseDetails")  # exact request consumer will make
    .will_respond_with(200, body=EachLike({    # what consumer expects back
        "course_name": Like("Selenium"),       # any string
        "price":       Like(10),               # any integer
    }, minimum=3))

# 2. Start mock server + redirect BASE_URL + call real consumer endpoint
with pact:                                     # starts mock server on port 9999
    with patch("books_service.courses_client.BASE_URL", pact.uri):
        response = client.get("/getProductPrices")  # calls REAL app.py

# 3. Assert consumer behaviour
assert response.json()["coursesPrice"] == 30   # 3 items × price=10
```

### Matchers

| Matcher | Meaning | Example |
|---|---|---|
| `Like("Selenium")` | Any value of same **type** | Any string |
| `Like(10)` | Any value of same **type** | Any integer |
| `EachLike({...}, minimum=3)` | Array with at least 3 items, each matching the shape | `[{...}, {...}, {...}]` |

### Provider State Flow

```
Consumer defines:   pact.given("Course Appium does not exist")
                         ↓
Provider implements: def state_appium_course_not_exist():
                         db.query(CourseModel).filter(...).delete()
                         ↓
Before verification: pactman POSTs {"state": "Course Appium does not exist"}
                     → state handler deletes Appium from DB
                         ↓
Verification:        GET /getCourseByName/Appium → real 404 → matches contract ✅
```

---

## Troubleshooting

| Error | Fix |
|---|---|
| `PACT_BROKER_TOKEN not set` | Set env var: `$env:PACT_BROKER_TOKEN = "..."` |
| `Pact file not found` | Run consumer tests first: `pytest tests/consumer/ -v` |
| `Port 8181 already in use` | Existing server detected and reused automatically |
| `FileNotFoundError pactman-verify` | Not applicable — we use pactman Python API directly |
| `[PactFlow] Skipping auto-publish — PACT_BROKER_TOKEN not set` | Set token before running: `$env:PACT_BROKER_TOKEN = "..."` |
| Auto-publish not triggering | Check if tests are passing — publish only fires on exitstatus=0 |
| Want to publish without running tests | Run manually: `python scripts/publish_pact.py` |

---

## The Complete Pact Lifecycle (Real World)

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   CONSUMER TEAM │     │    PACTFLOW       │     │  PROVIDER TEAM   │
│                 │     │  (Cloud Broker)   │     │                  │
│ 1. Write        │     │                  │     │ 4. Run provider  │
│    consumer     │     │                  │     │    tests in CI   │
│    tests        │     │                  │     │                  │
│                 │     │                  │     │                  │
│ 2. Tests pass → │────▶│ 3. Contract      │────▶│ 5. pactman       │
│    contract     │     │    stored with   │     │    fetches ALL   │
│    published    │     │    version tag   │     │    consumer      │
│                 │     │                  │     │    contracts     │
│                 │     │                  │     │                  │
│                 │◀────│ 6. Verification  │◀────│ 6. Verifies real │
│                 │     │    results       │     │    service       │
│                 │     │    published     │     │                  │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

---

## Interview Reference — Key Talking Points

- **Contract testing vs integration testing**: Contract tests are fast, isolated, no real network calls on consumer side. Integration tests need both services running.
- **Consumer-driven**: The consumer defines what it needs. Provider only needs to satisfy those specific fields/endpoints — not a full API spec.
- **`Like()` vs exact match**: `Like("Selenium")` means any string — real provider can return "Appium" and it passes. Exact match would fail.
- **Provider states**: The mechanism to set up DB preconditions before each interaction — equivalent to `@BeforeEach` with specific data setup.
- **Pact Broker**: Central storage for contracts. Decouples consumer and provider CI pipelines. Enables "can I deploy?" checks.

---

*Built as part of SDET learning — Python equivalent of the Java/Spring Boot Pact JVM course.*
