from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Request, Depends, Form, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
import markdown

from app.database import get_session
from app.models import Card, ReviewLog

router = APIRouter()

# Setup templates directory
templates = Jinja2Templates(directory="app/templates")


def render_markdown(text: str) -> str:
    """Helper to convert markdown strings to HTML safely with standard extensions."""
    return markdown.markdown(
        text, extensions=["fenced_code", "tables", "nl2br", "sane_lists"]
    )


# 1. Dashboard View
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    now = datetime.now()

    # Query database stats
    total_count = session.exec(select(func.count(Card.id))).one()
    due_count = session.exec(
        select(func.count(Card.id)).where(Card.next_review <= now)
    ).one()
    log_count = session.exec(select(func.count(ReviewLog.id))).one()

    # Group statistics by Deck
    deck_names = session.exec(select(Card.deck).distinct()).all()
    # Fallback to default if there is a general total but no distinct deck names resolved (pre-migration)
    if not deck_names and total_count > 0:
        deck_names = ["Default"]

    deck_summaries = []
    for dname in deck_names:
        total_in_deck = session.exec(select(func.count(Card.id)).where(Card.deck == dname)).one()
        due_in_deck = session.exec(
            select(func.count(Card.id))
            .where(Card.deck == dname)
            .where(Card.next_review <= now)
        ).one()
        deck_summaries.append({
            "name": dname,
            "total_count": total_in_deck,
            "due_count": due_in_deck
        })

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "total_count": total_count,
            "due_count": due_count,
            "log_count": log_count,
            "decks": deck_summaries,
        },
    )


# 2. Add Card View
@router.get("/cards/add", response_class=HTMLResponse)
def add_card_page(request: Request):
    return templates.TemplateResponse(request, "add.html")


# 3. Add Card Action (Bulk Import Support)
@router.post("/cards/add")
def add_card_action(
    bulk_data: str = Form(...),
    deck: str = Form("Default"),
    session: Session = Depends(get_session),
):
    lines = bulk_data.splitlines()
    added_count = 0
    
    # Strip and default deck name
    deck_name = deck.strip() if deck else "Default"
    if not deck_name:
        deck_name = "Default"

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            parts = line.split(":", 1)
            front_val = parts[0].strip()
            back_val = parts[1].strip()
            if front_val and back_val:
                new_card = Card(
                    deck=deck_name,
                    front=front_val,
                    back=back_val,
                    next_review=datetime.now(),
                )
                session.add(new_card)
                added_count += 1
    if added_count > 0:
        session.commit()

    # Redirect back to home after successful insert
    return HTMLResponse(status_code=303, headers={"Location": "/"})


# 4. List Cards View
@router.get("/cards", response_class=HTMLResponse)
def list_cards(
    request: Request,
    deck: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    # Fetch distinct deck names for the filter dropdown
    deck_names = session.exec(select(Card.deck).distinct()).all()

    query = select(Card).order_by(Card.id.desc())
    if deck:
        query = query.where(Card.deck == deck)
    cards = session.exec(query).all()

    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "cards": cards,
            "decks": deck_names,
            "selected_deck": deck,
            "now": datetime.now(),
        },
    )


# 5. Delete Card Action (HTMX compatible)
@router.delete("/cards/delete/{card_id}")
def delete_card(card_id: int, session: Session = Depends(get_session)):
    card = session.get(Card, card_id)
    if card:
        session.delete(card)
        session.commit()
    return Response(status_code=200)


# 5a. Edit Card View
@router.get("/cards/edit/{card_id}", response_class=HTMLResponse)
def edit_card_view(
    card_id: int, request: Request, session: Session = Depends(get_session)
):
    card = session.get(Card, card_id)
    if not card:
        return HTMLResponse("카드를 찾을 수 없습니다.", status_code=404)
    return templates.TemplateResponse(request, "edit.html", {"card": card})


# 5b. Edit Card Action
@router.post("/cards/edit/{card_id}")
def edit_card_action(
    card_id: int,
    front: str = Form(...),
    back: str = Form(...),
    deck: str = Form("Default"),
    session: Session = Depends(get_session),
):
    card = session.get(Card, card_id)
    if not card:
        return HTMLResponse("카드를 찾을 수 없습니다.", status_code=404)
    
    deck_name = deck.strip() if deck else "Default"
    if not deck_name:
        deck_name = "Default"

    card.front = front
    card.back = back
    card.deck = deck_name
    session.add(card)
    session.commit()
    return HTMLResponse(status_code=303, headers={"Location": "/cards"})


# 6. Spaced Repetition Core View
@router.get("/review", response_class=HTMLResponse)
def review_page(request: Request, deck: Optional[str] = Query(None)):
    return templates.TemplateResponse(request, "review.html", {"deck": deck})


# 7. Helper Endpoint for Navbar/Dashboard updates
@router.get("/review/due-count")
def due_count(
    deck: Optional[str] = Query(None), session: Session = Depends(get_session)
):
    now = datetime.now()
    query = select(func.count(Card.id)).where(Card.next_review <= now)
    if deck:
        query = query.where(Card.deck == deck)
    count = session.exec(query).one()
    # Return raw text for htmx insertion
    return Response(content=f"{count}개", media_type="text/plain")


