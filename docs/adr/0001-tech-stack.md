# ADR 0001: Initial Tech Stack

## Status

Accepted

## Context

The project requires a local-first workflow CLI with PostgreSQL persistence, image-assisted card matching, and strict integration safety controls.

## Decision

- use a local CLI architecture with phase-based workflow execution
- use PostgreSQL for workflow and artifact persistence
- use OpenCV for preprocessing and region operations
- use OpenCLIP + FAISS for image candidate retrieval
- use PaddleOCR (with Tesseract fallback) for text extraction
- use RapidFuzz for deterministic text-level disambiguation
- use Cardmarket downloadable bulk pricing files instead of Cardmarket API access

## API Safety and Permission Constraints

- all provider calls go through shared rate-limit middleware
- each provider has explicit max request budget configured in environment
- only officially supported/authorized API endpoints are permitted
- endpoint/scope policy checks run at startup and before live calls
- permission violations fail fast and are treated as non-retryable

## Consequences

- hybrid matching improves robustness vs vision-only matching
- implementation complexity is higher but yields explainable confidence
- strict policy gates reduce accidental API misuse risk

## Revisit Triggers

- provider policy changes
- significant dataset scale increase requiring indexing changes
- material drift in OCR or embedding retrieval quality

