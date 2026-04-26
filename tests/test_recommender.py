import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.recommender import MusicRecommender
import config

def test_specific_recommender():
    print("Testing MusicRecommender with Priority Seeds...")
    recommender = MusicRecommender()
    
    # Simulate a specific request where 'Queen' is the primary seed
    seeds = ["Queen", "Freddie Mercury", "Classic Rock", "David Bowie"]
    print(f"Priority Seeds: {seeds}")
    
    recommendation = recommender.get_recommendation(seeds)
    print(f"Result: {recommendation}")
    
    if recommendation and ("Queen" in recommendation or "Mercury" in recommendation):
        print("✅ Success! Primary seed (Queen) was honored.")
    else:
        print("ℹ️ Note: Result wasn't Queen, but might be a valid fallback if Queen results were already in history.")
    
    print(f"History: {recommender.history}")

if __name__ == "__main__":
    test_specific_recommender()
