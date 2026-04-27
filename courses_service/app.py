"""
CoursesCatalogue — Provider Microservice
=========================================
This is the PROVIDER service. It owns the course data.
The consumer (BooksCatalogue) calls this service to get course information.

Endpoints:
  GET /allCourseDetails → return list of all courses
  GET /getCourseByName/{name} → returns a single course or 404 if not found

Database:
  SQLite (file: courses.db) — auto-created on first run, no setup needed.
  Data is seeded on startup to match the course material data.

Run this service:
  uvicorn courses_service.app:app --port 8181 --reload
"""

from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.orm import declarative_base, sessionmaker

app = FastAPI(title="CoursesCatalogue")

# ── Database setup ─────────────────────────────────────────────────────────────
# SQLite creates the .db file automatically — no installation needed
DATABASE_URL = "sqlite:///./courses.db"
engine       = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base         = declarative_base()


class CourseModel(Base):
    """Represents one course record in the database."""
    __tablename__ = "courses"
    course_name = Column(String, primary_key=True, index=True)
    id          = Column(String)
    price       = Column(Integer)
    category    = Column(String)


# Create the table if it doesn't exist yet
Base.metadata.create_all(bind=engine)


def get_db():
    """Provides a database session for each request, closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Seed data on startup ───────────────────────────────────────────────────────
# Inserts initial course records when the DB is empty.
# These match the course material data exactly.
@app.on_event("startup")
def seed():
    db = SessionLocal()
    if db.query(CourseModel).count() == 0:
        db.add_all([
            CourseModel(course_name="Microservices testing", id="c02", price=23, category="api"),
            CourseModel(course_name="Selenium",              id="c03", price=66, category="web"),
            CourseModel(course_name="Appium",                id="c12", price=13, category="mobile"),
        ])
        db.commit()
    db.close()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/allCourseDetails")
def get_all_courses(db=Depends(get_db)):
    """
    Returns all courses from the database.
    Response: [ {course_name, id, price, category}, ... ]
    """
    courses = db.query(CourseModel).all()
    return [
        {"course_name": c.course_name, "id": c.id, "price": c.price, "category": c.category}
        for c in courses
    ]


@app.get("/getCourseByName/{name}")
def get_course_by_name(name: str, db=Depends(get_db)):
    """
    Returns a single course by name.
    Response: {course_name, id, price, category}
    Returns 404 if the course is not found.
    """
    course = db.query(CourseModel).filter(CourseModel.course_name == name).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return {
        "course_name": course.course_name,
        "id":          course.id,
        "price":       course.price,
        "category":    course.category,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8181)
