import sys
import os
sys.path.append(os.getcwd())

from src.utils.label_lookup import get_label

def test_label_lookup():
    test_cases = [
        "Michael Jackson - Billie Jean",
        "Arijit Singh - Tum Hi Ho",
        "The Weeknd - Blinding Lights",
        "T-Series - Guru Randhawa - High Rated Gabru"
    ]
    
    for tc in test_cases:
        print(f"Looking up label for: {tc}")
        label = get_label(tc)
        print(f"Result: {label}\n")

if __name__ == "__main__":
    test_label_lookup()
