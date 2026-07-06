import os
import sys

# Add project root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Safely target enyalien.db file in project root folder
DB_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "enyalien.db"
)


def reset_database():
    print("Preparing to reset Enyalien SQLite database...")

    # 1. Delete the SQLite database file if it exists
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            print(f"Removed existing database file: {DB_FILE}")
        except Exception as e:
            print(f"Error removing database file '{DB_FILE}': {e}")
            print(
                "Please make sure the FastAPI server is shut down before attempting a reset."
            )
            sys.exit(1)
    else:
        print("No database file found. Initializing a fresh one...")

    # 2. Re-initialize database tables
    try:
        from app.database import init_db

        init_db()
        print("Database tables initialized successfully.")
        print("Database reset completed successfully! You now have a clean slate.")
    except ImportError:
        print(
            "Error: Could not import app modules. Please check package configuration."
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Prompt for confirmation if run interactively
    if sys.stdin.isatty():
        confirm = input(
            "WARNING: This will delete ALL flashcards and review histories. Proceed? [y/N]: "
        )
        if confirm.lower() not in ["y", "yes"]:
            print("Reset cancelled.")
            sys.exit(0)

    reset_database()
