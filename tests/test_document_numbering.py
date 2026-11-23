"""Document numbering: one counter per user, going 1, 2, 3 with no gaps, always through the repository."""
from liner.business.document_numbering import SequentialNumbering
from liner.data_access.document_repository import SqliteDocumentRepository
from liner.database.sqlite_db import Database
from liner.models import User


def make(tmp_path):
    return SequentialNumbering(SqliteDocumentRepository(Database(tmp_path / "n.db")))


def test_numbers_start_at_one_and_count_up_by_one(tmp_path):
    numbering = make(tmp_path)
    user = User("demo", "Demo")
    assert [numbering.next_number(user) for _ in range(5)] == [1, 2, 3, 4, 5]


def test_each_user_has_their_own_counter(tmp_path):
    numbering = make(tmp_path)
    a, b = User("a", "A"), User("b", "B")
    assert numbering.next_number(a) == 1
    assert numbering.next_number(a) == 2
    assert numbering.next_number(b) == 1


def test_the_counter_survives_a_restart(tmp_path):
    user = User("demo", "Demo")
    first = make(tmp_path)
    first.next_number(user)
    first.next_number(user)
    assert make(tmp_path).next_number(user) == 3


def test_numbering_only_asks_the_repository():
    class FakeRepo:
        def __init__(self):
            self.asked = []

        def next_counter(self, user_id):
            self.asked.append(user_id)
            return 41

    repo = FakeRepo()
    assert SequentialNumbering(repo).next_number(User("u1", "U")) == 41
    assert repo.asked == ["u1"]
