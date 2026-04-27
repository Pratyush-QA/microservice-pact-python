# Microservice Pact Testing — Python Version

## Architecture (mirrors the Java course)

```
BooksCatalogue (Consumer)          CoursesCatalogue (Provider)
  books_service/app.py      ──►      courses_service/app.py
  port 8080                           port 8181

  Endpoints:                          Endpoints:
    POST /addBook                       GET /allCourseDetails
    GET  /getBooks/{id}                 GET /getCourseByName/{name}
    GET  /getProductPrices  ──calls──►
    GET  /getProductDetails/{name} ──►
```

## Java → Python Tool Mapping

| Java                              | Python                        |
|-----------------------------------|-------------------------------|
| Spring Boot                       | FastAPI + Uvicorn             |
| MySQL + JPA/Hibernate             | SQLite + SQLAlchemy           |
| JUnit 5                           | pytest                        |
| pact-jvm-consumer-junit5          | pact-python                   |
| pact-jvm-provider-junit5          | pact-python Verifier          |
| TestRestTemplate                  | requests library              |
| @Pact(consumer="BooksCatalogue")  | pact.given(...).upon_receiving(...) |
| PactDslJsonArray.arrayMinLike(3)  | EachLike({...}, minimum=3)    |
| PactDslJsonBody().integerType()   | Like(44)                      |
| @PactFolder("pacts")              | verifier.verify_pacts(file)   |
| @PactBroker(url=..., token=...)   | verifier.verify_pacts(broker_url=..., broker_token=...) |
| @State("courses exist", SETUP)    | def setup_courses_exist(db)   |

## Setup

```bash
cd microservice-pact-python
pip install -r requirements.txt
```

## Step 1 — Run Consumer Tests (generates the Pact contract file)

```bash
pytest tests/consumer/ -v
```

This:
1. Starts a Pact mock server on port 9999
2. Runs the consumer code against the mock (not the real Courses service)
3. Generates: `pacts/BooksCatalogue-CoursesCatalogue.json`

The generated JSON is the **contract** — BooksCatalogue's expectations.

## Step 2 — Run Provider Tests (verifies the contract)

```bash
pytest tests/provider/ -v
```

This:
1. Starts the REAL Courses service (FastAPI on port 8181)
2. Sets up DB state for each interaction (state handlers)
3. Pact Verifier replays every interaction from the pact JSON
4. Checks the real responses match the contract

## Step 3 — Run both services manually (optional)

```bash
# Terminal 1 — Provider (Courses service)
python courses_service/app.py

# Terminal 2 — Consumer (Books service)
python books_service/app.py

# Test live
curl http://localhost:8181/allCourseDetails
curl http://localhost:8080/getProductPrices
```

## PactFlow (cloud broker) — optional

In Java, the course uses:
```java
@PactBroker(url="https://rahulshettyacademy.pactflow.io/",
            authentication=@PactBrokerAuth(token="..."))
```

Python equivalent in provider test:
```python
verifier.verify_pacts(
    broker_url="https://rahulshettyacademy.pactflow.io/",
    broker_token="your-token",
)
```

And in consumer test, add to pact setup:
```python
pact = Consumer("BooksCatalogue").has_pact_with(
    Provider("CoursesCatalogue"),
    broker_base_url="https://rahulshettyacademy.pactflow.io/",
    broker_token="your-token",
    publish_to_broker=True,
    version="1.0.0",
)
```
