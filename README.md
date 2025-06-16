# Paperless x Mistral AI - Advanced OCR

## Features

  - 📄 Uses [Mistral AI's powerful OCR model](https://mistral.ai/news/mistral-ocr) to extract text from documents.
  - 🧠 **Verifies OCR output** using a Mistral LLM to determine if the content is meaningful or unreadable garbage.
  - 💾 Only updates the document's content in Paperless-ngx if the OCR text is valid.
  - ⚙️ Supports batch processing to upgrade the OCR on your existing documents.
  - 🏷️ Tracks processed documents using a custom field to prevent redundant work.

## Setup

### Clone Repository

```bash
git clone https://github.com/tomvoelker/paperless-mistral-ocr-titles.git
```

### Create .env file

```bash
cp .env.example .env
# Update .env file with the correct values
```

### Update docker-compose.yml file

Update your `docker-compose.yml` file to mount the scripts and enable the post-consumption script.

```yaml
services:
  # ...
  paperless-webserver:
    # ...
    volumes:
      - /path/to/paperless-mistral-ocr:/usr/src/paperless/scripts
      - /path/to/paperless-mistral-ocr/init:/custom-cont-init.d:ro
  environment:
    # ...
    PAPERLESS_POST_CONSUME_SCRIPT: /usr/src/paperless/scripts/main.py
```

> [\!IMPORTANT]
> The `init` folder (used to ensure the `mistralai` package is installed) must be owned by `root`. Run `sudo chown -R root:root /path/to/paperless-mistral-ocr/init` if you encounter permission issues.

## Processing Documents

### New Documents (Post-Consume)

The script will automatically process new documents as they are ingested into Paperless-ngx. It will:

1.  Perform OCR on the document (using either Mistral AI or Paperless-ngx's built-in OCR).
2.  Use a Mistral LLM to verify that the extracted text is meaningful.
3.  If the text is valid, update the document with the new OCR content. Otherwise, no changes are made.

### Backlog Processing

To process existing documents in your library, you can use the Python CLI directly:

```bash
python cli.py [args] [single|all]
```

**Arguments**

| Option | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `--paperlessurl [URL]` | Yes | `http://localhost:8000` | Sets the URL of the paperless API endpoint. |
| `--paperlesskey [KEY]` | Yes | | Sets the API key to use when authenticating to paperless. |
| `--mistralmodel [MODEL]` | No | `mistral-large-latest` | Sets the Mistral AI model used to **verify OCR content**. |
| `--mistralkey [KEY]` | Yes | | Sets the Mistral API key. |
| `--ocr-model [MODEL]` | No | `mistral-ocr-latest` | Sets the Mistral OCR model to use for processing. |
| `--use-paperless-ocr` | No | `false` | Use Paperless-ngx built-in OCR instead of Mistral's OCR. |
| `--dry` | No | `false` | Enables dry run which only prints the changes that would be made. |
| `--loglevel [LEVEL]` | No | `INFO` | Sets the desired loglevel (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `--track-processed` | No | `true` | Enable tracking of processed documents using a custom field. |
| `--processed-field-id N` | No | `3` | Custom field ID for tracking processed documents. |
| `--processed-field-name NAME`| No | `mistrall_processed` | Custom field name for tracking processed documents. |
| `--reprocess` | No | `false` | Force reprocessing of already processed documents. |

-----

### To run on all documents

```bash
python cli.py [args] all [filter_args]
```

**Filter Arguments**

| Option | Required | Default | Description |
| :--- | :--- | :--- | :--- |
| `--exclude [ID]` | No | | Excludes the document ID specified. Can be used multiple times. |
| `--filterstr [FILTER]` | No | | Filters documents based on a Paperless-ngx URL filter string. |

-----

### To run on a single document

```bash
python cli.py [args] single (document_id)
```

## Additional Notes

  - The OCR model used is `mistral-ocr-latest`, which can provide superior results compared to the default Tesseract engine in Paperless-ngx.
  - The script's primary goal is to improve document content quality. It first performs OCR, then uses a separate LLM call to validate the text before saving it back to Paperless-ngx.

> [\!CAUTION]
> This project was vide-coded for my personal use with documents in Georgian language (Mistral OCR struggles to work with Georgian).

## Contact, Support and Contributions

  - Create a GitHub issue for bug reports, feature requests, or questions.
  - Add a ⭐️ star on GitHub.
  - PRs are welcome.
