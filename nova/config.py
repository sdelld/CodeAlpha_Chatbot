"""Settings from environment variables (.env is loaded automatically; see .env.example)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # python-dotenv is optional
    pass


def _f(name, default):
    return float(os.environ.get(name, default))


class Settings:
    def __init__(self):
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.engine = os.environ.get("NOVA_ENGINE", "auto")  # auto | gemini | local
        self.chat_model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
        self.judge_model = os.environ.get("GEMINI_JUDGE_MODEL", "gemini-3.6-flash")
        self.embedding_model = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self.use_embeddings = os.environ.get("NOVA_EMBEDDINGS", "1") == "1"
        # USD per 1M tokens at paid-tier prices (free tier costs $0; this estimates production cost).
        self.price_in = _f("PRICE_INPUT_PER_MTOK", "0.30")
        self.price_out = _f("PRICE_OUTPUT_PER_MTOK", "2.50")
        self.timeout_s = _f("LLM_TIMEOUT_SECONDS", "25")
        self.max_retries = int(os.environ.get("LLM_MAX_RETRIES", "3"))
        self.max_tool_rounds = int(os.environ.get("MAX_TOOL_ROUNDS", "4"))
        self.history_turns = int(os.environ.get("HISTORY_TURNS", "6"))
        self.session_ttl_s = int(os.environ.get("SESSION_TTL_SECONDS", "3600"))
        self.answer_cache_ttl_s = int(os.environ.get("ANSWER_CACHE_TTL_SECONDS", "600"))
        self.data_dir = Path(os.environ.get("NOVA_DATA_DIR", ROOT / "data"))
        self.cache_dir = Path(os.environ.get("NOVA_CACHE_DIR", self.data_dir / "cache"))
        self.log_dir = Path(os.environ.get("LOG_DIR", ROOT / "logs"))

    @property
    def gemini_enabled(self):
        return bool(self.gemini_api_key) and self.engine in ("auto", "gemini")


settings = Settings()
