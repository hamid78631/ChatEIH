"""Configuration centralisée, lue depuis le fichier .env à la racine du projet."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Racine du dépôt : backend/app/config.py -> ../../
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # LLM
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # Embeddings
    embedding_model: str = "intfloat/multilingual-e5-small"

    # Chemins (relatifs à la racine du dépôt)
    corpus_dir: Path = Path("data/corpus")
    chroma_dir: Path = Path("data/chroma")
    chroma_collection: str = "eih"

    # Découpage
    chunk_strategy: Literal["fixed", "structural"] = "structural"
    chunk_size: int = 500
    chunk_overlap: int = 100

    # Recherche / génération
    top_k: int = 5
    score_threshold: float = 0.78

    # CORS (liste séparée par des virgules)
    cors_origins: str = "http://localhost:5173"

    @property
    def corpus_path(self) -> Path:
        return ROOT_DIR / self.corpus_dir

    @property
    def chroma_path(self) -> Path:
        return ROOT_DIR / self.chroma_dir


@lru_cache
def get_settings() -> Settings:
    return Settings()
