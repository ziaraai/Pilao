"""Dashboard (US-5.3): each dossier's step follows its latest DCE, analysis and memoir."""

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.api.helpers import signed_in_client
from tests.api.test_bids import RC, deposit, new_bid
from tests.conftest import FakeQueue, Outbox

Factory = Callable[[], TestClient]


def steps(c: TestClient) -> list[tuple[str, list[str], str | None, bool]]:
    return [
        (b["title"], b["done"], b["next_step"], b["waiting"])
        for b in c.get("/dashboard").json()["bids"]
    ]


def test_a_dossier_moves_through_its_steps(
    make_client: Factory, outbox: Outbox, queue: FakeQueue
) -> None:
    c = signed_in_client(make_client, outbox)
    bid = new_bid(c, title="Écoles")
    assert steps(c) == [("Écoles", [], "Déposer le DCE", False)]

    assert deposit(c, bid, ("RC.pdf", RC)).status_code == 202
    assert steps(c) == [("Écoles", [], "Lecture du DCE en cours", True)]  # being read

    queue.drain_dce()
    [(_, done, step, waiting)] = steps(c)
    assert done == ["dce"]
    assert (step, waiting) == ("Analyse du DCE en cours", True)  # started on its own

    actions = c.get("/dashboard").json()["actions"]
    assert actions == []  # nothing to do while Pilao works, and no deadline
