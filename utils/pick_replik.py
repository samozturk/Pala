import random

def pick_random(items):
    """Randomly select an element from a given list."""
    if not items:
        return None
    return random.choice(items)