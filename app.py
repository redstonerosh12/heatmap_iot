# min_lat = 1.22
# max_lat = 1.47

# min_lon = 103.60
# max_lon = 104.00

from fastapi import FastAPI
import math
import uvicorn
import json

try:
    from mangum import Mangum
    USE_LAMBDA = True
except ImportError:
    USE_LAMBDA = False

print("[DEBUG] USE_LAMBDA=", USE_LAMBDA)


app = FastAPI()

#lat lon weight
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


def lambda_handler(event, context):
    for record in event["Records"]:
        
        payload = json.loads(record["body"])
        
        print("Received payload:", payload)

        # Step 3: Example — extract threat score
        threat = payload["threatScore"]
        print("Threat score:", threat)

        # Step 4: Example — extract the first batch item
        first_batch = payload["batchData"][0]
        print("First batch datapoint:", first_batch)

    return {}



@app.post("/process_danger")
def process_danger(payload: dict):

    lat = payload.get("location", {}).get("latitude")
    lon = payload.get("location", {}).get("longitude")

    threat = payload.get("threatScore", 0)
    danger = danger_score(lat, lon, danger_hotspots)
    fake   = danger_score(lat, lon, fake_news_hotspot)

    base_score = 0.7 * threat + 0.3 * danger

    FAKE_WEIGHT = 0.3  # dont want to overdo the fake score part and give benefit of doubt
    reliability = 1 - fake * FAKE_WEIGHT
    reliability = max(0.0, min(1.0, reliability))

    final_score = base_score * reliability
    final_score = max(0.0, min(1.0, final_score))

    fin_level = "null"
    if final_score >= 0.7:
        fin_level = "high"
    elif final_score >= 0.5:
        fin_level = "medium"
    else:
        fin_level = "low"

    call_for_help = None
    if fin_level == "high":
        call_for_help = True
    else:
        call_for_help = False

    return {
        "recievedThreatScore": threat,
        "geoDangerScore": danger,
        "fakeNewsScore": fake,
        "finalThreatScore": final_score,
        "dangerLevel": fin_level,
        "callAuthority": call_for_help
    }



@app.get("/danger")
def get_danger(lat: float, lon: float):
    dan_score = danger_score(lat, lon, danger_hotspots)
    fake_score = danger_score(lat, lon, fake_news_hotspot)
    
    return {"danger_score": dan_score, "fake_report_score": fake_score}


if USE_LAMBDA:
    handler = Mangum(app)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)

