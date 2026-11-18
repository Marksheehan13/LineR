import threading
from datetime import date
from decimal import Decimal as D

import pytest

from liner.data_access.audit_log import SqliteAuditLog
from liner.data_access.document_repository import SqliteDocumentRepository
from liner.data_access.image_store import LocalImageStore
from liner.data_access.model_store import LocalModelStore
from liner.database.sqlite_db import Database
from liner.models import BandRow, Correction, Document, Field, Line, Prediction


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


@pytest.fixture
def repo(db):
    return SqliteDocumentRepository(db)


def sample(user="demo") -> Document:
    return Document(
        user_id=user, status="draft", image_ref="a" * 32 + ".png",
        supplier=Field("Acme", 0.9, None, "ocr"), date=Field(date(2026, 11, 3), 0.8, None, "ocr"),
        total=Field(D("22.30"), 0.99, None, "ocr"),
        lines=[Line("Paper", D("12.30"), None, D("23"), "suggested", False, Prediction(D("23"), 0.9, "why"), 0.9)],
        printed_vat={"23": D("2.30")}, original={"supplier": "Acme"},
        rows=[BandRow(date(2026, 11, 3), "Acme", "Paper", D("10.00"), D("23"), D("2.30"), D("12.30"), 1)],
        ocr_info={"words": 12})


def test_a_saved_document_comes_back_unchanged(repo):
    doc = sample()
    doc_id = repo.save(doc)
    got = repo.get(doc_id, "demo")
    assert got == doc and got.id == doc_id
    assert isinstance(got.total.value, D) and got.date.value == date(2026, 11, 3)


def test_update_in_place_and_list_filters_by_status(repo):
    doc = sample(); repo.save(doc)
    doc.status, doc.number = "confirmed", 1
    repo.save(doc)
    repo.save(sample())
    assert [d.status for d in repo.list("demo")] == ["confirmed", "draft"]
    assert [d.id for d in repo.list("demo", "confirmed")] == [doc.id]


def test_one_user_never_sees_or_overwrites_another_users_document(repo):   # risk R8
    doc = sample("alice"); repo.save(doc)
    assert repo.get(doc.id, "bob") is None
    assert repo.list("bob") == []
    doc.user_id = "bob"
    with pytest.raises(KeyError):
        repo.save(doc)
    assert repo.get(doc.id, "alice").user_id == "alice"


def test_unknown_id_returns_none(repo):
    assert repo.get("nope", "demo") is None


def test_counters_are_sequential_per_user(repo):
    assert [repo.next_counter("a") for _ in range(3)] == [1, 2, 3]
    assert repo.next_counter("b") == 1


def test_counter_hands_out_unique_numbers_under_concurrency(repo):
    seen, lock = [], threading.Lock()

    def work():
        for _ in range(10):
            n = repo.next_counter("a")
            with lock:
                seen.append(n)

    threads = [threading.Thread(target=work) for _ in range(6)]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert sorted(seen) == list(range(1, 61))


# ---- image store -----------------------------------------------------------------------------------


def test_image_store_round_trip_and_delete(tmp_path):
    s = LocalImageStore(tmp_path)
    ref = s.save("demo", b"bytes", "png")
    assert s.load(ref) == b"bytes"
    s.delete(ref); s.delete(ref)             # deleting twice is fine
    with pytest.raises(FileNotFoundError):
        s.load(ref)


@pytest.mark.parametrize("ref", ["../secret.png", "/etc/passwd", "abc.png", "a" * 32 + ".exe", "a" * 32 + "/../x.png"])
def test_image_store_refuses_paths_that_are_not_its_own_refs(tmp_path, ref):
    with pytest.raises(ValueError):
        LocalImageStore(tmp_path).load(ref)


def test_image_store_refuses_other_types(tmp_path):
    with pytest.raises(ValueError):
        LocalImageStore(tmp_path).save("demo", b"x", "exe")


# ---- model store -----------------------------------------------------------------------------------


def test_model_store_versions(tmp_path):
    s = LocalModelStore(tmp_path)
    assert s.load_latest("band-classifier") is None
    assert s.save("band-classifier", {"a": 1}) == 1 and s.save("band-classifier", {"a": 2}) == 2
    assert s.load_latest("band-classifier") == (2, {"a": 2})
    assert s.load_latest("other") is None
    with pytest.raises(ValueError):
        s.save("../evil", {})


# ---- audit log -------------------------------------------------------------------------------------


def test_audit_log_counts_corrections_per_field(db):
    log = SqliteAuditLog(db)
    log.record_corrections("d1", "demo", [Correction("total", "1.00", "2.00", "corrected"),
                                          Correction("line.band", "0", "9", "suggestion_changed"),
                                          Correction("line.band", "23", "23", "suggestion_accepted")], fields_shown=9)
    log.record_corrections("d2", "demo", [], fields_shown=6)
    s = log.summary()
    assert s == {"documents": 2, "fields_shown": 15, "corrections": {"total": 1, "line.band": 1},
                 "suggestions_accepted": 1}


def test_audit_log_is_idempotent_per_document(db):
    log = SqliteAuditLog(db)
    for _ in range(2):
        log.record_corrections("d1", "demo", [Correction("total", "1", "2", "corrected")], fields_shown=3)
    assert log.summary()["corrections"] == {"total": 1} and log.summary()["documents"] == 1
