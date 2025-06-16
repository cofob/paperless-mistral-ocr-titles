import os
from pathlib import Path

from dotenv import load_dotenv

dotenv_path = Path("/usr/src/paperless/scripts/.env")
load_dotenv(dotenv_path=dotenv_path)

DEFAULT_OCR_VERIFICATION_PROMPT = """You are an AI model responsible for analyzing OCR text from scanned documents.
Your task is to determine if the provided text is meaningful or simply unreadable garbage.
Your response must be a valid, well-formed JSON object.

===Response Guidelines
1. Analyze the provided OCR text.
2. If the text is mostly gibberish, random characters, or completely unreadable, set "is_garbage" to true.
3. If the text contains coherent words, sentences, or structured data (like forms, tables, etc.), even if there are some OCR errors, set "is_garbage" to false.
4. Your response should ONLY be the JSON object, with no additional text or explanations.

===Input
The input will be the truncated OCR text from a scanned document.

===Response Format
{"is_garbage": true}
"""

PROMPT = os.getenv("OVERRIDE_PROMPT", DEFAULT_OCR_VERIFICATION_PROMPT)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")
MISTRAL_OCR_MODEL = os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest")
MISTRAL_BASEURL = os.getenv("MISTRAL_BASEURL")

PAPERLESS_URL = os.getenv("PAPERLESS_URL", "http://localhost:8000")
PAPERLESS_API_KEY = os.getenv("PAPERLESS_API_KEY")
TIMEOUT = int(os.getenv("TIMEOUT", "10"))
USE_PAPERLESS_OCR = os.getenv("USE_PAPERLESS_OCR", "false").lower() == "true"

# Custom field tracking configuration
TRACK_PROCESSED = os.getenv("TRACK_PROCESSED", "true").lower() == "true"
PROCESSED_FIELD_ID = int(os.getenv("PROCESSED_FIELD_ID", "3"))
PROCESSED_FIELD_NAME = os.getenv("PROCESSED_FIELD_NAME", "mistral_processed")
REPROCESS_DOCUMENTS = os.getenv("REPROCESS_DOCUMENTS", "false").lower() == "true"
