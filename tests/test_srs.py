import pytest
from datetime import datetime, timedelta
from app.models import Card


def test_new_card_defaults():
    card = Card(front="Question", back="Answer")
    assert card.repetition == 0
    assert card.interval == 1
    assert card.easiness == 2.5


def test_review_good_progression():
    card = Card(front="Question", back="Answer")

    # 1st correct review
    log1 = card.apply_review("good")
    assert card.repetition == 1
    assert card.interval == 1
    assert card.easiness == pytest.approx(2.65)  # 2.5 + 0.15
    assert log1.rating == "good"
    assert log1.new_interval == 1

    # 2nd correct review
    card.apply_review("good")
    assert card.repetition == 2
    assert card.interval == 6
    assert card.easiness == pytest.approx(2.8)  # 2.65 + 0.15

    # 3rd correct review
    # interval should be round(6 * 2.8) = 17
    card.apply_review("good")
    assert card.repetition == 3
    assert card.interval == 17
    assert card.easiness == pytest.approx(2.95)  # 2.8 + 0.15

    # Easiness factor cap is 3.0
    card.apply_review("good")
    assert card.easiness == 3.0


def test_review_again_resets():
    card = Card(front="Question", back="Answer")

    # Set to a highly progressed state
    card.repetition = 4
    card.interval = 40
    card.easiness = 2.8

    # User forgets card (Again)
    log = card.apply_review("again")

    assert card.repetition == 0
    assert card.interval == 1
    assert card.easiness == pytest.approx(2.6)  # 2.8 - 0.2
    assert log.rating == "again"

    # Minimum easiness is capped at 1.3
    card.easiness = 1.4
    card.apply_review("again")
    assert card.easiness == 1.3


def test_next_review_timing():
    card = Card(front="Question", back="Answer")
    card.interval = 5

    now = datetime.now()
    card.apply_review("good")  # 1st review makes interval = 1
    card.apply_review("good")  # 2nd review makes interval = 6

    # Expected review date is 6 days from now (since repetition was 0, first good makes interval=1, then second good makes it 6)
    expected_approx = now + timedelta(days=6)

    # Truncated to start of hour
    assert card.next_review.minute == 0
    assert card.next_review.second == 0
    assert (
        abs((card.next_review - expected_approx).total_seconds()) < 7200
    )  # within 2 hours
