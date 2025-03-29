#!/usr/bin/env python3
import argparse
import logging
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from cfg import (
    MISTRAL_API_KEY,
    MISTRAL_MODEL,
    MISTRAL_OCR_MODEL,
    PAPERLESS_API_KEY,
    PAPERLESS_URL,
    PROCESSED_FIELD_ID,
    PROCESSED_FIELD_NAME,
    REPROCESS_DOCUMENTS,
    TRACK_PROCESSED,
    USE_PAPERLESS_OCR,
)
from main import ensure_custom_field_exists, get_document_custom_fields, get_single_document, make_request, process_single_document, set_auth_tokens


def get_all_documents(sess, paperless_url, advanced_filter=None):
    url = paperless_url + "/api/documents/"
    if advanced_filter:
        url += f"?{advanced_filter}"
    response = make_request(sess, url, "GET")
    if not response or not isinstance(response, dict):
        logging.error("could not retrieve documents")
        return []

    documents = response.get("results", [])
    total_count = response.get("count", 0)
    logging.info(f"Found {total_count} total documents, retrieving all pages")

    page = 1
    while response["next"]:
        page += 1
        logging.info(f"Retrieving page {page}")
        response = make_request(sess, response["next"], "GET")
        if not response or not isinstance(response, dict):
            logging.error("could not retrieve documents")
            return []

        documents.extend(response.get("results", []))
        logging.info(f"Retrieved {len(documents)}/{total_count} documents")

    return documents


