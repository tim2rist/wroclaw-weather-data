"""AWS Lambda: fetch Wrocław weather from Open-Meteo and store JSON in S3."""

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

import boto3

# Try to load environment variables from .env file for local development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("weather-parser")

DEFAULT_S3_BUCKET = "wroclaw-weather-data-snisarenko"
WROCLAW_LAT = 51.1079
WROCLAW_LON = 17.0385

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={WROCLAW_LAT}&longitude={WROCLAW_LON}"
    "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
    "precipitation,weather_code,wind_speed_10m,wind_direction_10m"
    "&timezone=Europe%2FWarsaw"
)


def fetch_weather() -> dict:
    """Fetch current weather data for Wrocław from Open-Meteo API."""
    logger.info("Fetching weather data from Open-Meteo API...")
    request = urllib.request.Request(
        OPEN_METEO_URL,
        headers={"User-Agent": "aws-lambda-wroclaw-weather/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            if status != 200:
                raise RuntimeError(f"Open-Meteo API returned status code {status}")
            data = json.loads(response.read().decode("utf-8"))
            logger.info("Successfully fetched weather data.")
            return data
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to fetch weather data: {exc}") from exc


def run_job() -> dict:
    """Fetch weather and write JSON files (historical & latest) to S3. Used by Lambda, Actions, and ECS."""
    bucket = os.environ.get("S3_BUCKET_NAME", DEFAULT_S3_BUCKET)
    prefix = os.environ.get("S3_KEY_PREFIX", "weather/wroclaw/").rstrip("/") + "/"

    try:
        weather_data = fetch_weather()
    except Exception as exc:
        logger.error(f"Weather data fetch step failed: {exc}")
        raise

    fetched_at = datetime.now(timezone.utc)

    payload = {
        "city": "Wrocław",
        "country": "Poland",
        "coordinates": {"latitude": WROCLAW_LAT, "longitude": WROCLAW_LON},
        "fetched_at": fetched_at.isoformat(),
        "source": "https://open-meteo.com",
        "weather": weather_data,
    }

    body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")

    # Define paths
    historical_key = f"{prefix}{fetched_at.strftime('%Y-%m-%dT%H-%M-%SZ')}.json"
    latest_key = f"{prefix}latest.json"

    logger.info(f"Initializing S3 client to upload to bucket: '{bucket}'")
    s3 = boto3.client("s3")

    try:
        # 1. Upload timestamped snapshot for long-term data lake analysis
        logger.info(f"Uploading historical snapshot: s3://{bucket}/{historical_key}")
        s3.put_object(
            Bucket=bucket,
            Key=historical_key,
            Body=body,
            ContentType="application/json",
        )

        # 2. Upload latest cache for frontend dashboard consumption
        logger.info(f"Uploading latest state: s3://{bucket}/{latest_key}")
        s3.put_object(
            Bucket=bucket,
            Key=latest_key,
            Body=body,
            ContentType="application/json",
        )
    except Exception as exc:
        logger.error(f"Failed to upload data to S3: {exc}")
        raise RuntimeError(f"AWS S3 upload error: {exc}") from exc

    logger.info("Pipeline run successfully completed.")
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "Weather data successfully ingested into S3 Data Lake",
                "bucket": bucket,
                "historical_key": historical_key,
                "latest_key": latest_key,
            }
        ),
    }


def lambda_handler(event, context):
    """AWS Lambda entrypoint."""
    return run_job()


if __name__ == "__main__":
    import sys

    try:
        res = run_job()
        print(res["body"])
    except Exception as e:
        logger.critical(f"Fatal execution error: {e}")
        sys.exit(1)
