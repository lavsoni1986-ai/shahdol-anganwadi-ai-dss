import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Union


def compute_sha256(file_path: Union[Path, str]) -> str:
    """Computes SHA256 hex digest of a local file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found for SHA256 computation: {path.absolute()}")
    
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def compute_text_sha256(text: str) -> str:
    """Computes SHA256 hex digest of a text string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def utc_timestamp() -> str:
    """Returns ISO 8601 formatted UTC timestamp string."""
    return datetime.now(timezone.utc).isoformat()


def generate_run_id() -> str:
    """Generates a compact timestamp-based run ID (e.g. 20260805T003500Z)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_prompt(prompt_version: str, benchmark_dir: Union[Path, str, None] = None) -> tuple[str, str]:
    """
    Loads prompt text from benchmark/prompts/{prompt_version}.txt
    Returns tuple of (prompt_text, prompt_sha256).
    """
    if benchmark_dir is None:
        base_dir = Path(__file__).parent
    else:
        base_dir = Path(benchmark_dir)
        
    prompt_file = base_dir / "prompts" / f"{prompt_version}.txt"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_file.absolute()}")
    
    prompt_text = prompt_file.read_text(encoding="utf-8").strip()
    prompt_sha256 = compute_text_sha256(prompt_text)
    return prompt_text, prompt_sha256
