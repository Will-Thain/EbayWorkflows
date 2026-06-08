from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import numpy as np

from ..config import RecognitionSettings

_RUNTIME_LOCK = threading.Lock()
_INFERENCE_LOCK = threading.Lock()
_RUNTIME_CACHE: dict[tuple[str, str], OpenClipRuntime] = {}


@dataclass(frozen=True, slots=True)
class OpenClipRuntime:
    """Cached OpenCLIP model, preprocess pipeline, and torch device."""

    model_name: str
    device_label: str
    model: Any
    preprocess: Any
    torch: Any
    device: Any


def normalize_torch_device(device: str) -> str:
    """Return a supported device label."""
    label = device.strip().lower()
    if label in {"cpu", "cuda", "directml"}:
        return label
    raise ValueError(f"Unsupported TORCH_DEVICE '{device}'. Use cpu, cuda, or directml.")


def resolve_torch_device(torch_module: Any, device_label: str) -> Any:
    """Resolve a torch device object from a normalized device label."""
    if device_label == "cpu":
        return torch_module.device("cpu")
    if device_label == "cuda":
        if not torch_module.cuda.is_available():
            raise ValueError("TORCH_DEVICE=cuda but CUDA is not available.")
        return torch_module.device("cuda")
    if device_label == "directml":
        try:
            import torch_directml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ValueError(
                "TORCH_DEVICE=directml requires torch-directml. Install with: pip install torch-directml"
            ) from exc
        return torch_directml.device()
    raise ValueError(f"Unsupported TORCH_DEVICE '{device_label}'.")


def get_openclip_runtime(settings: RecognitionSettings) -> OpenClipRuntime:
    """Return a cached OpenCLIP runtime for the configured model and device."""
    import open_clip  # type: ignore[import-not-found]
    import torch  # type: ignore[import-not-found]

    device_label = normalize_torch_device(settings.torch_device)
    cache_key = (settings.openclip_model_name, device_label)
    cached = _RUNTIME_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with _RUNTIME_LOCK:
        cached = _RUNTIME_CACHE.get(cache_key)
        if cached is not None:
            return cached

        device = resolve_torch_device(torch, device_label)
        model, _, preprocess = open_clip.create_model_and_transforms(
            settings.openclip_model_name,
            pretrained="openai",
            force_quick_gelu=True,
        )
        model.eval()
        model.to(device)
        runtime = OpenClipRuntime(
            model_name=settings.openclip_model_name,
            device_label=device_label,
            model=model,
            preprocess=preprocess,
            torch=torch,
            device=device,
        )
        _RUNTIME_CACHE[cache_key] = runtime
        return runtime


def clear_openclip_runtime_cache() -> None:
    """Clear cached OpenCLIP runtimes (for tests)."""
    with _RUNTIME_LOCK:
        _RUNTIME_CACHE.clear()


clear_openclip_cache = clear_openclip_runtime_cache


def embed_image_paths(image_paths: list[str], settings: RecognitionSettings) -> np.ndarray:
    """Embed one or more local image paths; returns shape (N, dimension)."""
    if not image_paths:
        return np.empty((0, 0), dtype=np.float32)

    from PIL import Image  # type: ignore[import-not-found]

    runtime = get_openclip_runtime(settings)
    batch_size = max(1, settings.embedding_batch_size)
    outputs: list[np.ndarray] = []

    with _INFERENCE_LOCK:
        for start in range(0, len(image_paths), batch_size):
            chunk = image_paths[start : start + batch_size]
            tensors = [
                runtime.preprocess(Image.open(path).convert("RGB"))
                for path in chunk
            ]
            batch = runtime.torch.stack(tensors).to(runtime.device)
            with runtime.torch.no_grad():
                features = runtime.model.encode_image(batch)
                features = features / features.norm(dim=-1, keepdim=True)
            outputs.append(features.detach().cpu().numpy().astype(np.float32))

    return np.vstack(outputs)


def embed_image_file(image_path: str, settings: RecognitionSettings) -> np.ndarray:
    """Embed a single image path; returns shape (1, dimension)."""
    return embed_image_paths([image_path], settings)
