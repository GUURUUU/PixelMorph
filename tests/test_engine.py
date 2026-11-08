"""
Engine-level tests. NOTE: FaceEngine raises FileNotFoundError at import time
when no swapper models are on disk — that behavior is part of the contract
being tested here.
"""
import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _load_engine_module():
    import app.face_engine as fe
    importlib.reload(fe)
    return fe


def test_engine_model_contract():
    try:
        fe = _load_engine_module()
    except FileNotFoundError as e:
        # no-models environment: the error must guide the user to the fix
        assert "download_models.py" in str(e.value)
        assert "onnx" in str(e.value)
        pytest.skip("no models on disk (CI default); error-raise contract verified")
    assert fe.MODEL_FILES, "engine must expose at least one resolved model"
    assert set(fe.MODEL_CONFIGS) == set(fe.MODEL_FILES), \
        "MODEL_CONFIGS must mirror MODEL_FILES"
    for name, path in fe.MODEL_FILES.items():
        path_obj = Path(path)
        assert path_obj.exists(), f"{name} resolved to missing path: {path}"


def test_engine_api_shape():
    try:
        fe = _load_engine_module()
    except FileNotFoundError:
        pytest.skip("no models on disk")
    engine = fe.FaceEngine()
    assert engine.available_models, "engine must expose at least one model"
    assert callable(engine.detect_faces)
    assert callable(engine.swap_image_file)
    assert callable(engine.prepare_embedding)
