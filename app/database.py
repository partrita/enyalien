import os
from sqlmodel import create_engine, SQLModel, Session

# Define SQLite database URL.
# Defaults to a local file 'enyalien.db' inside the project directory,
# but can be pointed to a persistent path like '/data/enyalien.db' in Docker.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///enyalien.db")

# connect_args={"check_same_thread": False} is required for SQLite in multi-threaded FastAPI apps
engine = create_engine(
    DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)


def init_db():
    """Create all tables in the database and seed initial amino acids if empty."""
    from datetime import datetime
    from sqlmodel import select, func, text
    from app.models import Card

    SQLModel.metadata.create_all(engine)

    # Automated migration: Add 'deck' column if it doesn't exist (preexisting database)
    with Session(engine) as session:
        try:
            columns_info = session.execute(text("PRAGMA table_info(card)")).all()
            column_names = [col[1] for col in columns_info]
            if "deck" not in column_names:
                session.execute(text("ALTER TABLE card ADD COLUMN deck VARCHAR DEFAULT 'Default'"))
                session.execute(text("CREATE INDEX IF NOT EXISTS ix_card_deck ON card (deck)"))
                session.commit()
                print("Database migration: Added 'deck' column to card table.")
        except Exception as e:
            print(f"Database migration check failed or not applicable: {e}")

    with Session(engine) as session:
        # Check if database is empty
        card_count = session.exec(select(func.count(Card.id))).one()
        if card_count == 0:
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
            for front, back in amino_acids:
                session.add(
                    Card(
                        deck="amino acid",
                        front=front,
                        back=back,
                        next_review=datetime.now(),
                    )
                )
            session.commit()


def get_session():
    """Dependency generator to retrieve db session."""
    with Session(engine) as session:
        yield session
