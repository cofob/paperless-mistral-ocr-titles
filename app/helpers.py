import json
import logging
import time
import traceback

import requests
from cfg import TIMEOUT
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def strtobool(value: str) -> bool:
    value = value.lower()
    if value in ("y", "yes", "on", "1", "true", "t"):
        return True
    return False


def create_retry_session(retries=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504), session=None):
    """Create a requests session with retry capabilities"""
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def make_request(sess, url, method, body=None, params=None, headers=None, stream=False, max_retries=3):
    if body is not None:
        body = json.dumps(body)
    if headers is None:
        headers = {}

    headers["Content-Type"] = "application/json"

    # Add retry capabilities to the session
    sess = create_retry_session(retries=max_retries, session=sess)

    # Track request attempt
    attempt = 0
    last_error = None

    while attempt < max_retries:
        attempt += 1
        try:
            r = sess.request(method, headers=headers, url=url, params=params, data=body, timeout=TIMEOUT, verify=True, stream=stream)
            r.raise_for_status()

            if stream:
                # For streaming responses, return the raw response object
                # This preserves the .iter_content method for download functionality
                return r

            try:
                # Try to parse as JSON
                json_response = r.json()
                return json_response
            except ValueError:
                # Not JSON, return text
                return r.text

        except requests.exceptions.ConnectionError as e:
            logging.error(f"Error connecting to {url} (attempt {attempt}/{max_retries}): {e}")
            last_error = e
        except requests.exceptions.Timeout as e:
            logging.error(f"Timeout calling {url} (attempt {attempt}/{max_retries}): {e}")
            last_error = e
        except requests.exceptions.HTTPError as e:
            logging.error(f"Http error calling {url} (attempt {attempt}/{max_retries}): {e}")
            logging.error(f"Response: {r.text}")
            last_error = e
        except requests.exceptions.RequestException as e:
            logging.error(f"Error calling {url} (attempt {attempt}/{max_retries}): {e}")
            last_error = e
        except Exception as e:
            logging.error(f"Unexpected error occurred during request to {url} (attempt {attempt}/{max_retries}): {e}")
            last_error = e

        # Only retry if we didn't reach max_retries yet
        if attempt < max_retries:
            # Add exponential backoff
            sleep_time = 2 ** (attempt - 1)
            logging.info(f"Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)

    # If we got here, all retries failed
    logging.error(f"All {max_retries} requests to {url} failed. Last error: {last_error}")
    return None
