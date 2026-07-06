import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import get_session
from app.models import Card, ReviewLog

# Isolated in-memory database with StaticPool to share connection across thread pools
TEST_DATABASE_URL = "sqlite://"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

@pytest.fixture(name="session")
def session_fixture():
    # Make sure all tables are created
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

@pytest.fixture(name="client")
def client_fixture(session):
    def get_session_override():
        return session
    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()

def test_bulk_import_cards(client, session):
    # Test bulk data payload with multiple cards and trailing colons
    bulk_input = "Front One:Back One\nFront Two:Back Two\nEmptyLine:\n"
    
    response = client.post("/cards/add", data={"bulk_data": bulk_input}, follow_redirects=False)
    
    # Importer returns a 303 Redirect to Home view
    assert response.status_code == 303
    
    # Verify card database count and properties
    cards = session.exec(select(Card)).all()
    assert len(cards) == 2
    assert cards[0].front == "Front One"
    assert cards[0].back == "Back One"
    assert cards[1].front == "Front Two"
    assert cards[1].back == "Back Two"

def test_reverse_review_mode_swap(client, session):
    # Register card to test DB
    card = Card(front="FrontQ", back="BackA")
    session.add(card)
    session.commit()
    
    # Query with mode=reverse parameter
    response = client.get(f"/review/card/{card.id}?reveal=true&mode=reverse")
    assert response.status_code == 200
    
    # Question view (rendered_front) should output BackA, answer should output FrontQ
    html_content = response.text
    assert "BackA" in html_content  # Flipped front
    assert "FrontQ" in html_content  # Flipped back


def test_edit_card_view_and_action(client, session):
    # Register card to test DB
    card = Card(front="OriginalFront", back="OriginalBack")
    session.add(card)
    session.commit()

    # 1. Test GET edit view
    response = client.get(f"/cards/edit/{card.id}")
    assert response.status_code == 200
    assert "OriginalFront" in response.text
    assert "OriginalBack" in response.text

    # 2. Test POST edit action
    post_data = {"front": "UpdatedFront", "back": "UpdatedBack"}
    response = client.post(
        f"/cards/edit/{card.id}", data=post_data, follow_redirects=False
    )
    assert response.status_code == 303  # Redirect to /cards

    # 3. Verify changes committed in DB
    session.expire(card)  # Refresh state from DB
    updated_card = session.get(Card, card.id)
    assert updated_card.front == "UpdatedFront"
    assert updated_card.back == "UpdatedBack"


def test_delete_card_action(client, session):
    # Register card to test DB
    card = Card(front="ToDeleteFront", back="ToDeleteBack")
    session.add(card)
    session.commit()

    # Send DELETE request
    response = client.delete(f"/cards/delete/{card.id}")
    assert response.status_code == 200

    # Verify card is gone
    deleted_card = session.get(Card, card.id)
    assert deleted_card is None


def test_deck_bulk_import_and_filtering(client, session):
    # 1. Bulk import into a custom deck
    bulk_input = "Hello:Annyeong\nWorld:Segye"
    response = client.post(
        "/cards/add",
        data={"bulk_data": bulk_input, "deck": "Korean Study"},
        follow_redirects=False
    )
    assert response.status_code == 303

    # Verify DB values have correct deck assigned
    cards = session.exec(select(Card)).all()
    assert len(cards) == 2
    assert cards[0].deck == "Korean Study"
    assert cards[1].deck == "Korean Study"

    # Add another card in a different deck
    other_card = Card(front="Bonjour", back="Hello", deck="French Study")
    session.add(other_card)
    session.commit()

    # 2. Query list view without filters (should show both decks)
    response_all = client.get("/cards")
    assert response_all.status_code == 200
    assert "Korean Study" in response_all.text
    assert "French Study" in response_all.text

    # 3. Query list view filtered by 'Korean Study'
    response_korean = client.get("/cards?deck=Korean+Study")
    assert response_korean.status_code == 200
    assert "Korean Study" in response_korean.text
    # Should not list French Study card contents
    assert "Bonjour" not in response_korean.text


def test_deck_review_queue_filtering(client, session):
    # Insert card into "Math"
    card_math = Card(front="MathQ", back="MathA", deck="Math")
    # Insert card into "History"
    card_history = Card(front="HistoryQ", back="HistoryA", deck="History")
    session.add(card_math)
    session.add(card_history)
    session.commit()

    # 1. Query next due card for Math deck
    response_math = client.get("/review/next?deck=Math")
    assert response_math.status_code == 200
    assert "MathQ" in response_math.text
    assert "HistoryQ" not in response_math.text

    # 2. Query next due card for History deck
    response_history = client.get("/review/next?deck=History")
    assert response_history.status_code == 200
    assert "HistoryQ" in response_history.text
    assert "MathQ" not in response_history.text

    # 3. Submit evaluation inside Math deck scope
    response_submit = client.post(
        f"/review/card/{card_math.id}/submit?rating=good&deck=Math",
        follow_redirects=False
    )
    assert response_submit.status_code == 200
    # Because there are no more due Math cards, it should return the empty completion fragment
    assert "오늘의 복습 완료!" in response_submit.text


def test_deck_edit_card_action(client, session):
    # Insert card in default deck
    card = Card(front="FrontText", back="BackText", deck="Default")
    session.add(card)
    session.commit()

    # Submit edit POST with a new deck name
    post_data = {"front": "FrontText", "back": "BackText", "deck": "Science Deck"}
    response = client.post(
        f"/cards/edit/{card.id}", data=post_data, follow_redirects=False
    )
    assert response.status_code == 303  # Redirect to cards manager

    # Check database model updates
    session.expire(card)
    updated = session.get(Card, card.id)
    assert updated.deck == "Science Deck"


def test_deck_management_page_and_crud(client, session):
    # 1. Setup multiple cards for a deck
    card1 = Card(front="Word1", back="Mean1", deck="Vocab")
    card2 = Card(front="Word2", back="Mean2", deck="Vocab")
    session.add(card1)
    session.add(card2)
    session.commit()

    # 2. Verify decks page lists Vocab
    response = client.get("/decks")
    assert response.status_code == 200
    assert "Vocab" in response.text
    assert "총 2장" in response.text

    # 3. Rename deck Vocab -> Glossary
    edit_data = {"old_name": "Vocab", "new_name": "Glossary"}
    response_edit = client.post("/decks/edit", data=edit_data, follow_redirects=False)
    assert response_edit.status_code == 303

    # Check updated database records
    session.expire_all()
    cards = session.exec(select(Card)).all()
    assert len(cards) == 2
    assert all(c.deck == "Glossary" for c in cards)

    # 4. Delete deck Glossary
    response_delete = client.delete("/decks/delete/Glossary")
    assert response_delete.status_code == 200

    # Check cards are cascade deleted
    remaining_cards = session.exec(select(Card)).all()
    assert len(remaining_cards) == 0


