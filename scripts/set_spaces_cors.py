"""
Set CORS policy on the Spaces bucket so browsers can PUT directly from the portal.
Run with: python scripts/set_spaces_cors.py
"""
import os, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

SPACES_REGION = os.getenv("SPACES_REGION")
SPACES_BUCKET = os.getenv("SPACES_BUCKET")
SPACES_KEY    = os.getenv("SPACES_KEY")
SPACES_SECRET = os.getenv("SPACES_SECRET")

missing = [k for k, v in {"SPACES_REGION": SPACES_REGION, "SPACES_BUCKET": SPACES_BUCKET,
                           "SPACES_KEY": SPACES_KEY, "SPACES_SECRET": SPACES_SECRET}.items() if not v]
if missing:
    print(f"ERROR: missing env vars: {missing}")
    sys.exit(1)

region_endpoint = f"https://{SPACES_REGION}.digitaloceanspaces.com"
s3 = boto3.session.Session().client(
    "s3",
    region_name=SPACES_REGION,
    endpoint_url=region_endpoint,
    aws_access_key_id=SPACES_KEY,
    aws_secret_access_key=SPACES_SECRET,
    config=Config(s3={"addressing_style": "virtual"}),
)

cors_config = {
    "CORSRules": [
        {
            "AllowedOrigins": ["https://api.humtech.ai", "http://localhost:8000"],
            "AllowedMethods": ["GET", "PUT", "HEAD"],
            "AllowedHeaders": ["*"],
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3600,
        }
    ]
}

try:
    s3.put_bucket_cors(Bucket=SPACES_BUCKET, CORSConfiguration=cors_config)
    print(f"CORS config applied to bucket: {SPACES_BUCKET}")
    print("Allowed origins: https://api.humtech.ai, http://localhost:8000")
    print("Allowed methods: GET, PUT, HEAD")
except ClientError as e:
    print(f"ERROR setting CORS: {e}")
    sys.exit(1)

# Verify
try:
    result = s3.get_bucket_cors(Bucket=SPACES_BUCKET)
    print("\nVerification — CORS rules now set:")
    for rule in result.get("CORSRules", []):
        print(f"  AllowedOrigins : {rule.get('AllowedOrigins')}")
        print(f"  AllowedMethods : {rule.get('AllowedMethods')}")
        print(f"  AllowedHeaders : {rule.get('AllowedHeaders')}")
except ClientError as e:
    print(f"(Could not verify — AccessDenied on read, but write may have succeeded: {e})")
