# CLAUDE.md — Project Memory File
> This file restores full context for Claude when the conversation history is exhausted.
> Paste this file content at the start of a new session to resume exactly where we left off.

---

## Project Identity

- **Repo:** https://github.com/Pratyush-QA/microservice-pact-python
- **Local path:** `D:\Study\Mirror\CompleteMaterial-SDET\1.PythonSDET\3.SDET-Syllabus\5.MicroService Testing\microservice-pact-python`
- **Purpose:** SDET learning POC — Consumer-Driven Contract Testing with FastAPI + PactFlow
- **Python:** 3.13 (system), venv at `.venv/`
- **Activate venv:** `.venv\Scripts\Activate.ps1`

---

## Architecture

```
BooksCatalogue (Consumer)     CoursesCatalogue (Provider)
  books_service/app.py   ──►    courses_service/app.py
  FastAPI port 8082              FastAPI port 8181
  SQLite: books.db               SQLite: courses.db
```

**Two real FastAPI microservices. SQLite auto-created on startup — no DB setup needed.**

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Language | Python 3.13 | — |
| Framework | FastAPI | async, auto Swagger UI |
| Database | SQLite + SQLAlchemy | zero setup, auto-created |
| Pact Library | **pactman 2.31.0** | pure Python, no Ruby needed |
| Cloud Broker | PactFlow — https://deepintent.pactflow.io | central contract storage |
| Test Runner | pytest | — |

### Why pactman and NOT pact-python?
- `pact-python` requires Ruby + pact-mock-service binary installed separately
- `pactman` is pure Python — no external binary needed
- Tradeoff: `pactman` has no built-in `publish_to_broker` in `has_pact_with()` (so we built conftest.py for auto-publish)

---

## Project Structure

```
microservice-pact-python/
├── books_service/
│   ├── app.py                  # Consumer FastAPI app (:8082)
│   └── courses_client.py       # HTTP client — only place that calls provider
│
├── courses_service/
│   └── app.py                  # Provider FastAPI app (:8181)
│
├── tests/
│   ├── consumer/
│   │   ├── conftest.py         # pytest_sessionfinish hook — auto-publishes contract
│   │   └── test_pact_consumer.py  # Defines contract interactions + consumer tests
│   └── provider/
│       └── test_pact_provider.py  # Fetches from PactFlow + verifies real service
│
├── scripts/
│   └── publish_pact.py         # Manual publish fallback (optional)
│
├── pacts/
│   └── BooksCatalogue-CoursesCatalogue-pact.json  # Generated contract
│
├── Python_Pact_Setup_Guide.docx  # Step-by-step Word doc for setup
├── requirements.txt
├── pytest.ini
└── CLAUDE.md                   # This file
```

---

## Key Design Decisions Made

### 1. courses_client.py is the seam for Pact
`app.py` never imports requests. All HTTP calls to the provider go through `courses_client.py`.
`BASE_URL` in `courses_client.py` is patched in tests to redirect to Pact mock server.

```python
# courses_client.py
BASE_URL = "http://localhost:8181"   # real provider

def get_all_courses(base_url=None):
    url = base_url or BASE_URL       # patch replaces BASE_URL value
    return requests.get(f"{url}/allCourseDetails").json()
```

```python
# In consumer test — patch redirects to mock server
with patch("books_service.courses_client.BASE_URL", pact.uri):
    response = client.get("/getProductPrices")
```

### 2. Provider tests use Python API directly (not CLI)
`pactman-verify` CLI does NOT exist as a `.exe` on Windows.
We use `BrokerPacts` + `interaction.verify()` from Python API directly.

```python
from pactman.verifier.broker_pact import BrokerPacts, PactBrokerConfig
from pactman.verifier.result import CaptureResult

broker_config = PactBrokerConfig(url=PACT_BROKER_URL, token=PACT_BROKER_TOKEN)
pacts = BrokerPacts(PROVIDER_NAME, broker_config, result_factory).consumers()

for pact in pacts:
    for interaction in pact.interactions:
        interaction.verify(provider_server, f"{state_server}/_pact/provider_states")
```

### 3. State server on port 8182
pactman POSTs to a state server before each interaction to set up DB.
We run a second FastAPI app on port 8182 as the state server.

### 4. Provider server on port 8181
Real CoursesCatalogue service runs in a background thread during provider tests.
`_port_in_use()` helper detects if service is already running — reuses it instead of starting again.

### 5. Auto-publish via conftest.py
pactman has no built-in broker publish in `has_pact_with()`.
We use `pytest_sessionfinish` hook in `tests/consumer/conftest.py` to auto-publish after consumer tests pass.
Manual fallback: `python scripts/publish_pact.py`

---

## PactFlow Configuration

