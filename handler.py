import io
import json
import os
from datetime import datetime
from time import sleep
from uuid import uuid4

import boto3
from utils import convert_file_from_base64_to_bytes, send_post_request

bucket_name = os.environ.get("BUCKET_NAME", "t3s-tj9y5a9l7vavms53hss3")
region = "eu-central-1"

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("TextExtractionResults")

textract = boto3.client("textract")


def file_upload(event, context):
    transaction_id = uuid4().hex

    try:
        body = json.loads(event["body"]) or {}
        callback_url = body.get("callback_url")
        file_as_string = body.get("file")
        if not callback_url or not file_as_string:
            return {"statusCode": 422, "body": "Missing required parameters"}
        decoded_file, file_name = convert_file_from_base64_to_bytes(
            file_as_string, transaction_id
        )
        s3.upload_fileobj(io.BytesIO(decoded_file), bucket_name, file_name)
        file_url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{file_name}"
        # Start Textract job
        response = textract.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": bucket_name, "Name": file_name}}
        )
        job_id = response["JobId"]

    except Exception as exc:
        return {"statusCode": 400, "body": str(exc)}

    table.put_item(
        Item={
            "file_id": transaction_id,
            "file_url": file_url,
            "status": "pending",
            "callback_url": callback_url,
            "job_id": job_id,
        }
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "message": "File uploaded successfully",
                "id": str(transaction_id),
                "job_id": job_id,
            }
        ),
    }


def process_uploaded_file(event, context):
    # Get the bucket name and object key from the S3 event
    key = event["Records"][0]["s3"]["object"]["key"]
    file_id = key.split(".")[0]
    db_response = table.get_item(Key={"file_id": file_id})
    callback_url = db_response["Item"]["callback_url"]
    file_url = db_response["Item"]["file_url"]
    job_id = db_response["Item"]["job_id"]

    result, error = get_textract_result(job_id, 100)
    if error:
        send_post_request(callback_url, {"id": file_id, "status": "failed"})
    else:
        formatted_result = " \n".join(
            [line.get("Text", "") for line in result if line.get("Text")]
        )
        send_post_request(
            callback_url,
            {
                "id": file_id,
                "status": "success",
                "file_url": file_url,
                "result": formatted_result,
            },
        )
    db_response = table.put_item(
        Item={
            "file_id": file_id,
            "file_url": file_url,
            "result": formatted_result,
            "status": "success",
            "callback_url": callback_url,
        }
    )


def get_textract_result(
    job_id: str, max_results: int = 100, max_retries: int = 14, retry: int = 1
) -> tuple[str, str]:
    response = textract.get_document_text_detection(
        JobId=job_id, MaxResults=max_results
    )
    if response.get("JobStatus") == "IN_PROGRESS":
        print(str(datetime.now()), "Task in progress... sleep")
        if retry == max_retries:
            return None, "Execution was stopped because time is out..."
        retry += 1
        sleep(20)
        return get_textract_result(job_id, max_results, max_retries, retry)
    elif response.get("JobStatus") == "FAILED":
        return None, "Task failed"
    else:
        return response["Blocks"], None


def get_result(event, context):
    file_id = event["pathParameters"]["file_id"]
    response404 = {"statusCode": 404, "body": json.dumps({"message": "Not found"})}
    if len(file_id) != 32:
        return response404

    db_response = table.get_item(Key={"file_id": file_id})
    result = db_response.get("Item")
    if not result:
        return response404
    return {
        "statusCode": 200,
        "body": json.dumps(result),
    }
