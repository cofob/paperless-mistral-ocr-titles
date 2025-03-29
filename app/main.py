#!/usr/bin/env python3
import base64
import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime

import requests
from cfg import (
    MISTRAL_API_KEY,
    MISTRAL_BASEURL,
    MISTRAL_MODEL,
    MISTRAL_OCR_MODEL,
    PAPERLESS_API_KEY,
    PAPERLESS_URL,
    PROCESSED_FIELD_ID,
    PROCESSED_FIELD_NAME,
    PROMPT,
    REPROCESS_DOCUMENTS,
    TIMEOUT,
    TRACK_PROCESSED,
    USE_PAPERLESS_OCR,
)
from helpers import make_request, strtobool
from mistralai import FilePurpose, Mistral


def check_args(doc_pk):
    if not PAPERLESS_API_KEY:
        logging.error("Missing PAPERLESS_API_KEY")
        sys.exit(1)
    if not PAPERLESS_URL:
        logging.error("Missing PAPERLESS_URL")
        sys.exit(1)
    if not MISTRAL_API_KEY:
        logging.error("Missing MISTRAL_API_KEY")
        sys.exit(1)
    if not MISTRAL_MODEL:
        logging.error("Missing MISTRAL_MODEL")
        sys.exit(1)
    if not doc_pk:
        logging.error("Missing DOCUMENT_ID")
        sys.exit(1)
    if not PROMPT:
        logging.error("Missing PROMPT")
        sys.exit(1)
    if not TIMEOUT:
        logging.error("Missing TIMEOUT")
        sys.exit(1)


def encode_file_to_base64(file_path):
    """Encode a file to base64."""
    with open(file_path, "rb") as file:
        return base64.b64encode(file.read()).decode("utf-8")


def perform_mistral_ocr(file_path, mistral_api_key):
    """Perform OCR using Mistral AI's OCR capabilities."""
    client = Mistral(api_key=mistral_api_key)

    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return None

    try:
        # If file is a PDF
        if file_path.lower().endswith(".pdf"):
            # Upload the PDF file
            uploaded_file = client.files.upload(
                file={
                    "file_name": os.path.basename(file_path),
                    "content": open(file_path, "rb"),
                },
                purpose="ocr",  # type: ignore (https://github.com/mistralai/client-python/issues/196)
            )
            signed_url = client.files.get_signed_url(file_id=uploaded_file.id)
            ocr_response = client.ocr.process(
                model=MISTRAL_OCR_MODEL,
                document={"type": "document_url", "document_url": signed_url.url},
            )
        # If file is an image
        else:
            logging.warning(f"Performing OCR on image file {file_path} (this is less tested and probably more error prone)")
            base64_image = encode_file_to_base64(file_path)

            # Detect image format for the correct MIME type
            image_format = "jpeg"  # Default
            if file_path.lower().endswith((".png")):
                image_format = "png"
            elif file_path.lower().endswith((".gif")):
                image_format = "gif"

            ocr_response = client.ocr.process(
                model=MISTRAL_OCR_MODEL, document={"type": "image_url", "image_url": f"data:image/{image_format};base64,{base64_image}"}
            )

        # Extract text content from all pages
        text_content = ""
        for page in ocr_response.pages:
            text_content += page.markdown + "\n\n"

        return text_content.strip()
    except Exception as e:
        logging.error(f"Error performing OCR with Mistral: {e}")
        return None
    finally:
        # Attempt to clean up any uploaded files
        try:
            if "uploaded_file" in locals() and hasattr(uploaded_file, "id"):
                client.files.delete(file_id=uploaded_file.id)
                logging.debug(f"Deleted temporary Mistral file: {uploaded_file.id}")
        except Exception as e:
            logging.warning(f"Failed to delete temporary Mistral file: {e}")


def generate_title(content, model, api_key, similar_docs=None):
    """Generate a title for the document content using Mistral AI with JSON response format."""
    client = Mistral(api_key=api_key)
    now = datetime.now()

    # Build the context with similar documents if available
    context = now.strftime("%m/%d/%Y") + " " + content[:4000]

    if similar_docs:
        similar_titles = "\nTitles of similar documents:\n" + "\n".join([f"- {doc['title']}" for doc in similar_docs])
        context += similar_titles

    messages = [{"role": "system", "content": PROMPT}, {"role": "user", "content": context}]

    try:
        chat_response = client.chat.complete(model=model, messages=messages, response_format={"type": "json_object"})

        if not chat_response.choices:
            logging.error("No response from Mistral")
            return None

        # The response is already in JSON format, so we can return it directly
        return chat_response.choices[0].message.content
    except Exception as e:
        logging.error(f"Error generating title with Mistral: {e}")
        return None


def set_auth_tokens(session: requests.Session, api_key):
    session.headers.update({"Authorization": f"Token {api_key}"})


def parse_response(response):
    """Parse the JSON response from Mistral."""
    try:
        data = json.loads(response)
        return data["title"], data.get("explanation", "")
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON response: {e}")
        return None, None
    except KeyError as e:
        logging.error(f"Missing required field in response: {e}")
        return None, None


