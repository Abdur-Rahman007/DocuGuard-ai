"""Phase 5: deployment feature gate and release-shape smoke tests."""
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch

from docuguard.config import PROJECT_ROOT, sample_pdfs
from docuguard.deployment import local_ollama_available


def test_local_ollama_available_success():
    class FakeResponse:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): return False
    with patch("docuguard.deployment.urlopen", return_value=FakeResponse()) as fn:
        assert local_ollama_available() is True
        assert fn.call_args.args[0] == "http://127.0.0.1:11434/api/version"


def test_local_ollama_unavailable_is_safe():
    with patch("docuguard.deployment.urlopen", side_effect=URLError("not running")):
        assert local_ollama_available() is False


def test_release_has_sample_data_and_app():
    assert (PROJECT_ROOT / "app.py").is_file()
    assert (PROJECT_ROOT / "requirements.txt").is_file()
    assert (PROJECT_ROOT / "sample-data/engineer/task1-procurement/purchase-request.csv").is_file()
    assert len(sample_pdfs()) == 10