# 8. Fetch Next Card Fragment
@router.get("/review/next", response_class=HTMLResponse)
def get_next_card(
    request: Request,
    mode: str = Query("forward"),
    deck: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    now = datetime.now()
    # Fetch oldest due card in specific deck
    query = select(Card).where(Card.next_review <= now)
    if deck:
        query = query.where(Card.deck == deck)
    due_card = session.exec(query.order_by(Card.next_review, Card.id)).first()

    if not due_card:
        return templates.TemplateResponse(
            request, "components/review_empty.html", {"deck": deck}
        )

    # Swap content if reverse mode is selected
    front_content = due_card.back if mode == "reverse" else due_card.front
    rendered_front = render_markdown(front_content)

    return templates.TemplateResponse(
        request,
        "components/card_face.html",
        {
            "card": due_card,
            "rendered_front": rendered_front,
            "mode": mode,
            "deck": deck,
        },
    )


# 9. Get specific card / reveal answer
@router.get("/review/card/{card_id}", response_class=HTMLResponse)
def show_card_details(
    card_id: int,
    request: Request,
    reveal: bool = Query(False),
    mode: str = Query("forward"),
    deck: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    card = session.get(Card, card_id)
    if not card:
        return HTMLResponse("카드 오류", status_code=404)

    # Swap question/answer text based on mode
    front_text = card.back if mode == "reverse" else card.front
    back_text = card.front if mode == "reverse" else card.back

    rendered_front = render_markdown(front_text)

    if reveal:
        rendered_back = render_markdown(back_text)
        return templates.TemplateResponse(
            request,
            "components/card_answer.html",
            {
                "card": card,
                "rendered_front": rendered_front,
                "rendered_back": rendered_back,
                "mode": mode,
                "deck": deck,
            },
        )

    return templates.TemplateResponse(
        request,
        "components/card_face.html",
        {
            "card": card,
            "rendered_front": rendered_front,
            "mode": mode,
            "deck": deck,
        },
    )


# 10. Grade evaluation submission
@router.post("/review/card/{card_id}/submit", response_class=HTMLResponse)
def submit_card_rating(
    card_id: int,
    request: Request,
    rating: str = Query(...),
    mode: str = Query("forward"),
    deck: Optional[str] = Query(None),
    session: Session = Depends(get_session),
):
    card = session.get(Card, card_id)
    if not card:
        return HTMLResponse("카드가 존재하지 않습니다.", status_code=404)

    # Apply algorithm modifications
    log = card.apply_review(rating)

    session.add(card)
    session.add(log)
    session.commit()

    # Process redirect to get the next card fragment
    now = datetime.now()
    query = select(Card).where(Card.next_review <= now)
    if deck:
        query = query.where(Card.deck == deck)
    next_due = session.exec(query.order_by(Card.next_review, Card.id)).first()

    if not next_due:
        # Trigger header update and display completion screen
        response = templates.TemplateResponse(
            request, "components/review_empty.html", {"deck": deck}
        )
        response.headers["HX-Trigger"] = "queue-updated"
        return response

    next_front = next_due.back if mode == "reverse" else next_due.front
    rendered_front = render_markdown(next_front)

    response = templates.TemplateResponse(
        request,
        "components/card_face.html",
        {
            "card": next_due,
            "rendered_front": rendered_front,
            "mode": mode,
            "deck": deck,
        },
    )
    # Tell HTMX to fire an event so the header counter refreshes itself
    response.headers["HX-Trigger"] = "queue-updated"
    return response


# 11. Decks Management Page
@router.get("/decks", response_class=HTMLResponse)
def decks_page(request: Request, session: Session = Depends(get_session)):
    now = datetime.now()
    total_count = session.exec(select(func.count(Card.id))).one()
    deck_names = session.exec(select(Card.deck).distinct()).all()
    if not deck_names and total_count > 0:
        deck_names = ["Default"]

    deck_summaries = []
    for dname in deck_names:
        total_in_deck = session.exec(select(func.count(Card.id)).where(Card.deck == dname)).one()
        due_in_deck = session.exec(
            select(func.count(Card.id))
            .where(Card.deck == dname)
            .where(Card.next_review <= now)
        ).one()
        deck_summaries.append({
            "name": dname,
            "total_count": total_in_deck,
            "due_count": due_in_deck
        })
    return templates.TemplateResponse(request, "decks.html", {"decks": deck_summaries})


# 12. Edit Deck Name Action
@router.post("/decks/edit")
def edit_deck_name(
    old_name: str = Form(...),
    new_name: str = Form(...),
    session: Session = Depends(get_session),
):
    old_name = old_name.strip()
    new_name = new_name.strip()
    if not new_name:
        return HTMLResponse("새 덱 이름은 필수입니다.", status_code=400)
    
    # Batch update card.deck to rename
    cards = session.exec(select(Card).where(Card.deck == old_name)).all()
    for card in cards:
        card.deck = new_name
        session.add(card)
    session.commit()
    return HTMLResponse(status_code=303, headers={"Location": "/decks"})


# 13. Delete Deck Action (HTMX compatible)
@router.delete("/decks/delete/{deck_name}")
def delete_deck(deck_name: str, session: Session = Depends(get_session)):
    # Batch delete all cards belonging to this deck
    cards = session.exec(select(Card).where(Card.deck == deck_name)).all()
    for card in cards:
        session.delete(card)
    session.commit()
    return Response(status_code=200)

