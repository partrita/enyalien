import os
from sqlmodel import create_engine, SQLModel, Session

# Define SQLite database URL.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///enyalien.db")

# connect_args={"check_same_thread": False} is required for SQLite in multi-threaded FastAPI apps
engine = create_engine(
    DATABASE_URL, echo=False, connect_args={"check_same_thread": False}
)


def init_db():
    """Create all tables in the database and seed initial admin + amino acids deck if empty."""
    from datetime import datetime
    from sqlmodel import select, func, text
    from app.models import Card, User, Deck, hash_password

    # Check if migration/reset is needed (transition from old schema string-based deck to deck_id)
    recreate = False
    try:
        with Session(engine) as session:
            columns_info = session.execute(text("PRAGMA table_info(card)")).all()
            column_names = [col[1] for col in columns_info]
            # If the old column 'deck' exists but the new column 'deck_id' doesn't, we drop and recreate
            if "deck" in column_names and "deck_id" not in column_names:
                recreate = True
    except Exception as e:
        print(f"Schema detection check bypassed: {e}")

    if recreate:
        print("Old database schema detected. Dropping all tables to rebuild User & Deck normalized schema...")
        try:
            SQLModel.metadata.drop_all(engine)
        except Exception as e:
            print(f"Failed to drop old tables: {e}")

    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Check if we need to seed the default user
        user_count = session.exec(select(func.count(User.id))).one()
        if user_count == 0:
            # Create default admin user
            admin_user = User(
                username="admin",
                hashed_password=hash_password("admin123"),
            )
            session.add(admin_user)
            session.commit()
            session.refresh(admin_user)

            # Create default deck for admin user
            amino_deck = Deck(
                name="amino acid",
                user_id=admin_user.id,
                is_shared=True,  # Share it by default so other users can see and import it
            )
            session.add(amino_deck)
            session.commit()
            session.refresh(amino_deck)

            # Seed amino acid cards
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
                        deck_id=amino_deck.id,
                        front=front,
                        back=back,
                        next_review=datetime.now(),
                    )
                )
            session.commit()
            print("Database initialized and seeded with default admin user and amino acids deck.")


def get_session():
    """Dependency generator to retrieve db session."""
    with Session(engine) as session:
        yield session
