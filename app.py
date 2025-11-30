# min_lat = 1.22
# max_lat = 1.47

# min_lon = 103.60
# max_lon = 104.00

from fastapi import FastAPI
import math
import uvicorn
import json
import time

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

typical_route = [
    (1.336260, 103.887638),
    (1.338771, 103.705947)
]


DECAY = 0.05  # tweak for steepness

def danger_score(lat, lon, hotspot):
    score = 0
    for h_lat, h_lon, intensity in hotspot:
        d = math.sqrt((lat - h_lat)**2 + (lon - h_lon)**2)
        score += intensity * math.exp(-d / DECAY)
    return min(score, 1.0)

def emotion_score(emotion_payload):
    emo = emotion_payload.get("emotion", "").lower()
    conf = emotion_payload.get("confidence", 0.0)

    danger_emotions = {"angry", "fear", "panic", "upset", "distress"}

    if emo in danger_emotions:
        return conf
    return 0.0

def time_danger_score() -> float:
    """
    hour: 0–23 (24h format)
    Returns a value 0.0 (day) to 1.0 (max night danger)
    """
    hour = time.localtime().tm_hour

    # Daytime: totally safe
    if 6 <= hour < 18:
        return 0.0

    # Early evening: ramp up 18 → 22
    if 18 <= hour < 22:
        return (hour - 18) / 4  # 0 → 1 linearly

    # Late night: fully dangerous
    if 22 <= hour or hour < 6:
        return 1.0
    
    else:
        return 0.0
    

def anomalous_path_score(lat, lon, route_points):
    """Returns score (0 to 1) based on deviation from nearest typical route"""
    if lat is None or lon is None:
        return 0.0

    min_dist = float("inf")

    for p_lat, p_lon in route_points:
        d = math.sqrt((lat - p_lat)**2 + (lon - p_lon)**2)
        min_dist = min(min_dist, d)

    score = min(1.0, min_dist / 0.02)

    return score


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
def process_danger(req:dict):
    payload = req.get("mqtt")
    payload2 = req.get("sentiment")

    lat = payload.get("location", {}).get("latitude")
    lon = payload.get("location", {}).get("longitude")

    threat = payload.get("threatScore", 0)
    danger = danger_score(lat, lon, danger_hotspots)
    fake   = danger_score(lat, lon, fake_news_hotspot)
    time_score = time_danger_score()
    emotion_danger = emotion_score(payload2)
    anomaly_danger = anomalous_path_score(lat, lon, typical_route)

    base_score = (
        0.4 * emotion_danger + 
        0.3 * danger +
        0.1 * time_score +
        0.1 * anomaly_danger)

    FAKE_WEIGHT = 0.25  # dont want to overdo the fake score part and give benefit of doubt
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
        "callAuthority": call_for_help,
        # "debug":{
        #     "emotion_danger":emotion_danger,
        #     "danger":danger,
        #     "time_score":time_score,
        #     "anomaly_danger":anomaly_danger
        # }
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

