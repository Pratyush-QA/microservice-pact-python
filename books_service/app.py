"""
BooksCatalogue — Consumer Microservice
========================================
This is the CONSUMER service. It manages book data and calls the
CoursesCatalogue service to fetch course pricing information.

Endpoints:
  POST /addBook → add a new book to the database
  GET /getBooks/{id} → get a book by its ID
  GET /getProductPrices → total books price + total courses price (calls Courses service)
  GET /getProductDetails/{name} → book details combined with course price and category

Database:
  SQLite (file: books.db) — auto-created on first run, no setup needed.
  Data is seeded on startup.

Run this service:
  uvicorn books_service.app:app --port 8082 --reload
"""

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.orm import declarative_base, sessionmaker

# Import the HTTP client that talks to the Courses service.
# Try package-level import first (used when running from project root via pytest).
# Fall back to direct import (used when running the file directly).
try:
    from books_service.courses_client import get_all_courses, get_course_by_name
except ImportError:
    from courses_client import get_all_courses, get_course_by_name

app = FastAPI(title="BooksCatalogue")

# ── Database setup ─────────────────────────────────────────────────────────────
# SQLite creates the .db file automatically — no installation needed
DATABASE_URL     = "sqlite:///./books.db"
engine           = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal     = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base             = declarative_base()
# Provider URL is configured inside courses_client.py — not here


class BookModel(Base):
    """Represents one book record in the database."""
    __tablename__ = "books"
    id        = Column(String, primary_key=True)
    book_name = Column(String)
    isbn      = Column(String)
    aisle     = Column(Integer)
    author    = Column(String)


# Create the table if it doesn't exist yet
Base.metadata.create_all(bind=engine)


# ── Seed data on startup ───────────────────────────────────────────────────────
# Inserts initial book records when the DB is empty.
@app.on_event("startup")
def seed_books():
    db = SessionLocal()
    if db.query(BookModel).count() == 0:
        db.add_all([
            BookModel(id="hrtge43", book_name="Microservices", isbn="hrtge", aisle=43, author="Shetty"),
            BookModel(id="khuys21", book_name="Selenium",      isbn="khuys", aisle=21, author="Shetty"),
            BookModel(id="ttefs36", book_name="Appium",        isbn="ttefs", aisle=36, author="Shetty"),
        ])
        db.commit()
    db.close()


# ── Request model ──────────────────────────────────────────────────────────────
class BookRequest(BaseModel):
    book_name: str
    isbn: str
    aisle: int
    author: str


# ── Helpers ────────────────────────────────────────────────────────────────────
def build_id(isbn: str, aisle: int) -> str:
    """Generates a unique book ID by combining isbn and aisle number."""
    return isbn + str(aisle)


def get_db():
    """Provides a database session for each request, closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/addBook", status_code=201)
def add_book(book: BookRequest, db=Depends(get_db)):
    """
    Adds a new book to the database.
    The book ID is auto-generated from isbn + aisle.
    Returns a message indicating success or if the book already exists.
    """
    book_id  = build_id(book.isbn, book.aisle)
    existing = db.query(BookModel).filter(BookModel.id == book_id).first()
    if existing:
        return {"msg": "Book already exist", "id": book_id}
    db_book = BookModel(id=book_id, book_name=book.book_name,
                        isbn=book.isbn, aisle=book.aisle, author=book.author)
    db.add(db_book)
    db.commit()
    return {"msg": "Success Book is Added", "id": book_id}


@app.get("/getBooks/{id}")
def get_book_by_id(id: str, db=Depends(get_db)):
    """
    Fetches a single book by its ID.
    Returns 404 if not found.
    """
    book = db.query(BookModel).filter(BookModel.id == id).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return {
        "id":        book.id,
        "book_name": book.book_name,
        "isbn":      book.isbn,
        "aisle":     book.aisle,
        "author":    book.author,
    }


@app.get("/getProductPrices")
def get_product_prices():
    """
    Combines the fixed books total price with the sum of all course prices.
    Internally calls the Courses service — URL is configured in courses_client.py.
    Response: {booksPrice, coursesPrice}
    """
    books_price   = 250
    courses       = get_all_courses()          # uses BASE_URL from courses_client.py
    courses_price = sum(c["price"] for c in courses)
    return {"booksPrice": books_price, "coursesPrice": courses_price}


@app.get("/getProductDetails/{name}")
def get_product_details(name: str, db=Depends(get_db)):
    """
    Combines local book data with course pricing from the Courses service.
    If the Courses service returns 404 (course not found), a message is shown instead.
    Response: {product, price, category} or {product, msg}
    """
    book = db.query(BookModel).filter(BookModel.book_name == name).first()
    if not book:
        raise HTTPException(status_code=404, detail="Book not found locally")

    product = {
        "book_name": book.book_name,
        "id":        book.id,
        "isbn":      book.isbn,
        "aisle":     book.aisle,
        "author":    book.author,
    }

    course = get_course_by_name(name)          # uses BASE_URL from courses_client.py
    if course is None:
        return {"product": product, "msg": f"{name}Category and price details are not available at this time"}

    return {"product": product, "price": course["price"], "category": course["category"]}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
