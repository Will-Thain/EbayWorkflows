"""Shim: OpenCLIP runtime lives in mtg_card_recognition."""

from __future__ import annotations

from mtg_card_recognition.embeddings import openclip as _openclip

from ..adapters.recognition_settings import coerce_recognition_settings
from ..config import Settings

OpenClipRuntime = _openclip.OpenClipRuntime
clear_openclip_cache = _openclip.clear_openclip_cache
clear_openclip_runtime_cache = _openclip.clear_openclip_runtime_cache
normalize_torch_device = _openclip.normalize_torch_device
resolve_torch_device = _openclip.resolve_torch_device


def get_openclip_runtime(settings: Settings) -> OpenClipRuntime:
    return _openclip.get_openclip_runtime(coerce_recognition_settings(settings))


def embed_image_paths(image_paths: list[str], settings: Settings):
    return _openclip.embed_image_paths(image_paths, coerce_recognition_settings(settings))


def embed_image_file(image_path: str, settings: Settings):
    return _openclip.embed_image_file(image_path, coerce_recognition_settings(settings))
