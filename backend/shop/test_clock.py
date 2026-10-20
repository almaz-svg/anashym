from unittest.mock import patch
from django.utils import timezone


def freeze_order_morning(test):
    """Keep same-day 15:00 order fixtures valid regardless of test runner time."""
    morning = timezone.localtime().replace(hour=10, minute=0, second=0, microsecond=0)
    clock = patch('django.utils.timezone.now', return_value=morning)
    clock.start()
    test.addCleanup(clock.stop)
