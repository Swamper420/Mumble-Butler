import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from modules.recommender import MusicRecommender
import config

def test_recommender():
    print("Testing MusicRecommender...")
    recommender = MusicRecommender()
    
    seeds = ["chill lo-fi", "jazz", "Nujabes"]
    print(f"Seeds: {seeds}")
    
    recommendation = recommender.get_recommendation(seeds)
    print(f"Result: {recommendation}")
    
    if recommendation:
        print("✅ Success!")
        print(f"History: {recommender.history}")
    else:
        print("❌ Failed to get recommendation.")

if __name__ == "__main__":
    test_recommender()
