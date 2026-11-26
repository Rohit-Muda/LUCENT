from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from backend.app.models import Base


def test_domain_metadata_contains_expected_tables() -> None:
    assert set(Base.metadata.tables) == {
        "lectures",
        "transcripts",
        "notes",
        "concept_explanations",
        "revision_points",
        "quiz_questions",
        "quiz_options",
        "processing_jobs",
        "generation_chunks",
        "lecture_pdfs",
    }


def test_domain_tables_compile_for_mysql() -> None:
    for table in Base.metadata.sorted_tables:
        str(CreateTable(table).compile(dialect=mysql.dialect()))
