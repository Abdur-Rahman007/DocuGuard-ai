"""Runtime feature detection for optional, server-local Ollama.

Cloud Streamlit servers cannot access the developer's own Windows Ollama service.
Return False quickly in that case rather than displaying a button that will fail.
"""
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def local_ollama_available(timeout: float = 0.5) -> bool:
    """Check the fixed loopback Ollama endpoint, without accepting external URLs."""
    try:
        with urlopen("http://127.0.0.1:11434/api/version", timeout=timeout) as response:
            return response.status == 200
    except (HTTPError, URLError, TimeoutError, OSError, ValueError):
        return False
