import json
import boto3
import os
import math
import time
import urllib.request

sns = boto3.client("sns")

bedrock_runtime = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1"
)
TELEGRAM_TOKEN="8264216094:AAGwEyXOacVF7Ut3gvAD9upeD9IAyeZrato"
CHAT_ID="1409687271"

TOPIC_ARN = os.environ["SNS_TOPIC"]
ENDPOINT_NAME = "emotion-detector-20251201-140734-endpoint"


FRIEND_ACCOUNT_ID = "085557291473"
FRIEND_ROLE_ARN = f"arn:aws:iam::{FRIEND_ACCOUNT_ID}:role/CrossAccountSageMaker"
FRIEND_REGION = "us-east-2"


def get_cross_account_sagemaker_client():
   
    sts = boto3.client("sts")

    try:
        assumed = sts.assume_role(
            RoleArn=FRIEND_ROLE_ARN,
            RoleSessionName="CrossAccountSageMaker"
        )["Credentials"]

        sm_runtime = boto3.client(
            "sagemaker-runtime",
            region_name=FRIEND_REGION,
            aws_access_key_id=assumed["AccessKeyId"],
            aws_secret_access_key=assumed["SecretAccessKey"],
            aws_session_token=assumed["SessionToken"]
        )

        return sm_runtime

    except Exception as e:
        print("Error assuming cross-account role:", e)
        raise


def invoke_sagemaker_emotion_detection(audio_data):
    try:
        # MUST use cross-account creds
        sm_runtime = get_cross_account_sagemaker_client()

        response = sm_runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType="application/json",
            # Body=json.dumps({"audio_base64": audio_data})
            Body = f'{{"audio_base64": "{audio_data}"}}'
        )

        return json.loads(response["Body"].read().decode())

    except Exception as e:
        print(f"Error invoking SageMaker endpoint: {e}")
        return {"emotion": "unknown", "confidence": 0.0, "transcription": ""}



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

DECAY = 0.05


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


def time_danger_score():
    hour = time.localtime().tm_hour

    if 6 <= hour < 18:
        return 0.0
    if 18 <= hour < 22:
        return (hour - 18) / 4
    if hour >= 22 or hour < 6:
        return 1.0
    return 0.0


def anomalous_path_score(lat, lon, route_points):
    if lat is None or lon is None:
        return 0.0

    min_dist = float("inf")
    for p_lat, p_lon in route_points:
        d = math.sqrt((lat - p_lat)**2 + (lon - p_lon)**2)
        min_dist = min(min_dist, d)

    return min(1.0, min_dist / 0.02)


def generate_situation_summary(emotion_result, threat_score, danger_level, lat, lon, device_id, timestamp,
                                   geo_danger, time_score, anomaly_score, fake_news_score):
    """Use Bedrock to generate a user-friendly alert message"""
    try:
        transcription = emotion_result.get('transcription', '')
        emotion = emotion_result.get('emotion', 'unknown')
        confidence = emotion_result.get('confidence', 0.0)

        # Interpret the scores for the AI
        area_risk = "high-risk area" if geo_danger > 0.5 else "moderate-risk area" if geo_danger > 0.2 else "normal area"
        time_risk = "late night hours" if time_score > 0.8 else "evening hours" if time_score > 0.3 else "daytime"
        route_status = "significantly off typical route" if anomaly_score > 0.7 else "slightly off typical route" if anomaly_score > 0.3 else "on typical route"
        reliability = "high false-alarm area" if fake_news_score > 0.6 else "some false reports in area" if fake_news_score > 0.3 else "reliable area"

        prompt = f"""You are a safety alert system. Generate a clear, concise message for someone receiving an SMS alert about a potential safety concern.

Context:
- Detected emotion: {emotion} (confidence: {confidence:.0%})
- Audio said: "{transcription}"
- Overall danger level: {danger_level}
- Area safety: {area_risk}
- Time of day: {time_risk}
- Route: {route_status}
- Area reliability: {reliability}
- GPS coordinates: {lat}, {lon}

Write a brief message (2-4 sentences) that:
1. Describes what was detected and where
4. Mention/summarise what the audio said
2. Mentions any concerning factors (dangerous area, unusual time, off-route, etc.)
3. Indicates urgency and what action should be taken

Be direct and clear. Use plain language. Include the GPS location in your response."""

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        response = bedrock_runtime.invoke_model(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            body=json.dumps(request_body)
        )

        response_body = json.loads(response["body"].read())
        return response_body["content"][0]["text"]

    except Exception as e:
        print(f"Error generating summary with Bedrock: {e}")
        return "Unable to generate situation summary."

import base64
import subprocess
import uuid

def convert_m4a_b64_to_wav_b64(m4a_b64: str) -> str:
    input_path = None
    output_path = None

    try:
        # 1. Decode base64 input
        
        m4a_bytes = base64.b64decode(m4a_b64)
        

        # 2. Write temp input file
        input_path = f"/tmp/{uuid.uuid4()}.m4a"
        output_path = f"/tmp/{uuid.uuid4()}.wav"

       
        with open(input_path, "wb") as f:
            f.write(m4a_bytes)

        # 3. Run FFmpeg to convert → WAV 16kHz PCM S16LE
        ffmpeg_path = "/opt/bin/ffmpeg"

        cmd = [
            ffmpeg_path,
            "-y",                      # Overwrite output
            "-i", input_path,          # Input file
            "-acodec", "pcm_s16le",    # Audio codec
            "-ar", "16000",            # Sample rate 16kHz
            "-ac", "1",                # Mono channel
            output_path
        ]

        
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)

        if proc.returncode != 0:
            stderr = proc.stderr.decode()
            print(f"FFmpeg error (return code {proc.returncode}):")
            print(stderr)
            raise RuntimeError(f"FFmpeg conversion failed: {stderr}")

        print(f"FFmpeg conversion successful")

        # 4. Read output WAV and encode to base64
        
        with open(output_path, "rb") as f:
            wav_bytes = f.read()

        
        wav_b64 = base64.b64encode(wav_bytes).decode()
    

        return wav_b64

    except subprocess.TimeoutExpired:
        print("FFmpeg conversion timed out after 30 seconds")
        raise RuntimeError("FFmpeg conversion timed out")

    except Exception as e:
        print(f"Error during audio conversion: {e}")
        raise

    finally:
        # 5. Cleanup temp files
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
                
            except Exception as e:
               

        if output_path and os.path.exists(output_path):
            try:
                os.remove(output_path)
                
            except Exception as e:
                



