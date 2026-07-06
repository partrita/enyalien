from datetime import datetime, timedelta
from typing import Optional
from sqlmodel import SQLModel, Field


class Card(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    deck: str = Field(default="Default", index=True, description="Name of the deck this card belongs to")
    front: str = Field(description="Front of the card (Markdown supported)")
    back: str = Field(description="Back of the card (Markdown supported)")
    created_at: datetime = Field(default_factory=datetime.now)
    repetition: int = Field(default=0, description="Consecutive correct reviews")
    interval: int = Field(default=1, description="Days to wait until next review")
    easiness: float = Field(
        default=2.5, description="Ease factor (difficulty multiplier)"
    )
    next_review: datetime = Field(default_factory=datetime.now)

    def apply_review(self, rating: str) -> "ReviewLog":
        """
        Updates scheduling metrics based on user feedback.
        rating: 'again' (forgot/don't know) or 'good' (remembered/know)
        """
        prev_rep = self.repetition
        prev_interval = self.interval
        prev_easiness = self.easiness

        if rating == "again":
            self.repetition = 0
            self.interval = 1
            # Decrease easiness to make it show up more frequently
            self.easiness = max(1.3, self.easiness - 0.2)
        else:  # rating == 'good'
            self.repetition += 1
            if self.repetition == 1:
                self.interval = 1
            elif self.repetition == 2:
                self.interval = 6
            else:
                self.interval = int(round(prev_interval * self.easiness))

            # Increase easiness slightly for correct answer
            self.easiness = min(3.0, self.easiness + 0.15)

        # Set the next review date/time.
        # To avoid card showing up at exact minutes, truncate to the start of the hour.
        now = datetime.now()
        self.next_review = (now + timedelta(days=self.interval)).replace(
            minute=0, second=0, microsecond=0
        )

        return ReviewLog(
            card_id=self.id,
            rating=rating,
            previous_repetition=prev_rep,
            new_repetition=self.repetition,
            previous_interval=prev_interval,
            new_interval=self.interval,
            previous_easiness=prev_easiness,
            new_easiness=self.easiness,
            reviewed_at=now,
        )


class ReviewLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    card_id: Optional[int] = Field(default=None, foreign_key="card.id")
    reviewed_at: datetime = Field(default_factory=datetime.now)
    rating: str  # 'again' or 'good'
    previous_repetition: int
    new_repetition: int
    previous_interval: int
    new_interval: int
    previous_easiness: float
    new_easiness: float
