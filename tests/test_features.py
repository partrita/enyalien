import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine, Session, select, func
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import get_session
from app.models import Card, ReviewLog, User, Deck, SessionToken

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


def test_user_registration_and_login(client, session):
    # 1. Register user
    reg_data = {
        "username": "tester",
        "password": "testpassword",
        "password_confirm": "testpassword",
    }
    response = client.post("/register", data=reg_data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/login"

    # Verify user created in DB
    user = session.exec(select(User).where(User.username == "tester")).first()
    assert user is not None

    # 2. Login
    login_data = {
        "username": "tester",
        "password": "testpassword",
    }
    response = client.post("/login", data=login_data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/"
    
    # Session cookie should be set
    assert "session_id" in client.cookies


def test_deck_creation_with_bulk_import(client, session):
    # Register & Login
    client.post("/register", data={"username": "tester", "password": "pass", "password_confirm": "pass"})
    client.post("/login", data={"username": "tester", "password": "pass"})

    # Create deck with bulk cards
    deck_data = {
        "name": "Spanish Vocab",
        "bulk_data": "Uno:One\nDos:Two\nTres:Three"
    }
    response = client.post("/decks", data=deck_data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/decks"

    # Verify deck created
    user = session.exec(select(User).where(User.username == "tester")).first()
    deck = session.exec(select(Deck).where(Deck.name == "Spanish Vocab").where(Deck.user_id == user.id)).first()
    assert deck is not None
    assert deck.is_shared is False

    # Verify cards created
    cards = session.exec(select(Card).where(Card.deck_id == deck.id)).all()
    assert len(cards) == 3
    assert cards[0].front == "Uno"
    assert cards[0].back == "One"


def test_deck_sharing_and_import(client, session):
    # 1. User1 creates and shares a deck
    client.post("/register", data={"username": "user1", "password": "pass", "password_confirm": "pass"})
    client.post("/login", data={"username": "user1", "password": "pass"})

    client.post("/decks", data={"name": "Science", "bulk_data": "Atom:Unit"})
    user1 = session.exec(select(User).where(User.username == "user1")).first()
    deck_user1 = session.exec(select(Deck).where(Deck.name == "Science").where(Deck.user_id == user1.id)).first()

    # Share deck
    response = client.post(f"/decks/share/{deck_user1.id}", follow_redirects=False)
    assert response.status_code == 303
    session.refresh(deck_user1)
    assert deck_user1.is_shared is True

    # Logout User1
    client.post("/logout")
    client.cookies.clear()

    # 2. User2 registers, logs in, and imports User1's shared deck
    client.post("/register", data={"username": "user2", "password": "pass", "password_confirm": "pass"})
    client.post("/login", data={"username": "user2", "password": "pass"})

    # Check shared decks view
    response = client.get("/decks/shared")
    assert response.status_code == 200
    assert "Science" in response.text
    assert "user1" in response.text

    # Import deck
    response = client.post(f"/decks/shared/import/{deck_user1.id}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == "/decks"

    # Verify deck cloned for User2
    user2 = session.exec(select(User).where(User.username == "user2")).first()
    cloned_name = "Science (shared by user1)"
    deck_user2 = session.exec(select(Deck).where(Deck.name == cloned_name).where(Deck.user_id == user2.id)).first()
    assert deck_user2 is not None
    assert deck_user2.is_shared is False  # Cloned deck is private

    # Verify cards cloned
    cards_user2 = session.exec(select(Card).where(Card.deck_id == deck_user2.id)).all()
    assert len(cards_user2) == 1
    assert cards_user2[0].front == "Atom"
    assert cards_user2[0].back == "Unit"


def test_nested_card_management(client, session):
    # Register & Login
    client.post("/register", data={"username": "tester", "password": "pass", "password_confirm": "pass"})
    client.post("/login", data={"username": "tester", "password": "pass"})

    # Create deck
    client.post("/decks", data={"name": "History"})
    user = session.exec(select(User).where(User.username == "tester")).first()
    deck = session.exec(select(Deck).where(Deck.name == "History").where(Deck.user_id == user.id)).first()

    # 1. Add card
    card_data = {"front": "Napoleon", "back": "French General"}
    response = client.post(f"/decks/{deck.id}/cards/add", data=card_data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == f"/decks/{deck.id}/cards"

    card = session.exec(select(Card).where(Card.deck_id == deck.id)).first()
    assert card is not None
    assert card.front == "Napoleon"

    # 2. Edit card
    edit_data = {"front": "Napoleon Bonaparte", "back": "Emperor of the French"}
    response = client.post(f"/decks/{deck.id}/cards/edit/{card.id}", data=edit_data, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["Location"] == f"/decks/{deck.id}/cards"

    session.refresh(card)
    assert card.front == "Napoleon Bonaparte"
    assert card.back == "Emperor of the French"

    # 3. Delete card
    response = client.delete(f"/decks/{deck.id}/cards/delete/{card.id}")
    assert response.status_code == 200

    deleted_card = session.get(Card, card.id)
    assert deleted_card is None