def download_document(sess, doc_id, paperless_url, temp_dir):
    download_url = f"{paperless_url}/api/documents/{doc_id}/download/"
    logging.info(f"Downloading document {doc_id}")

    doc_source_path = None
    try:
        # Get a streaming response - this returns a requests Response object directly
        response = make_request(sess, download_url, "GET", stream=True)

        # Check if we got a valid response object
        if response and isinstance(response, requests.Response):
            # Create a temporary file to store the document
            os.makedirs(temp_dir, exist_ok=True)
            doc_source_path = os.path.join(temp_dir, f"document_{doc_id}.pdf")

            with open(doc_source_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logging.info(f"Document downloaded to {doc_source_path}")
            return doc_source_path
        else:
            logging.error(f"Could not download document {doc_id} - invalid response type")
            return None
    except Exception as e:
        logging.error(f"Error downloading document {doc_id}: {e}")
        # Clean up if download failed
        if doc_source_path and os.path.exists(doc_source_path):
            try:
                os.remove(doc_source_path)
            except:
                pass
        return None


def run_single_document(args):
    if args.dry:
        logging.info("Running in dry mode")
    logging.info(f"Running for document {args.document_id}")

    # Create a temporary directory for this run
    temp_dir = os.path.join(os.getcwd(), "temp_docs")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        with requests.Session() as sess:
            set_auth_tokens(sess, args.paperlesskey)

            # Handle custom field for tracking processed documents
            if args.track_processed:
                field_id = ensure_custom_field_exists(sess, args.paperlessurl, args.processed_field_name, args.processed_field_id)
                if field_id and field_id != args.processed_field_id:
                    logging.info(f"Custom field ID mismatch, using ID {field_id} instead of configured {args.processed_field_id}")
                    args.processed_field_id = field_id

            doc_info = get_single_document(sess, args.document_id, args.paperlessurl)
            if not isinstance(doc_info, dict):
                logging.error(f"could not retrieve document info for document {args.document_id}")
                return

            doc_contents = doc_info["content"]
            doc_title = doc_info["title"]

            # Download the document
            doc_source_path = download_document(sess, args.document_id, args.paperlessurl, temp_dir)

            process_single_document(
                sess,
                args.document_id,
                doc_title,
                doc_contents,
                doc_source_path,
                doc_info,
                args.paperlessurl,
                args.mistralmodel,
                args.mistralkey,
                args.dry,
            )
    except Exception as e:
        logging.error(f"Error processing document {args.document_id}: {e}")
    finally:
        # Clean up temp directory after processing
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logging.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logging.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")


def process_document_with_retry(sess, doc, temp_dir, args, max_retries=3):
    """Process a single document with retry logic"""
    doc_id = doc["id"]
    doc_title = doc["title"]
    doc_content = doc["content"]

    # Skip if already processed and reprocessing is not enabled
    if args.track_processed and not args.reprocess:
        custom_fields = get_document_custom_fields(doc)
        if args.processed_field_id in custom_fields and custom_fields[args.processed_field_id]:
            logging.info(f"Document {doc_id} has already been processed, skipping (use --reprocess to force reprocessing)")
            return True  # Return success since we're skipping by design

    retries = 0
    while retries < max_retries:
        try:
            # Download the document
            doc_source_path = download_document(sess, doc_id, args.paperlessurl, temp_dir)

            process_single_document(
                sess,
                doc_id,
                doc_title,
                doc_content,
                doc_source_path,
                doc,
                args.paperlessurl,
                args.mistralmodel,
                args.mistralkey,
                args.dry,
            )
            return True
        except Exception as e:
            retries += 1
            logging.error(f"Error processing document {doc_id} (attempt {retries}/{max_retries}): {e}")
            # Add a small delay before retrying
            time.sleep(2)

    logging.error(f"Failed to process document {doc_id} after {max_retries} attempts")
    return False


def run_all_documents(args):
    if args.dry:
        logging.info("Running in dryrun mode")

    logging.info("Running on all documents")

    # Create a temporary directory for this run
    temp_dir = os.path.join(os.getcwd(), "temp_docs")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        with requests.Session() as sess:
            set_auth_tokens(sess, args.paperlesskey)

            # Handle custom field for tracking processed documents
            if args.track_processed:
                field_id = ensure_custom_field_exists(sess, args.paperlessurl, args.processed_field_name, args.processed_field_id)
                if field_id and field_id != args.processed_field_id:
                    logging.info(f"Custom field ID mismatch, using ID {field_id} instead of configured {args.processed_field_id}")
                    args.processed_field_id = field_id

            all_docs = get_all_documents(sess, args.paperlessurl, args.filterstr)
            if not all_docs or not isinstance(all_docs, list):
                logging.error("could not retrieve documents")
                return

            total_docs = len(all_docs)
            logging.info(f"found {total_docs} documents")

            # Filter excluded documents
            if args.exclude:
                all_docs = [doc for doc in all_docs if doc["id"] not in args.exclude]
                logging.info(f"Filtered to {len(all_docs)} documents after exclusions")

            # Process documents with progress tracking
            success_count = 0
            failed_count = 0
            skipped_count = 0

            for i, doc in enumerate(all_docs, 1):
                doc_id = doc["id"]

                # Skip if already processed and reprocessing is not enabled
                if args.track_processed and not args.reprocess:
                    custom_fields = get_document_custom_fields(doc)
                    if args.processed_field_id in custom_fields and custom_fields[args.processed_field_id]:
                        logging.info(f"Document {doc_id} has already been processed, skipping (use --reprocess to force reprocessing)")
                        skipped_count += 1
                        continue

                logging.info(f"Processing document {i}/{len(all_docs)} (ID: {doc_id})")
                result = process_document_with_retry(sess, doc, temp_dir, args)

                if result:
                    success_count += 1
                else:
                    failed_count += 1

                # Log progress periodically
                if i % 10 == 0 or i == len(all_docs):
                    logging.info(
                        f"Progress: {i}/{len(all_docs)} documents processed ({success_count} success, {failed_count} failed, {skipped_count} skipped)"
                    )

                # Clean up temporary files periodically to avoid filling disk
                if i % 20 == 0:
                    try:
                        for f in os.listdir(temp_dir):
                            file_path = os.path.join(temp_dir, f)
                            if os.path.isfile(file_path):
                                os.remove(file_path)
                        logging.debug("Cleaned temporary files")
                    except Exception as e:
                        logging.warning(f"Failed to clean temporary files: {e}")

            logging.info(f"Completed processing {len(all_docs)} documents")
            logging.info(f"Results: {success_count} successful, {failed_count} failed, {skipped_count} skipped")
    except Exception as e:
        logging.error(f"Error during batch processing: {e}")
    finally:
        # Clean up temp directory after processing
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logging.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logging.warning(f"Failed to clean up temporary directory {temp_dir}: {e}")


def parse_args(args):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-l",
        "--loglevel",
        dest="loglevel",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        type=lambda s: s.upper(),
        help="Set the logging level",
    )
    parser.add_argument("--dry", action="store_true", help="Run without making any changes")
    parser.add_argument("--paperlessurl", type=str, default=PAPERLESS_URL, help="URL for the paperless instance")
    parser.add_argument("--paperlesskey", type=str, default=PAPERLESS_API_KEY, help="API key for the paperless instance")
    parser.add_argument("--mistralmodel", type=str, default=MISTRAL_MODEL, help="Mistral AI model to use")
    parser.add_argument("--mistralkey", type=str, default=MISTRAL_API_KEY, help="Mistral AI key to use")
    parser.add_argument("--ocr-model", type=str, default=MISTRAL_OCR_MODEL, help="Mistral OCR model to use for OCR processing")
    parser.add_argument(
        "--use-paperless-ocr", action="store_true", default=USE_PAPERLESS_OCR, help="Use Paperless-ngx built-in OCR instead of Mistral OCR"
    )
    parser.add_argument("--track-processed", action="store_true", default=TRACK_PROCESSED, help="Track processed documents using a custom field")
    parser.add_argument("--processed-field-id", type=int, default=PROCESSED_FIELD_ID, help="Custom field ID to use for tracking processed documents")
    parser.add_argument(
        "--processed-field-name", type=str, default=PROCESSED_FIELD_NAME, help="Custom field name to use for tracking processed documents"
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        default=REPROCESS_DOCUMENTS,
        help="Reprocess documents even if they've been processed before (will update the processed timestamp)",
    )

    subparsers = parser.add_subparsers()

    parser_all = subparsers.add_parser("all", description="Run on all documents")
    parser_all.add_argument("--exclude", action="append", type=int, help="Document ID to skip")
    parser_all.add_argument("--filterstr", type=str, help="Pass in url query parameters to filter document filter request by")
    parser_all.set_defaults(func=run_all_documents)

    parser_single = subparsers.add_parser("single", description="Run on a single document")
    parser_single.add_argument("document_id", type=int)
    parser_single.set_defaults(func=run_single_document)

    parsed_args = parser.parse_args(args)

    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=parsed_args.loglevel)

    try:
        parsed_args.func(parsed_args)
    except AttributeError:
        parser.print_help()
    except Exception as e:
        logging.critical(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    parse_args(sys.argv[1:])
