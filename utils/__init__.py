import urllib.request
import json
import base64
import imghdr
import binascii


def convert_file_from_base64_to_bytes(
    file_as_string: str, file_name: str
) -> tuple[bytes, str]:
    try:
        if file_as_string.startswith("data:"):
            extension = file_as_string.split(",")[0].split(";")[0].split("/")[1]
            return (
                base64.b64decode(file_as_string.split(",")[-1]),
                f"{file_name}.{extension}",
            )
        decoded_file = base64.b64decode(file_as_string)
        extension = imghdr.what(None, decoded_file)
        return decoded_file, f"{file_name}.{extension}"
    except (TypeError, binascii.Error):
        return None, None

def send_post_request(url: str, payload: dict) -> int:
    """Send request, return tuple with status code and error"""
    try:
        request = urllib.request.urlopen(
            urllib.request.Request(
                url=f"{url}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Accept": "application/json"},
                method="POST",
            ),
            timeout=5,
        )
        return request.status, None
    except Exception as e:
        return None, e