def update_document_title(sess, doc_pk, title, paperless_url):
    url = paperless_url + f"/api/documents/{doc_pk}/"
    body = {"title": title}
    resp = make_request(sess, url, "PATCH", body=body)
    if not resp:
        logging.error(f"could not update document {doc_pk} title to {title}")
        return
    logging.info(f"updated document {doc_pk} title to {title}")


def update_document_content(sess, doc_pk, content, paperless_url):
    url = paperless_url + f"/api/documents/{doc_pk}/"
    body = {"content": content}
    resp = make_request(sess, url, "PATCH", body=body)
    if not resp:
        logging.error(f"could not update document {doc_pk} content")
        return
    logging.info(f"updated document {doc_pk} content")


def get_custom_fields(sess, paperless_url):
    """Get all custom fields from Paperless to verify our field exists."""
    url = paperless_url + "/api/custom_fields/"
    resp = make_request(sess, url, "GET")
    if not resp or not isinstance(resp, dict):
        logging.error("Could not retrieve custom fields")
        return None
    return resp.get("results", [])


def create_custom_field(sess, paperless_url, field_name):
    """Create a custom field for tracking processed documents if it doesn't exist."""
    url = paperless_url + "/api/custom_fields/"
    body = {
        "name": field_name,
        "data_type": "number",  # Use number type for UNIX timestamp
        "required": False,
    }
    resp = make_request(sess, url, "POST", body=body)
    if not resp or not isinstance(resp, dict):
        logging.error(f"Could not create custom field {field_name}")
        return None
    logging.info(f"Created custom field {field_name} with ID {resp.get('id')}")
    return resp.get("id")


def ensure_custom_field_exists(sess, paperless_url, field_name, field_id):
    """Make sure the custom field exists, create it if not."""
    fields = get_custom_fields(sess, paperless_url)
    if not fields:
        # Try to create the field
        return create_custom_field(sess, paperless_url, field_name)

    # Check if our field exists by ID
    for field in fields:
        if field.get("id") == field_id:
            logging.debug(f"Found existing custom field {field_name} with ID {field_id}")
            return field_id

    # Check if our field exists by name
    for field in fields:
        if field.get("name") == field_name:
            field_id = field.get("id")
            logging.debug(f"Found existing custom field {field_name} with ID {field_id}")
            return field_id

    # Field doesn't exist, create it
    return create_custom_field(sess, paperless_url, field_name)


def get_document_custom_fields(doc_info):
    """Extract custom fields from document info."""
    custom_fields = {}
    if "custom_fields" in doc_info:
        for field in doc_info["custom_fields"]:
            custom_fields[field["field"]] = field["value"]
    return custom_fields


def check_document_processed(custom_fields, field_id):
    """Check if the document has already been processed."""
    if not custom_fields:
        return False

    # Check if our field exists in the custom fields
    if field_id in custom_fields and custom_fields[field_id]:
        return True

    return False


def update_document_processed_status(sess, doc_pk, paperless_url, field_id):
    """Update the custom field to indicate the document has been processed."""
    # First, get the current document to retrieve existing custom fields
    doc_info = get_single_document(sess, doc_pk, paperless_url)
    if not isinstance(doc_info, dict):
        logging.error(f"Could not retrieve document info for document {doc_pk}")
        return False

    # Get existing custom fields
    existing_custom_fields = doc_info.get("custom_fields", [])

    # Check if our field already exists in the list
    field_exists = False
    timestamp = int(datetime.now().timestamp())

    # Create a new list of custom fields, preserving existing ones
    updated_custom_fields = []
    for field in existing_custom_fields:
        if field["field"] == field_id:
            # Update the existing field
            field_exists = True
            updated_field = {"field": field_id, "value": timestamp}
            updated_custom_fields.append(updated_field)
        else:
            # Preserve other fields
            updated_custom_fields.append(field)

    # Add our field if it doesn't exist yet
    if not field_exists:
        updated_custom_fields.append({"field": field_id, "value": timestamp})

    # Update the document with all custom fields
    url = paperless_url + f"/api/documents/{doc_pk}/"
    body = {"custom_fields": updated_custom_fields}
    resp = make_request(sess, url, "PATCH", body=body)

    if not resp:
        logging.error(f"Could not update processed status for document {doc_pk}")
        return False

    logging.info(f"Updated processed status for document {doc_pk} with timestamp {timestamp}")
    return True


