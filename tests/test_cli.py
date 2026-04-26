from __future__ import annotations

import json

from moodle_sync.cli import main
from moodle_sync.embeddings import HashingEmbedder
from moodle_sync.indexer import index_courses
from tests.conftest import make_pdf


def test_search_json_output_shape(tmp_path, capsys):
    courses = tmp_path / "courses"
    db = tmp_path / "search.sqlite3"
    pdf = courses / "COMP1003" / "Week 01" / "testing.pdf"
    pdf.parent.mkdir(parents=True)
    make_pdf(pdf, ["Pytest fixtures make regression testing reliable."])
    index_courses(courses, db, HashingEmbedder())

    exit_code = main(["--courses-dir", str(courses), "--db", str(db), "search", "regression testing", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["query"] == "regression testing"
    assert payload["results"][0]["citation"] == "COMP1003 · Week 01 · testing.pdf · p. 1"
    assert "scores" in payload["results"][0]
