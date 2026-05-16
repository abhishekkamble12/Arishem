# loading the data from s3 
import boto3
import tempfile

s3 = boto3.client(
    's3',
    aws_access_key_id='YOUR_KEY',
    aws_secret_access_key='YOUR_SECRET',
    region_name='ap-south-1'
)

def download_pdf(bucket_name, s3_key):

    temp_file = tempfile.NamedTemporaryFile(delete=False)

    s3.download_file(
        bucket_name,
        s3_key,
        temp_file.name
    )

    return temp_file.name