def process_single_document(
    sess, doc_pk, doc_title, doc_contents, doc_source_path, doc_info, paperless_url, mistral_model, mistral_api_key, dry_run=False
):
    temp_dir = None
    try:
        # If tracking is enabled, check if document has already been processed
        if TRACK_PROCESSED and not REPROCESS_DOCUMENTS:
            custom_fields = get_document_custom_fields(doc_info)
            if check_document_processed(custom_fields, PROCESSED_FIELD_ID):
                logging.info(f"Document {doc_pk} has already been processed, skipping (set REPROCESS_DOCUMENTS=true to reprocess)")
                return False

        # If configured to use Mistral OCR, perform OCR on the document
        if not USE_PAPERLESS_OCR and doc_source_path:
            new_content = perform_mistral_ocr(doc_source_path, mistral_api_key)
            if not new_content:
                logging.error(f"Failed to perform OCR on document {doc_pk}, using existing content")
            else:
                doc_contents = new_content
                if not dry_run:
                    update_document_content(sess, doc_pk, doc_contents, paperless_url)
                else:
                    logging.info(f"would update document {doc_pk} content to: \n\n{doc_contents}")

        # Find similar documents
        similar_docs = find_similar_documents(sess, doc_pk, paperless_url)
        if similar_docs:
            logging.info(
                f"Found {len(similar_docs)} similar documents to help with title generation: {[similar_doc['title'] for similar_doc in similar_docs]}"
            )
        else:
            logging.info(f"No similar documents found for document {doc_pk}")

        response = generate_title(doc_contents, mistral_model, mistral_api_key, similar_docs)
        if not response:
            logging.error(f"could not generate title for document {doc_pk}")
            return False
        title, explain = parse_response(response)
        if not title:
            logging.error(f"could not parse response for document {doc_pk}: {response}")
            return False
        logging.info(f"will update document {doc_pk} title from {doc_title} to: {title} because {explain}")

        # Update the document title
        if not dry_run:
            update_document_title(sess, doc_pk, title, paperless_url)

            # Update the processed status if tracking is enabled
            if TRACK_PROCESSED:
                update_document_processed_status(sess, doc_pk, paperless_url, PROCESSED_FIELD_ID)

        return True
    except Exception as e:
        logging.error(f"Error processing document {doc_pk}: {e}")
        return False
    finally:
        # Clean up the temporary file if we created one
        if doc_source_path and os.path.exists(doc_source_path) and "temp_docs" in doc_source_path:
            try:
                os.remove(doc_source_path)
                logging.debug(f"Removed temporary file: {doc_source_path}")
            except Exception as e:
                logging.warning(f"Failed to remove temporary file {doc_source_path}: {e}")


def get_single_document(sess, doc_pk, paperless_url):
    url = paperless_url + f"/api/documents/{doc_pk}/"
    return make_request(sess, url, "GET")


def run_for_document(doc_pk):
    check_args(doc_pk)

    with requests.Session() as sess:
        set_auth_tokens(sess, PAPERLESS_API_KEY)

        # Check if we're tracking processed documents and ensure the field exists
        global PROCESSED_FIELD_ID  # Move global declaration to the beginning of the scope
        if TRACK_PROCESSED:
            field_id = ensure_custom_field_exists(sess, PAPERLESS_URL, PROCESSED_FIELD_NAME, PROCESSED_FIELD_ID)
            if field_id and field_id != PROCESSED_FIELD_ID:
                logging.info(f"Custom field ID mismatch, using ID {field_id} instead of configured {PROCESSED_FIELD_ID}")
                PROCESSED_FIELD_ID = field_id

        doc_info = get_single_document(sess, doc_pk, PAPERLESS_URL)
        if not isinstance(doc_info, dict):
            logging.error(f"could not retrieve document info for document {doc_pk}")
            return

        doc_contents = doc_info["content"]
        doc_title = doc_info["title"]
        doc_source_path = os.getenv("DOCUMENT_SOURCE_PATH", None)

        process_single_document(
            sess, doc_pk, doc_title, doc_contents, doc_source_path, doc_info, PAPERLESS_URL, MISTRAL_MODEL, MISTRAL_API_KEY, DRY_RUN
        )


def find_similar_documents(sess, doc_pk, paperless_url, limit=5):
    """Find similar documents using Paperless-ngx's 'more like' search API."""

    # Use the 'more_like_id' endpoint to find similar documents
    url = f"{paperless_url}/api/documents/"
    params = {"more_like_id": doc_pk, "ordering": "-score", "page_size": limit}  # Sort by relevance

    resp = make_request(sess, url, "GET", params=params)
    if not resp or not isinstance(resp, dict):
        logging.error("Could not retrieve similar documents")
        return []

    # Extract titles of similar documents
    similar_docs = []
    for doc in resp.get("results", []):
        if doc.get("id") != doc_pk:  # Double check we're not including the current document
            similar_docs.append({"id": doc.get("id"), "title": doc.get("title"), "score": doc.get("score", 0)})

    return similar_docs


if __name__ == "__main__":
    LOGLEVEL = os.environ.get("LOGLEVEL", "INFO").upper()
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=LOGLEVEL)
    DRY_RUN = strtobool(os.getenv("DRY_RUN", "false"))
    if DRY_RUN:
        logging.info("DRY_RUN ENABLED")

    # Ensure temp directory exists but is clean
    temp_dir = os.path.join(os.getcwd(), "temp_docs")
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
            logging.debug(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logging.warning(f"Failed to clean temporary directory {temp_dir}: {e}")
    os.makedirs(temp_dir, exist_ok=True)

    run_for_document(os.getenv("DOCUMENT_ID"))
