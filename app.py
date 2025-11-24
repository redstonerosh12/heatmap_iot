# min_lat = 1.22
# max_lat = 1.47

# min_lon = 103.60
# max_lon = 104.00

from fastapi import FastAPI
import math
import uvicorn

try:
    from mangum import Mangum
    USE_LAMBDA = True
except ImportError:
    USE_LAMBDA = False

print("[DEBUG] USE_LAMBDA=", USE_LAMBDA)


app = FastAPI()

danger_hotspots = [
    (1.306947, 103.833945, 0.8),
    (1.319891, 103.890061, 0.6),
    (1.340711, 103.955230, 0.2)
]

fake_news_hotspot = [
    (1.429458, 103.836149, 0.9),
    (1.252825, 103.830313, 0.5),
    (1.414066, 104.059419, 1.0),
    (1.334065, 103.684282, 0.6)

]


DECAY = 0.05  # tweak for steepness

def danger_score(lat, lon, hotspot):
    score = 0
    for h_lat, h_lon, intensity in hotspot:
        d = math.sqrt((lat - h_lat)**2 + (lon - h_lon)**2)
        score += intensity * math.exp(-d / DECAY)
    return min(score, 1.0)

@app.get("/danger")
def get_danger(lat: float, lon: float):
    dan_score = danger_score(lat, lon, danger_hotspots)
    fake_score = danger_score(lat, lon, fake_news_hotspot)
    
    return {"danger_score": dan_score, "fake_report_score": fake_score}


if USE_LAMBDA:
    handler = Mangum(app)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)

