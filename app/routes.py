import secrets
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, Query, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
import markdown

from app.database import get_session
from app.models import Card, ReviewLog, User, Deck, SessionToken, hash_password, verify_password

router = APIRouter()

# Setup templates directory
templates = Jinja2Templates(directory="app/templates")


# Custom Redirect Exception for Auth redirects
class RedirectException(Exception):
    def __init__(self, url: str):
        self.url = url


async def redirect_exception_handler(request: Request, exc: RedirectException):
    # If HTMX request, return redirect header instead of standard redirect response
    if request.headers.get("HX-Request"):
        return Response(headers={"HX-Redirect": exc.url})
    return RedirectResponse(url=exc.url)


def render_markdown(text: str) -> str:
    """Helper to convert markdown strings to HTML safely with standard extensions."""
    return markdown.markdown(
        text, extensions=["fenced_code", "tables", "nl2br", "sane_lists"]
    )


# Authentication Dependencies
def get_optional_user(request: Request, session: Session = Depends(get_session)) -> Optional[User]:
    token = request.cookies.get("session_id")
    if not token:
        return None
    session_token = session.get(SessionToken, token)
    if not session_token:
        return None
    return session.get(User, session_token.user_id)


def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if not user:
        raise RedirectException(url="/login")
    return user


# --- AUTHENTICATION ROUTES ---

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "register.html", {"user": None})


@router.post("/register")
def register_action(
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    session: Session = Depends(get_session)
):
    user_name = username.strip()
    if not user_name:
        return HTMLResponse("아이디를 입력해 주세요.", status_code=400)
    if password != password_confirm:
        return HTMLResponse("비밀번호가 일치하지 않습니다.", status_code=400)

    # Check if username exists
    existing = session.exec(select(User).where(User.username == user_name)).first()
    if existing:
        return HTMLResponse("이미 존재하는 아이디입니다.", status_code=400)

    # Create user
    new_user = User(
        username=user_name,
        hashed_password=hash_password(password),
    )
    session.add(new_user)
    session.commit()

    return RedirectResponse(url="/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, user: Optional[User] = Depends(get_optional_user)):
    if user:
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"user": None})


@router.post("/login")
def login_action(
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session)
):
    user_name = username.strip()
    user = session.exec(select(User).where(User.username == user_name)).first()
    if not user or not verify_password(password, user.hashed_password):
        return HTMLResponse("아이디 또는 비밀번호가 올바르지 않습니다.", status_code=400)

    # Generate session token
    token = secrets.token_hex(32)
    session_token = SessionToken(token=token, user_id=user.id)
    session.add(session_token)
    session.commit()

    # Create response and set cookie
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="session_id",
        value=token,
        httponly=True,
        max_age=2592000,  # 30 days
        samesite="lax",
    )
    return response


@router.post("/logout")
def logout_action(
    request: Request,
    session: Session = Depends(get_session)
):
    token = request.cookies.get("session_id")
    if token:
        # Delete from DB
        session_token = session.get(SessionToken, token)
        if session_token:
            session.delete(session_token)
            session.commit()

    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("session_id")
    return response


# --- DASHBOARD ROUTE ---

@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    now = datetime.now()

    # Query user's decks
    decks = session.exec(select(Deck).where(Deck.user_id == user.id)).all()

    total_count = 0
    due_count = 0
    deck_summaries = []

    for deck in decks:
        total_in_deck = session.exec(select(func.count(Card.id)).where(Card.deck_id == deck.id)).one()
        due_in_deck = session.exec(
            select(func.count(Card.id))
            .where(Card.deck_id == deck.id)
            .where(Card.next_review <= now)
        ).one()
        
        total_count += total_in_deck
        due_count += due_in_deck

        deck_summaries.append({
            "id": deck.id,
            "name": deck.name,
            "total_count": total_in_deck,
            "due_count": due_in_deck,
            "is_shared": deck.is_shared,
        })

    # Number of review logs for cards belonging to user's decks
    deck_ids = [d.id for d in decks]
    if deck_ids:
        log_count = session.exec(
            select(func.count(ReviewLog.id))
            .join(Card)
            .where(Card.deck_id.in_(deck_ids))
        ).one()
    else:
        log_count = 0

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "user": user,
            "total_count": total_count,
            "due_count": due_count,
            "log_count": log_count,
            "decks": deck_summaries,
        },
    )


# --- DECK ROUTES ---