- **URL:** `https://deepintent.pactflow.io`
- **Token:** Read from env var `PACT_BROKER_TOKEN` — NEVER hardcoded
- **Set token:** `$env:PACT_BROKER_TOKEN = "your-read-write-token-here"`
- **Get token:** https://deepintent.pactflow.io → Settings → API Tokens → Read/Write Token
- **Consumer version:** `CONSUMER_VERSION` env var (default `"1.0.0"`)
- **Publish API:** `PUT /pacts/provider/{provider}/consumer/{consumer}/version/{version}`

---

## Bugs Debugged and Fixed

### Bug 1: pactman-verify not found (WinError 2)
**Problem:** Original code used `subprocess` to call `pactman-verify` — binary doesn't exist on Windows.
**Fix:** Eliminated subprocess entirely. Use Python API directly via `BrokerPacts` + `interaction.verify()`.

### Bug 2: Port 8181 already in use (OSError 10048)
**Problem:** Running provider tests twice caused port conflict.
**Fix:** Added `_port_in_use()` helper. Fixture checks port before starting — reuses existing server if occupied.

```python
def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0
```

### Bug 3: body[0].id size 1 is smaller than minimum size 3
**Problem:** pactman EachLike bug — path matching gives `$.body.id` weight 0 for actual path `[', 'body', 0, 'id']` because integer index `0` breaks matching. Falls back to `$.body` rule (min=3) and wrongly applies it as STRING LENGTH constraint on `id` field.
**Fix:** Changed all DB IDs to 3+ character strings.

```python
# Wrong (triggers bug):
CourseModel(id="2", ...)   # length 1 < min 3 → fails

# Fixed:
CourseModel(id="c02", ...)  # length 3 → passes
```

IDs used: `"c02"`, `"c03"`, `"c12"` in both `courses_service/app.py` seed data AND state handlers.

### Bug 4: State handler using "insert if empty" pattern
**Problem:** Provider DB still had old short IDs from server startup seed. State handler only inserted if empty — never updated.
**Fix:** `state_courses_exist()` now always does DELETE then INSERT.

```python
def state_courses_exist():
    db = SessionLocal()
    db.query(CourseModel).delete()   # always clear first
    db.add_all([
        CourseModel(course_name="Microservices testing", id="c02", price=23, category="api"),
        CourseModel(course_name="Selenium",              id="c03", price=66, category="web"),
        CourseModel(course_name="Appium",                id="c12", price=13, category="mobile"),
    ])
    db.commit()
    db.close()
```

---

## Consumer Test Pattern

```python
# 1. Define interaction (nothing runs yet)
pact.given("courses exist")
    .upon_receiving("getting all courses details")
    .with_request("GET", "/allCourseDetails")
    .will_respond_with(200, body=EachLike({
        "course_name": Like("Selenium"),   # any string
        "id":          Like("3"),          # any string
        "price":       Like(10),           # any integer
        "category":    Like("web"),        # any string
    }, minimum=3))

# 2. Start mock server + redirect BASE_URL + call real consumer endpoint
with pact:                                          # mock server starts on port 9999
    with patch("books_service.courses_client.BASE_URL", pact.uri):
        response = client.get("/getProductPrices")  # real app.py runs

# 3. Assert consumer behaviour
assert response.json()["coursesPrice"] == 30        # 3 items × price=10
```

### How EachLike works
- `EachLike({...}, minimum=3)` → mock returns array of 3 copies using example values
- `Like(10)` → mock uses `10` as example value; contract checks TYPE only (any integer passes)
- Mock always returns exact example values → predictable assertions

---

## Provider Test Pattern

```python
# State handlers — keyed to "given" strings in consumer contract
STATE_HANDLERS = {
    "courses exist":                state_courses_exist,
    "Course Appium exist":          state_appium_course_exist,
    "Course Appium does not exist": state_appium_course_not_exist,
}

# State server — FastAPI on port 8182
@state_app.post("/_pact/provider_states")
async def provider_states(request):
    body = await request.json()
    handler = STATE_HANDLERS.get(body.get("state", ""))
    if handler:
        handler()
    return {"result": state}

# Verification test
def test_pact_provider(provider_server, state_server):
    broker_config = PactBrokerConfig(url=PACT_BROKER_URL, token=PACT_BROKER_TOKEN)
    result_factory = partial(CaptureResult, level=logging.INFO)
    pacts = BrokerPacts(PROVIDER_NAME, broker_config, result_factory).consumers()

    success = True
    for pact in pacts:
        for interaction in pact.interactions:
            interaction.verify(provider_server, f"{state_server}/_pact/provider_states")
            success = interaction.result.success and success

    assert success, "Pact verification FAILED"
```

---

