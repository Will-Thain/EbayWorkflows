from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ebay_workflows.services.openclip_runtime import (
    clear_openclip_runtime_cache,
    embed_image_paths,
    get_openclip_runtime,
    normalize_torch_device,
    resolve_torch_device,
)


def test_normalize_torch_device_accepts_supported_values() -> None:
    assert normalize_torch_device("cpu") == "cpu"
    assert normalize_torch_device(" CUDA ") == "cuda"
    assert normalize_torch_device("DirectML") == "directml"


def test_normalize_torch_device_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unsupported TORCH_DEVICE"):
        normalize_torch_device("metal")


def test_resolve_torch_device_cpu() -> None:
    torch_module = MagicMock()
    torch_module.device.return_value = "cpu-device"
    assert resolve_torch_device(torch_module, "cpu") == "cpu-device"


def test_get_openclip_runtime_uses_cache() -> None:
    clear_openclip_runtime_cache()
    settings = SimpleNamespace(openclip_model_name="ViT-B-32", torch_device="cpu")
    fake_model = MagicMock()
    fake_preprocess = MagicMock()

    with patch("open_clip.create_model_and_transforms", return_value=(fake_model, None, fake_preprocess)) as create_mock:
        with patch("ebay_workflows.services.openclip_runtime.resolve_torch_device", return_value=MagicMock()):
            first = get_openclip_runtime(settings)  # type: ignore[arg-type]
            second = get_openclip_runtime(settings)  # type: ignore[arg-type]

    assert first is second
    create_mock.assert_called_once()
    fake_model.eval.assert_called_once()
    fake_model.to.assert_called_once()


def test_embed_image_paths_empty() -> None:
    settings = SimpleNamespace(embedding_batch_size=8)
    result = embed_image_paths([], settings)  # type: ignore[arg-type]
    assert result.shape == (0, 0)
