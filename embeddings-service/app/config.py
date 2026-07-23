from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Bearer token required on every request. Empty disables auth checking —
    # only acceptable for local dev; set this in any deployed environment
    # (matches backend/.env's EMBEDDINGS_API_KEY value).
    embeddings_api_key: str = ""

    # Must match scripts/seed/04_embed.py's EMBED_MODEL_ID exactly, or query
    # vectors and the seeded passage vectors in document_chunks land in
    # different embedding spaces and cosine similarity becomes meaningless.
    embed_model_id: str = "intfloat/multilingual-e5-base"
    embed_max_length: int = 512
    embed_max_batch: int = 32


@lru_cache
def get_settings() -> Settings:
    return Settings()
