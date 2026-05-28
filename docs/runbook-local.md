# Local Runbook

## Prerequisites

- PostgreSQL running locally
- Python runtime and virtual environment (or chosen runtime equivalent)
- eBay API credentials configured in environment variables
- downloaded Cardmarket bulk pricing file available locally

## Setup Steps

1. create and activate virtual environment
2. install dependencies (`pip install -e .` or `pip install -r requirements.txt`)
3. set required environment variables from `.env.example`
4. run DB migrations
5. run `ebay-workflows validate-env`
6. run a dry-run workflow command to validate integration configuration

## First Execution

- use a narrow query and low page cap for initial validation
- verify that run/step records are persisted
- inspect listing/image ingestion counts before enabling larger runs

## API and Permission Safety Checklist

- confirm configured requests-per-minute values are below provider limits
- confirm only approved scopes are present for live API credentials (for example eBay)
- confirm `DISABLE_LIVE_API_WRITES=true` for ingestion-only workflow
- confirm policy checks are enabled before running live API calls

## Troubleshooting

- auth failure: validate credentials and scope grants
- repeated throttling: lower per-provider request budget and page size
- data mismatch: inspect raw payload snapshots and schema validation errors
- OCR/matching drift: compare against labeled regression dataset

