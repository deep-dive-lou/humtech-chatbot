"""
Diagnostic: check DigitalOcean Spaces bucket CORS config and generate a test presigned PUT URL.
Run with: python scripts/check_spaces.py
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

print(f"\n=== Spaces config ===")
print(f"Bucket  : {SPACES_BUCKET}")
print(f"Region  : {SPACES_REGION}")
print(f"Endpoint: {region_endpoint}")

# 1. Check CORS config
print("\n=== CORS config ===")
try:
    cors = s3.get_bucket_cors(Bucket=SPACES_BUCKET)
    for rule in cors.get("CORSRules", []):
        print(f"  AllowedOrigins : {rule.get('AllowedOrigins')}")
        print(f"  AllowedMethods : {rule.get('AllowedMethods')}")
        print(f"  AllowedHeaders : {rule.get('AllowedHeaders')}")
        print(f"  ExposeHeaders  : {rule.get('ExposeHeaders')}")
        print(f"  MaxAgeSeconds  : {rule.get('MaxAgeSeconds')}")
        print()
except ClientError as e:
    print(f"  No CORS config (or error): {e}")

# 2. Generate a test presigned PUT URL (without ACL)
print("=== Test presigned PUT URL (no ACL) ===")
test_key = "test/diagnostic-test.txt"
url = s3.generate_presigned_url(
    ClientMethod="put_object",
    Params={"Bucket": SPACES_BUCKET, "Key": test_key, "ContentType": "text/plain"},
    ExpiresIn=300,
)
print(f"  Key : {test_key}")
print(f"  URL : {url}")
print()
print("To test: curl -X PUT -H 'Content-Type: text/plain' -d 'hello' '<URL>'")
print("Expected: HTTP 200 (empty body)")
