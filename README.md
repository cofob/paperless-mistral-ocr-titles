# Paperless x Mistral AI - Title and OCR

This is a fork of [paperless-titles-from-ai](https://github.com/sjafferali/paperless-titles-from-ai) that adds Mistral AI's OCR capabilities and improves on the document processing pipeline.

> [!NOTE]
> Big thanks to [sjafferali](https://github.com/sjafferali) for the original project! As this project severely modifies the original, I've decided to create a new project instead of contributing back to the original.

## Features

- Uses [Mistral AI's powerful OCR model](https://mistral.ai/news/mistral-ocr) to extract text from documents
- Generates meaningful titles for documents based on their content (just like the original project)
- Updates both the document title and OCR content in Paperless-ngx
- Supports batch processing for existing documents
- Tracks processed documents using custom fields
- Smarter title generation using similar documents to maintain naming consistency

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
Update docker compose file with the correct path to the project directory.

```yaml
services:
  # ...
  paperless-webserver:
    # ...
    volumes:
      - /path/to/paperless-titles-from-ai:/usr/src/paperless/scripts
      - /path/to/paperless-titles-from-ai/init:/custom-cont-init.d:ro
  environment:
    # ...
    PAPERLESS_POST_CONSUME_SCRIPT: /usr/src/paperless/scripts/app/main.py
```

> [!IMPORTANT]
> The init folder (used to ensure mistralai package is installed) must be owned by root.

## Processing Documents

### New Documents (Post-Consume)
The script will automatically process new documents as they are ingested into Paperless-ngx. It will:
1. Perform OCR on the document (using either Mistral AI or Paperless-ngx's built-in OCR)
2. Generate a meaningful title based on the document content and similar documents
3. Update the document with both the new title and OCR text

### Backlog Processing
To process existing documents, you can use the Python CLI directly:

```bash
python app/cli.py [args] [single|all]
```

**Arguments**

| Option                | Required | Default                      | Description                                                           |
|-----------------------|----------|------------------------------|-----------------------------------------------------------------------|
| --paperlessurl [URL]  | Yes      | https://paperless.local:8080 | Sets the URL of the paperless API endpoint.                           |
| --paperlesskey [KEY]  | Yes      |                              | Sets the API key to use when authenticating to paperless.             |
| --mistralmodel [MODEL] | No       | mistral-large-latest         | Sets the Mistral AI model used to generate title.                     |
| --mistralkey [KEY]     | Yes      |                              | Sets the Mistral API key used to generate title.                      |
| --ocr-model [MODEL]   | No       | mistral-ocr-latest           | Sets the Mistral OCR model to use for OCR processing.                 |
| --use-paperless-ocr   | No       | false                        | Use Paperless-ngx built-in OCR instead of Mistral's OCR capabilities. |
| --dry                 | No       | False                        | Enables dry run which only prints out the changes that would be made. |
| --loglevel [LEVEL]    | No       | INFO                         | Loglevel sets the desired loglevel.                                   |
| --track-processed     | No       | true                         | Enable tracking of processed documents using custom fields.            |
| --processed-field-id N| No       | 3                           | Custom field ID for tracking processed documents.                      |
| --processed-field-name NAME| No  | mistral_processed          | Custom field name for tracking processed documents.                    |
| --reprocess          | No       | false                       | Force reprocessing of already processed documents.                     |

### To run on all documents
```bash
python app/cli.py [args] all [filter_args]
```

**Filter Arguments**

| Option         | Required | Default | Description                                                                                           |
|----------------|----------|---------|-------------------------------------------------------------------------------------------------------|
| --exclude [ID] | No       |         | Excludes the document ID specified from being updated. This argument may be specified multiple times. |
| --filterstr [FILTERSTRING]   | No       |         | Filters the documents to be updated based on the URL filter string.                                   |

### To run on a single document
```bash
python app/cli.py [args] single (document_id)
```

## Additional Notes
- The default Mistral model used for generation is `mistral-large-latest`.
- The OCR model used is `mistral-ocr-latest`, which provides superior OCR capabilities compared to Paperless-ngx's built-in OCR.
- The script will first perform OCR on the original document and then generate a title based on the OCR text.
- Both the title and OCR text are saved back to the document in Paperless-ngx.

> [!CAUTION]
> This project was hacked together in a few hours, so there are likely some bugs and improvements that can be made. 
> Thus as always, use at your own risk and remember to back up your data!

## Contact, Support and Contributions
- Create a GitHub issue for bug reports, feature requests, or questions.
- Add a ⭐️ star on GitHub.
- PRs are welcome
