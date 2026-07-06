import os
import sys
from datetime import datetime

# Add project root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select

try:
    from app.database import engine, init_db
    from app.models import Card
except ImportError:
    print(
        "Error: Could not import app modules. Please make sure you are running the script within the virtual environment."
    )
    sys.exit(1)


def seed_data():
    # Make sure tables exist
    init_db()

    # 20 Standard Amino Acids (Korean Name (English Name) : 3-Letter, 1-Letter Code)
    amino_acids = [
        ("알라닌 (Alanine)", "3문자: Ala  \n1문자: A"),
        ("아르기닌 (Arginine)", "3문자: Arg  \n1문자: R"),
        ("아스파라긴 (Asparagine)", "3문자: Asn  \n1문자: N"),
        ("아스파르트산 (Aspartic acid)", "3문자: Asp  \n1문자: D"),
        ("시스테인 (Cysteine)", "3문자: Cys  \n1문자: C"),
        ("글루탐산 (Glutamic acid)", "3문자: Glu  \n1문자: E"),
        ("글루타민 (Glutamine)", "3문자: Gln  \n1문자: Q"),
        ("글라이신 (Glycine)", "3문자: Gly  \n1문자: G"),
        ("히스티딘 (Histidine)", "3문자: His  \n1문자: H"),
        ("아이소류신 (Isoleucine)", "3문자: Ile  \n1문자: I"),
        ("류신 (Leucine)", "3문자: Leu  \n1문자: L"),
        ("라이신 (Lysine)", "3문자: Lys  \n1문자: K"),
        ("메티오닌 (Methionine)", "3문자: Met  \n1문자: M"),
        ("페닐알라닌 (Phenylalanine)", "3문자: Phe  \n1문자: F"),
        ("프롤린 (Proline)", "3문자: Pro  \n1문자: P"),
        ("세린 (Serine)", "3문자: Ser  \n1문자: S"),
        ("트레오닌 (Threonine)", "3문자: Thr  \n1문자: T"),
        ("트립토판 (Tryptophan)", "3문자: Trp  \n1문자: W"),
        ("티로신 (Tyrosine)", "3문자: Tyr  \n1문자: Y"),
        ("발린 (Valine)", "3문자: Val  \n1문자: V"),
    ]

    print("Connecting to database and checking cards...")

    with Session(engine) as session:
        added_count = 0
        skipped_count = 0

        for front, back in amino_acids:
            # Check if this card already exists by front name
            existing = session.exec(select(Card).where(Card.front == front)).first()

            if not existing:
                new_card = Card(
                    deck="amino acid",
                    front=front,
                    back=back,
                    next_review=datetime.now(),
                )
                session.add(new_card)
                added_count += 1
            else:
                skipped_count += 1

        if added_count > 0:
            session.commit()
            print(f"Success! Added {added_count} new amino acid flashcards.")
        else:
            print("No new cards were added.")

        if skipped_count > 0:
            print(f"Skipped {skipped_count} cards (already present in the database).")


if __name__ == "__main__":
    seed_data()