def lambda_handler(event, context):

    # for record in event["Records"]:
    #     print("RAW BODY:", record["body"])
    #     payload = json.loads(record["body"])
    for record in event["Records"]:
        body = record.get("body", "").strip()

        if not body:
            print("⚠️ Skipping empty SQS message")
            continue

        try:
            payload = json.loads(body)
        except Exception as e:
            print("⚠️ Failed to parse JSON:", body[:200])
            continue

        print("Received payload:", payload)

        device_id = payload.get("deviceId")
        timestamp = payload.get("timestamp")
        location = payload.get("location", {})
        lat = location.get("latitude")
        lon = location.get("longitude")
        raw_audio_b64 = payload.get("audioData")

        # Convert m4a → wav using ffmpeg
        print("Starting M4A to WAV conversion...")
        try:
            wav_audio_b64 = convert_m4a_b64_to_wav_b64(raw_audio_b64)
            print("Audio conversion successful!")
        except Exception as e:
            print(f"Audio conversion failed: {e}")
            # Fall back to sending raw audio if conversion fails
            wav_audio_b64 = raw_audio_b64
            print("Falling back to raw audio format")

        emotion_result = invoke_sagemaker_emotion_detection(wav_audio_b64)
        print("Emotion detection result:", emotion_result)

        danger = danger_score(lat, lon, danger_hotspots)
        fake = danger_score(lat, lon, fake_news_hotspot)
        time_score = time_danger_score()
        emotion_danger = emotion_score(emotion_result)
        anomaly_danger = anomalous_path_score(lat, lon, typical_route)

        emo = emotion_result.get("emotion", "").lower()
        conf = float(emotion_result.get("confidence", 0.0))

        negative_emotions = ["angry", "fear", "panic", "upset", "distress", "sad", "disgust"]

        emotion_danger = 0.0
        if emo in negative_emotions:
            
            emotion_danger = min(1.0, conf * 2.0)

       
        transcription = emotion_result.get("transcription", "").lower()

        # Tier 1 – Extreme danger keywords → immediate HIGH
        tier1 = ["rape", "raped", "stab", "knife", "kill", "kidnap"]
        # Tier 2 – Strong fear phrases → moderate danger
        tier2 = ["help", "danger", "scared", "follow", "following me", "threat"]

        keyword_danger = 0.0

        if any(k in transcription for k in tier1):
            keyword_danger = 1.0   # MAX danger
        elif any(k in transcription for k in tier2):
            keyword_danger = 0.6


        
        base_score = (
            0.40 * emotion_danger +
            0.30 * danger +
            0.10 * time_score +
            0.10 * anomaly_danger +
            0.40 * keyword_danger     # HIGH weight for keywords
        )

        base_score = min(1.0, base_score)


        FAKE_WEIGHT = 0.25
        reliability = 1 - fake * FAKE_WEIGHT
        reliability = max(0.0, min(1.0, reliability))

        final_score = base_score * reliability


        
        if any(k in transcription for k in tier1):
            final_score = max(final_score, 0.95)   # always HIGH danger
        elif any(k in transcription for k in tier2):
            final_score = max(final_score, 0.70)   # at least MEDIUM


      
        if final_score >= 0.7:
            danger_level = "high"
        elif final_score >= 0.5:
            danger_level = "medium"
        else:
            danger_level = "low"

        call_for_help = (danger_level == "high")
        # call_for_help = True

        print(f"Final threat score: {final_score}, Danger level: {danger_level}")

        summary = generate_situation_summary(
            emotion_result, final_score, danger_level, lat, lon, device_id, timestamp,
            danger, time_score, anomaly_danger, fake
        )
        google_maps_link = f"https://maps.google.com/?q={lat},{lon}"

        message = f"""[Threat Alert]
    Device ID: {device_id}
    Location: {lat}, {lon}
    Timestamp: {timestamp}
    Map: {google_maps_link}

    Emotion: {emotion_result.get('emotion')} (confidence: {emotion_result.get('confidence'):.2f})

    Threat Score: {final_score:.2f}
    Danger Level: {danger_level.upper()}
    Call Authority: {'YES' if call_for_help else 'NO'}

    Summary:{summary}   
    """
        print(f"Message from LLM:{message}")

        

        # sns.publish(
        #     TopicArn=TOPIC_ARN,
        #     Message=message,
        #     Subject=f"Alert - {danger_level.upper()}"
        # )
        url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload= {
            "chat_id":CHAT_ID,
            "text": f"Alert - {danger_level.upper()}\n\n{message}"
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"}
            )

            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read().decode()
                print("Telegram response:", resp_body)

        except Exception as e:
            print("Telegram ERROR:", e)
    # print("SMS sent")
    return {"status": "Processing complete", "message": "SMS sent"}