@router.get("/decks", response_class=HTMLResponse)
def decks_page(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    now = datetime.now()
    decks = session.exec(select(Deck).where(Deck.user_id == user.id)).all()

    deck_summaries = []
    for deck in decks:
        total_in_deck = session.exec(select(func.count(Card.id)).where(Card.deck_id == deck.id)).one()
        due_in_deck = session.exec(
            select(func.count(Card.id))
            .where(Card.deck_id == deck.id)
            .where(Card.next_review <= now)
        ).one()
        deck_summaries.append({
            "id": deck.id,
            "name": deck.name,
            "total_count": total_in_deck,
            "due_count": due_in_deck,
            "is_shared": deck.is_shared,
        })

    return templates.TemplateResponse(
        request,
        "decks.html",
        {
            "user": user,
            "decks": deck_summaries,
        },
    )


@router.post("/decks")
def create_deck(
    name: str = Form(...),
    bulk_data: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck_name = name.strip()
    if not deck_name:
        return HTMLResponse("덱 이름은 필수입니다.", status_code=400)

    # Create deck
    new_deck = Deck(name=deck_name, user_id=user.id)
    session.add(new_deck)
    session.commit()
    session.refresh(new_deck)

    # Parse and import bulk cards if present
    if bulk_data and bulk_data.strip():
        added_count = 0
        for line in bulk_data.splitlines():
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                parts = line.split(":", 1)
                front_val = parts[0].strip()
                back_val = parts[1].strip()
                if front_val and back_val:
                    new_card = Card(
                        deck_id=new_deck.id,
                        front=front_val,
                        back=back_val,
                        next_review=datetime.now(),
                    )
                    session.add(new_card)
                    added_count += 1
        if added_count > 0:
            session.commit()

    return RedirectResponse(url="/decks", status_code=303)


@router.post("/decks/edit/{deck_id}")
def edit_deck_name(
    deck_id: int,
    new_name: str = Form(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    name_clean = new_name.strip()
    if not name_clean:
        return HTMLResponse("덱 이름은 필수입니다.", status_code=400)

    deck.name = name_clean
    session.add(deck)
    session.commit()
    return RedirectResponse(url="/decks", status_code=303)


@router.delete("/decks/delete/{deck_id}")
def delete_deck(
    deck_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    session.delete(deck)
    session.commit()
    return Response(status_code=200)


@router.post("/decks/share/{deck_id}")
def toggle_share_deck(
    deck_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    deck.is_shared = not deck.is_shared
    session.add(deck)
    session.commit()

    return RedirectResponse(url="/decks", status_code=303)


# --- SHARED DECKS ROUTING ---

@router.get("/decks/shared", response_class=HTMLResponse)
def shared_decks_page(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # Fetch all decks shared by other users
    shared_decks = session.exec(
        select(Deck).where(Deck.is_shared == True).where(Deck.user_id != user.id)
    ).all()

    deck_summaries = []
    for s_deck in shared_decks:
        owner = session.get(User, s_deck.user_id)
        owner_name = owner.username if owner else "Unknown"
        total_in_deck = session.exec(select(func.count(Card.id)).where(Card.deck_id == s_deck.id)).one()
        deck_summaries.append({
            "id": s_deck.id,
            "name": s_deck.name,
            "total_count": total_in_deck,
            "owner_name": owner_name,
        })

    return templates.TemplateResponse(
        request,
        "shared_decks.html",
        {
            "user": user,
            "decks": deck_summaries,
        },
    )


@router.post("/decks/shared/import/{deck_id}")
def import_shared_deck(
    deck_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # Fetch original deck
    orig_deck = session.get(Deck, deck_id)
    if not orig_deck or not orig_deck.is_shared:
        return HTMLResponse("공유된 덱을 찾을 수 없습니다.", status_code=404)

    # Get owner info
    owner = session.get(User, orig_deck.user_id)
    owner_name = owner.username if owner else "Unknown"

    # Create new deck cloned for current user
    new_name = f"{orig_deck.name} (shared by {owner_name})"
    cloned_deck = Deck(
        name=new_name,
        user_id=user.id,
        is_shared=False,  # Imported copy is private by default
    )
    session.add(cloned_deck)
    session.commit()
    session.refresh(cloned_deck)

    # Clone all cards from original deck to new deck
    cards = session.exec(select(Card).where(Card.deck_id == orig_deck.id)).all()
    for card in cards:
        cloned_card = Card(
            deck_id=cloned_deck.id,
            front=card.front,
            back=card.back,
            next_review=datetime.now(),  # Reset SRS schedule for new user
        )
        session.add(cloned_card)
    session.commit()

    return RedirectResponse(url="/decks", status_code=303)


# --- CARD MANAGEMENT WITHIN DECKS ---

@router.get("/decks/{deck_id}/cards", response_class=HTMLResponse)
def deck_cards_page(
    deck_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    cards = session.exec(
        select(Card).where(Card.deck_id == deck.id).order_by(Card.id.desc())
    ).all()

    return templates.TemplateResponse(
        request,
        "deck_cards.html",
        {
            "user": user,
            "deck": deck,
            "cards": cards,
        },
    )


@router.post("/decks/{deck_id}/cards/add")
def add_cards_to_deck(
    deck_id: int,
    front: Optional[str] = Form(None),
    back: Optional[str] = Form(None),
    bulk_data: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    added_count = 0
    # Process bulk data if provided
    if bulk_data and bulk_data.strip():
        for line in bulk_data.splitlines():
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                parts = line.split(":", 1)
                f_val = parts[0].strip()
                b_val = parts[1].strip()
                if f_val and b_val:
                    new_card = Card(
                        deck_id=deck.id,
                        front=f_val,
                        back=b_val,
                        next_review=datetime.now(),
                    )
                    session.add(new_card)
                    added_count += 1
    # Process single card if provided
    elif front and back:
        f_val = front.strip()
        b_val = back.strip()
        if f_val and b_val:
            new_card = Card(
                deck_id=deck.id,
                front=f_val,
                back=b_val,
                next_review=datetime.now(),
            )
            session.add(new_card)
            added_count += 1

    if added_count > 0:
        session.commit()

    return RedirectResponse(url=f"/decks/{deck_id}/cards", status_code=303)


@router.delete("/decks/{deck_id}/cards/delete/{card_id}")
def delete_card_from_deck(
    deck_id: int,
    card_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    card = session.get(Card, card_id)
    if not card or card.deck_id != deck.id:
        return HTMLResponse("카드를 찾을 수 없습니다.", status_code=404)

    session.delete(card)
    session.commit()
    return Response(status_code=200)


@router.get("/decks/{deck_id}/cards/edit/{card_id}", response_class=HTMLResponse)
def edit_card_view(
    deck_id: int,
    card_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    card = session.get(Card, card_id)
    if not card or card.deck_id != deck.id:
        return HTMLResponse("카드를 찾을 수 없습니다.", status_code=404)

    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "user": user,
            "deck": deck,
            "card": card,
        },
    )


@router.post("/decks/{deck_id}/cards/edit/{card_id}")
def edit_card_action(
    deck_id: int,
    card_id: int,
    front: str = Form(...),
    back: str = Form(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = session.get(Deck, deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    card = session.get(Card, card_id)
    if not card or card.deck_id != deck.id:
        return HTMLResponse("카드를 찾을 수 없습니다.", status_code=404)

    f_val = front.strip()
    b_val = back.strip()
    if not f_val or not b_val:
        return HTMLResponse("카드 앞면과 뒷면은 필수입니다.", status_code=400)

    card.front = f_val
    card.back = b_val
    session.add(card)
    session.commit()
    return RedirectResponse(url=f"/decks/{deck_id}/cards", status_code=303)


# --- REDIRECT HELPER ENDPOINTS (TO PREVENT BROKEN LINKS) ---

@router.get("/cards")
def redirect_cards():
    return RedirectResponse(url="/decks", status_code=303)


@router.get("/cards/add")
def redirect_add_cards():
    return RedirectResponse(url="/decks", status_code=303)


# --- SPACED REPETITION CORE REVIEW VIEWS ---

@router.get("/review", response_class=HTMLResponse)
def review_page(
    request: Request,
    deck_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    deck = None
    if deck_id:
        deck = session.get(Deck, deck_id)
        if not deck or deck.user_id != user.id:
            return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)

    return templates.TemplateResponse(
        request,
        "review.html",
        {
            "user": user,
            "deck": deck,
            "deck_id": deck_id,
        },
    )


@router.get("/review/due-count")
def due_count(
    deck_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    now = datetime.now()
    if deck_id:
        query = (
            select(func.count(Card.id))
            .where(Card.deck_id == deck_id)
            .where(Card.next_review <= now)
        )
    else:
        user_decks = session.exec(select(Deck.id).where(Deck.user_id == user.id)).all()
        if user_decks:
            query = (
                select(func.count(Card.id))
                .where(Card.deck_id.in_(user_decks))
                .where(Card.next_review <= now)
            )
        else:
            return Response(content="0개", media_type="text/plain")

    count = session.exec(query).one()
    return Response(content=f"{count}개", media_type="text/plain")


@router.get("/review/next", response_class=HTMLResponse)
def get_next_card(
    request: Request,
    mode: str = Query("forward"),
    deck_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    now = datetime.now()
    
    if deck_id:
        deck = session.get(Deck, deck_id)
        if not deck or deck.user_id != user.id:
            return HTMLResponse("덱을 찾을 수 없습니다.", status_code=404)
        query = (
            select(Card)
            .where(Card.deck_id == deck_id)
            .where(Card.next_review <= now)
        )
    else:
        user_decks = session.exec(select(Deck.id).where(Deck.user_id == user.id)).all()
        if not user_decks:
            return templates.TemplateResponse(
                request, "components/review_empty.html", {"deck": None, "deck_id": None, "user": user}
            )
        query = (
            select(Card)
            .where(Card.deck_id.in_(user_decks))
            .where(Card.next_review <= now)
        )

    due_card = session.exec(query.order_by(Card.next_review, Card.id)).first()

    if not due_card:
        deck = session.get(Deck, deck_id) if deck_id else None
        return templates.TemplateResponse(
            request, "components/review_empty.html", {"deck": deck, "deck_id": deck_id, "user": user}
        )

    front_content = due_card.back if mode == "reverse" else due_card.front
    rendered_front = render_markdown(front_content)

    return templates.TemplateResponse(
        request,
        "components/card_face.html",
        {
            "user": user,
            "card": due_card,
            "rendered_front": rendered_front,
            "mode": mode,
            "deck_id": deck_id,
        },
    )


@router.get("/review/card/{card_id}", response_class=HTMLResponse)
def show_card_details(
    card_id: int,
    request: Request,
    reveal: bool = Query(False),
    mode: str = Query("forward"),
    deck_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    card = session.get(Card, card_id)
    if not card:
        return HTMLResponse("카드 오류", status_code=404)

    # Check card ownership via its deck
    deck = session.get(Deck, card.deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("접근 권한이 없습니다.", status_code=403)

    front_text = card.back if mode == "reverse" else card.front
    back_text = card.front if mode == "reverse" else card.back

    rendered_front = render_markdown(front_text)

    if reveal:
        rendered_back = render_markdown(back_text)
        return templates.TemplateResponse(
            request,
            "components/card_answer.html",
            {
                "user": user,
                "card": card,
                "rendered_front": rendered_front,
                "rendered_back": rendered_back,
                "mode": mode,
                "deck_id": deck_id,
            },
        )

    return templates.TemplateResponse(
        request,
        "components/card_face.html",
        {
            "user": user,
            "card": card,
            "rendered_front": rendered_front,
            "mode": mode,
            "deck_id": deck_id,
        },
    )


@router.post("/review/card/{card_id}/submit", response_class=HTMLResponse)
def submit_card_rating(
    card_id: int,
    request: Request,
    rating: str = Query(...),
    mode: str = Query("forward"),
    deck_id: Optional[int] = Query(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    card = session.get(Card, card_id)
    if not card:
        return HTMLResponse("카드가 존재하지 않습니다.", status_code=404)

    deck = session.get(Deck, card.deck_id)
    if not deck or deck.user_id != user.id:
        return HTMLResponse("접근 권한이 없습니다.", status_code=403)

    # Apply algorithm modifications
    log = card.apply_review(rating)

    session.add(card)
    session.add(log)
    session.commit()

    # Process redirect to get the next card fragment
    now = datetime.now()
    if deck_id:
        query = (
            select(Card)
            .where(Card.deck_id == deck_id)
            .where(Card.next_review <= now)
        )
    else:
        user_decks = session.exec(select(Deck.id).where(Deck.user_id == user.id)).all()
        if user_decks:
            query = (
                select(Card)
                .where(Card.deck_id.in_(user_decks))
                .where(Card.next_review <= now)
            )
        else:
            response = templates.TemplateResponse(
                request, "components/review_empty.html", {"deck": None, "deck_id": None, "user": user}
            )
            response.headers["HX-Trigger"] = "queue-updated"
            return response

    next_due = session.exec(query.order_by(Card.next_review, Card.id)).first()

    if not next_due:
        # Trigger header update and display completion screen
        deck_obj = session.get(Deck, deck_id) if deck_id else None
        response = templates.TemplateResponse(
            request, "components/review_empty.html", {"deck": deck_obj, "deck_id": deck_id, "user": user}
        )
        response.headers["HX-Trigger"] = "queue-updated"
        return response

    next_front = next_due.back if mode == "reverse" else next_due.front
    rendered_front = render_markdown(next_front)

    response = templates.TemplateResponse(
        request,
        "components/card_face.html",
        {
            "user": user,
            "card": next_due,
            "rendered_front": rendered_front,
            "mode": mode,
            "deck_id": deck_id,
        },
    )
    # Tell HTMX to fire an event so the header counter refreshes itself
    response.headers["HX-Trigger"] = "queue-updated"
    return response
