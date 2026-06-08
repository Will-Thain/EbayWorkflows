from __future__ import annotations

from mtg_card_recognition.config import RecognitionSettings

from ..config import Settings


def recognition_settings_from_app(settings: Settings) -> RecognitionSettings:
    """Map eBay workflow Settings to framework-agnostic RecognitionSettings."""
    return RecognitionSettings(
        image_cache_dir=settings.image_cache_dir,
        tesseract_cmd=settings.tesseract_cmd,
        ocr_engine=settings.ocr_engine,
        image_download_timeout_ms=settings.image_download_timeout_ms,
        card_zone_ocr_enabled=settings.card_zone_ocr_enabled,
        card_zone_faiss_enabled=settings.card_zone_faiss_enabled,
        card_zone_align_enabled=settings.card_zone_align_enabled,
        card_set_symbol_match_enabled=settings.card_set_symbol_match_enabled,
        card_set_symbol_min_score=settings.card_set_symbol_min_score,
        card_mana_cost_enabled=settings.card_mana_cost_enabled,
        image_evidence_min_ocr_similarity=settings.image_evidence_min_ocr_similarity,
        image_evidence_min_faiss_score=settings.image_evidence_min_faiss_score,
        image_evidence_min_mana_confidence=settings.image_evidence_min_mana_confidence,
        image_min_region_score=settings.image_min_region_score,
        image_allow_full_frame_fallback=settings.image_allow_full_frame_fallback,
        faiss_index_path=settings.faiss_index_path,
        faiss_top_k=settings.faiss_top_k,
        faiss_index_use_art_zone=settings.faiss_index_use_art_zone,
        openclip_model_name=settings.openclip_model_name,
        torch_device=settings.torch_device,
        embedding_batch_size=settings.embedding_batch_size,
        align_min_confidence=settings.align_min_confidence,
        verify_name_hard_min=settings.verify_name_hard_min,
        verify_name_strong_min=settings.verify_name_strong_min,
        verify_symbol_strong_min=settings.verify_symbol_strong_min,
        faiss_propose_candidates=settings.faiss_propose_candidates,
    )


def coerce_recognition_settings(settings: Settings | RecognitionSettings) -> RecognitionSettings:
    if isinstance(settings, RecognitionSettings):
        return settings
    if isinstance(settings, Settings):
        return recognition_settings_from_app(settings)
    return RecognitionSettings(
        image_cache_dir=getattr(settings, "image_cache_dir", "."),
        tesseract_cmd=getattr(settings, "tesseract_cmd", None),
        ocr_engine=getattr(settings, "ocr_engine", "pytesseract"),
        image_download_timeout_ms=getattr(settings, "image_download_timeout_ms", 20000),
        card_zone_ocr_enabled=getattr(settings, "card_zone_ocr_enabled", True),
        card_zone_faiss_enabled=getattr(settings, "card_zone_faiss_enabled", True),
        card_zone_align_enabled=getattr(settings, "card_zone_align_enabled", True),
        card_set_symbol_match_enabled=getattr(settings, "card_set_symbol_match_enabled", True),
        card_set_symbol_min_score=getattr(settings, "card_set_symbol_min_score", 0.45),
        card_mana_cost_enabled=getattr(settings, "card_mana_cost_enabled", True),
        image_evidence_min_ocr_similarity=getattr(
            settings, "image_evidence_min_ocr_similarity", 0.60
        ),
        image_evidence_min_faiss_score=getattr(settings, "image_evidence_min_faiss_score", 0.55),
        image_evidence_min_mana_confidence=getattr(
            settings, "image_evidence_min_mana_confidence", 0.30
        ),
        image_min_region_score=getattr(settings, "image_min_region_score", 0.55),
        image_allow_full_frame_fallback=getattr(settings, "image_allow_full_frame_fallback", True),
        faiss_index_path=getattr(settings, "faiss_index_path", ""),
        faiss_top_k=getattr(settings, "faiss_top_k", 5),
        faiss_index_use_art_zone=getattr(settings, "faiss_index_use_art_zone", True),
        openclip_model_name=getattr(settings, "openclip_model_name", "ViT-B-32"),
        torch_device=getattr(settings, "torch_device", "cpu"),
        embedding_batch_size=getattr(settings, "embedding_batch_size", 32),
        align_min_confidence=getattr(settings, "align_min_confidence", 0.35),
        verify_name_hard_min=getattr(settings, "verify_name_hard_min", 0.75),
        verify_name_strong_min=getattr(settings, "verify_name_strong_min", 0.88),
        verify_symbol_strong_min=getattr(settings, "verify_symbol_strong_min", 0.55),
        faiss_propose_candidates=getattr(settings, "faiss_propose_candidates", True),
    )