## Run Commands (in order)

```powershell
# 1. Activate venv
.venv\Scripts\Activate.ps1

# 2. Set PactFlow token
$env:PACT_BROKER_TOKEN = "your-token-here"

# 3. Run consumer tests (auto-publishes contract to PactFlow on pass)
pytest tests/consumer/ -v

# 4. Run provider tests (fetches from PactFlow, verifies real service)
pytest tests/provider/ -v -s

# Optional — start services manually
uvicorn courses_service.app:app --port 8181 --reload   # Terminal 1
uvicorn books_service.app:app --port 8082 --reload     # Terminal 2

# Optional — manual publish without running tests
python scripts/publish_pact.py
```

---

## Auto-Publish Flow (conftest.py)

```
pytest tests/consumer/ -v
    → all 3 tests pass
    → conftest.py: pytest_sessionfinish fires
        → exitstatus == 0?  ✅
        → PACT_BROKER_TOKEN set?  ✅
        → pact file exists?  ✅
        → PUT https://deepintent.pactflow.io/pacts/provider/CoursesCatalogue/consumer/BooksCatalogue/version/1.0.0
        → [PactFlow] ✅ Contract published successfully!
```

Skips publish if: tests failed / token not set / pact file missing.

---

## Contracts Defined (3 Interactions)

| Given | Request | Expected Response |
|---|---|---|
| `courses exist` | `GET /allCourseDetails` | 200, array ≥3 items, each with course_name/id/price/category |
| `Course Appium exist` | `GET /getCourseByName/Appium` | 200, single object with course_name/id/price/category |
| `Course Appium does not exist` | `GET /getCourseByName/Appium` | 404 |

---

## Endpoints

| Service | Port | Endpoint | Description |
|---|---|---|---|
| CoursesCatalogue | 8181 | `GET /allCourseDetails` | All courses |
| CoursesCatalogue | 8181 | `GET /getCourseByName/{name}` | Single course (200 or 404) |
| BooksCatalogue | 8082 | `GET /getProductPrices` | Books price + courses price sum |
| BooksCatalogue | 8082 | `GET /getProductDetails/{name}` | Book + course combined |
| BooksCatalogue | 8082 | `POST /addBook` | Add new book |
| BooksCatalogue | 8082 | `GET /getBooks/{id}` | Get book by ID |

---

## What Pact Catches (Bug Scenarios)

1. Field renamed (`price` → `course_price`)
2. Field removed entirely
3. Data type changed (int → string)
4. HTTP status code changed (200 → 201)
5. 404 behaviour changed (404 → 200 with empty body)
6. Endpoint URL renamed (`/allCourseDetails` → `/courses`)
7. HTTP method changed (GET → POST)
8. Array wrapped in object (`[...]` → `{"data": [...]}`)
9. Array returned with fewer items than minimum (< 3)
10. Required request header changed
11. Query parameter renamed
12. Flat structure changed to nested
13. Null returned instead of typed value

**Does NOT catch:** wrong business values, wrong calculations, performance issues, security bugs.

---

## Files Generated by This Project (not in repo / gitignored)

- `books.db` — SQLite for BooksCatalogue (auto-created)
- `courses.db` — SQLite for CoursesCatalogue (auto-created)
- `.venv/` — virtual environment

## Files committed to repo

- `pacts/BooksCatalogue-CoursesCatalogue-pact.json` — kept for GitHub visibility
- `Python_Pact_Setup_Guide.docx` — Word setup guide

---

## Git History (key commits)

```
9c87fbe  Update README and Setup Guide for auto-publish feature
deb42ab  Add auto-publish contract to PactFlow after consumer tests pass
015d232  Remove outdated HOW_TO_RUN.md
d682e5e  Added Guide Doc for Setup
592e1ed  Add microservice Pact contract testing POC (Python)
```

---

## Interview Talking Points

- **Contract testing vs integration testing:** Contract = fast, isolated, no real network on consumer side. Integration = both services running, slow, flaky.
- **Consumer-driven:** Consumer defines what it needs. Provider only needs to satisfy those specific fields — not full API spec.
- **`Like()` vs exact match:** `Like("Selenium")` = any string. Real provider can return "Appium" and it passes.
- **Provider states:** DB setup mechanism before each interaction — equivalent to `@BeforeEach` with specific data.
- **Pact Broker:** Central contract storage. Decouples CI pipelines. Enables "can I deploy?" check.
- **`patch` in consumer tests:** Only active during pytest. Never runs in production. `app.py` has zero knowledge of tests.
- **Two `get_all_courses()` methods:** One in `courses_client.py` (HTTP caller), one in `courses_service/app.py` (HTTP handler). Same name, opposite roles, connected only via HTTP network.
