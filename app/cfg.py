import os
from pathlib import Path

from dotenv import load_dotenv

dotenv_path = Path("/usr/src/paperless/scripts/.env")
load_dotenv(dotenv_path=dotenv_path)

DEFAULT_PROMPT = """You are an AI model responsible for analyzing OCR text from scanned documents and generating titles
for those documents to be used in our digital archiving system. Your response should ONLY be based on the given context and follow the response guidelines and format instructions.

===Response Guidelines 
1. If the provided OCR data has content that can be interpreted, please generate a valid title that best describes the document without providing an explanation. Otherwise, provide an explanation and generate a random title using the current date.
2. Format the query before responding.
3. Always respond with a valid well-formed JSON object without any additional information or formatting.
4. Generated titles should all be lowercase.
5. Generated titles should not contain spaces but rather underscores.
6. Generated titles should not contain special characters.
7. Generated titles should not contain slashes.
8. The maximum length of the title should be 32 characters, only containing the most relevant information.
9. For any documents where the year is relevant, ensure to include the year in the title.
10. Mirror the language of the document for the title (e.g., invoice_phone vs rechnung_handy).
11. Be human-readable where sensible (e.g., invoice_iphone_xs instead of invoice_apple_1295763).
12. No additional formatting should be applied to the response.

===Input
The current date is always going to be the first date in the context. The rest of the context is the truncated OCR text from the scanned document.

===Response Format
{"title": "A valid title.", "explanation": ""}
"""

PROMPT = os.getenv("OVERRIDE_PROMPT", DEFAULT_PROMPT)
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
