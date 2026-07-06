import os
import sys
from datetime import datetime

# Add project root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select

try:
    from app.database import engine
    from app.models import Card
except ImportError:
    print("Error: Could not import app modules. Please check package configuration.")
    sys.exit(1)


def export_backup():
    print("Connecting to database and fetching flashcard data...")

    with Session(engine) as session:
        cards = session.exec(select(Card)).all()

        if not cards:
            print("No cards found in the database. Backup aborted.")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

        # Save backup file directly in the project root folder
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        backup_filename = os.path.join(root_dir, f"enyalien_backup_{timestamp}.md")

        print(f"Generating backup content for {len(cards)} card(s)...")

        lines = []
        lines.append("# 🧠 Enyalien Flashcards Backup")
        lines.append(
            f"- **Generated at**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        lines.append(f"- **Total Cards**: {len(cards)}")
        lines.append("\n---\n")

        # Section 1: Raw Bulk Data (Copy-paste ready for bulk import)
        lines.append("## 📋 Raw Bulk Data (일괄 추가 복사용)")
        lines.append(
            "아래 코드 블록의 전체 텍스트를 복사하여 **일괄 카드 추가(Bulk Import)** 입력란에 그대로 붙여넣을 수 있습니다:\n"
        )
        lines.append("```txt")
        for card in cards:
            escaped_back = card.back.replace("\n", "  \n")
            escaped_back = escaped_back.replace("\r", "")
            lines.append(f"{card.front}:{escaped_back}")
        lines.append("```")
        lines.append("\n---\n")

        # Section 2: Detailed Cards Table
        lines.append("## 🗂️ Card Details (카드 상세 표)")
        lines.append(
            "| ID | 덱 (Deck) | 앞면 (Front) | 뒷면 (Back) | 복습 주기 (Interval) | Ease Factor | 다음 복습 예정일 (Next Review) |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for card in cards:
            front_preview = card.front.replace("|", "\\|").replace("\n", " ")
            back_preview = card.back.replace("|", "\\|").replace("\n", " <br> ")
            next_review_str = (
                card.next_review.strftime("%Y-%m-%d %H:%M")
                if card.next_review
                else "N/A"
            )
            lines.append(
                f"| {card.id} | {card.deck} | {front_preview} | {back_preview} | {card.interval}일 | {card.easiness:.2f} | {next_review_str} |"
            )

        try:
            with open(backup_filename, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print(f"Backup file successfully generated: {backup_filename}")
        except Exception as e:
            print(f"Error saving backup file: {e}")


if __name__ == "__main__":
    export_backup()
