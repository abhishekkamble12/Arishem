import logging
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from decouple import config

logger = logging.getLogger(__name__)

OBJECT_STORAGE_REGION = config("OBJECT_STORAGE_REGION", default="us-east-1")
OBJECT_STORAGE_BUCKET = config("OBJECT_STORAGE_BUCKET")
OBJECT_STORAGE_ENDPOINT_URL = config("OBJECT_STORAGE_ENDPOINT_URL", default="")
OBJECT_STORAGE_ACCESS_KEY_ID = config("OBJECT_STORAGE_ACCESS_KEY_ID", default="")
OBJECT_STORAGE_SECRET_ACCESS_KEY = config("OBJECT_STORAGE_SECRET_ACCESS_KEY", default="")

_s3 = None

def get_s3_client():
    global _s3
    if _s3 is None:
        client_kwargs = {
            "region_name": OBJECT_STORAGE_REGION,
        }
        if OBJECT_STORAGE_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = OBJECT_STORAGE_ENDPOINT_URL
        if OBJECT_STORAGE_ACCESS_KEY_ID and OBJECT_STORAGE_SECRET_ACCESS_KEY:
            client_kwargs["aws_access_key_id"] = OBJECT_STORAGE_ACCESS_KEY_ID
            client_kwargs["aws_secret_access_key"] = OBJECT_STORAGE_SECRET_ACCESS_KEY
            
        _s3 = boto3.client("s3", **client_kwargs)
    return _s3

def upload_file_to_s3(file_obj, s3_key: str) -> bool:
    """
    Uploads a file-like object to S3.
    Returns True if successful, False otherwise.
    """
    try:
        s3 = get_s3_client()
        s3.upload_fileobj(file_obj, OBJECT_STORAGE_BUCKET, s3_key)
        logger.info("Uploaded to s3://%s/%s", OBJECT_STORAGE_BUCKET, s3_key)
        return True
    except (ClientError, BotoCoreError) as e:
        logger.exception("S3 upload failed for key '%s': %s", s3_key, str(e))
        return False
