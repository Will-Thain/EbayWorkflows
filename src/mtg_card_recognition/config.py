from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RecognitionSettings:
    """Framework-agnostic settings for MTG card recognition (extractable to standalone repo)."""

    image_cache_dir: str
    tesseract_cmd: str | None = None
    ocr_engine: str = "pytesseract"
    image_download_timeout_ms: int = 20000

    card_zone_ocr_enabled: bool = True
    card_zone_faiss_enabled: bool = True
    card_zone_align_enabled: bool = True
    card_set_symbol_match_enabled: bool = True
    card_set_symbol_min_score: float = 0.45
    card_mana_cost_enabled: bool = True

    image_evidence_min_ocr_similarity: float = 0.60
    image_evidence_min_faiss_score: float = 0.55
    image_evidence_min_mana_confidence: float = 0.30

    image_min_region_score: float = 0.55
    image_allow_full_frame_fallback: bool = True

    faiss_index_path: str = ""
    faiss_top_k: int = 5
    faiss_index_use_art_zone: bool = True
    openclip_model_name: str = "ViT-B-32"
    torch_device: str = "cpu"
    embedding_batch_size: int = 32

    align_min_confidence: float = 0.35
    verify_name_hard_min: float = 0.75
    verify_name_strong_min: float = 0.88
    verify_symbol_strong_min: float = 0.55
    faiss_propose_candidates: bool = True
