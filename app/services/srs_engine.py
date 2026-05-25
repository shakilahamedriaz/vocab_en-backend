from datetime import datetime, timedelta
from typing import Tuple


class SRSEngine:
    """
    Spaced Repetition System Engine based on SM-2 algorithm.
    """

    MIN_EASINESS_FACTOR = 1.3
    INITIAL_EASINESS_FACTOR = 2.5

    # Interval schedule for first 5 reviews (in days)
    INTERVAL_SCHEDULE = [1, 3, 7, 14, 30]

    @staticmethod
    def calculate_next_review(
        quality: int,
        repetitions: int,
        easiness_factor: float,
        current_interval: int
    ) -> Tuple[int, int, float, datetime]:
        """
        Calculate next review parameters based on SM-2 algorithm.

        Args:
            quality: User response quality (0-5)
                0: Complete blackout
                1: Incorrect, recognized after seeing answer
                2: Incorrect, easy to recall after seeing answer
                3: Correct with serious difficulty
                4: Correct with minor hesitation
                5: Perfect recall
            repetitions: Number of successful reviews
            easiness_factor: Current easiness factor
            current_interval: Current interval in days

        Returns:
            Tuple of (new_interval, new_repetitions, new_easiness_factor, next_review_date)
        """
        if quality < 3:
            # Incorrect response - reset
            new_interval = 1
            new_repetitions = 0
        else:
            # Correct response
            new_repetitions = repetitions + 1

            if new_repetitions <= len(SRSEngine.INTERVAL_SCHEDULE):
                new_interval = SRSEngine.INTERVAL_SCHEDULE[new_repetitions - 1]
            else:
                new_interval = round(current_interval * easiness_factor)

        # Update easiness factor using SM-2 formula
        # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        ef_adjustment = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
        new_easiness_factor = max(SRSEngine.MIN_EASINESS_FACTOR, easiness_factor + ef_adjustment)

        # Calculate next review date
        next_review = datetime.utcnow() + timedelta(days=new_interval)

        return new_interval, new_repetitions, new_easiness_factor, next_review

    @staticmethod
    def classify_mastery(repetitions: int, easiness_factor: float, accuracy: float) -> str:
        """
        Classify word mastery level.
        """
        if repetitions == 0:
            return "new"
        elif repetitions < 3:
            return "learning"
        elif repetitions >= 5 and easiness_factor > 2.3 and accuracy > 85:
            return "mastered"
        elif repetitions >= 3 and easiness_factor > 2.0:
            return "familiar"
        else:
            return "learning"

    @staticmethod
    def calculate_overdue_days(next_review: datetime) -> int:
        """
        Calculate how many days a word is overdue.
        """
        if next_review is None:
            return 0
        delta = datetime.utcnow() - next_review
        return max(0, delta.days)
