import logging
import os
import shutil
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)

# Use a local directory for storage instead of S3
LOCAL_STORAGE_DIR = os.path.join(settings.BASE_DIR, "local_storage")

def get_s3_client():
    # Return a dummy client or None since we aren't using S3
    return None

def upload_file_to_s3(file_obj, s3_key: str) -> bool:
    """
    Uploads a file-like object to local storage instead of S3.
    Returns True if successful, False otherwise.
    """
    try:
        target_path = os.path.join(LOCAL_STORAGE_DIR, s3_key)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Save the file locally
        with open(target_path, 'wb+') as destination:
            for chunk in file_obj.chunks():
                destination.write(chunk)
                
        logger.info("Saved file locally to %s", target_path)
        return True
    except Exception as e:
        logger.exception("Local upload failed for key '%s': %s", s3_key, str(e))
        return False
