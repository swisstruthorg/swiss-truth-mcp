from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "swisstruth2026"

    anthropic_api_key: str = ""
    swiss_truth_api_key: str = "dev-key-change-in-prod"

    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # Confidence threshold for certified claims returned in search
    default_min_confidence: float = 0.8

    # TTL in days for certified claims before re-review is recommended
    default_ttl_days: int = 365

    # n8n webhook — wenn gesetzt, wird bei Claim-Zertifizierung ein Event gesendet
    n8n_webhook_url: str = ""

    # Auth — JWT Secret Key (in Produktion unbedingt in .env setzen!)
    secret_key: str = "dev-secret-key-change-in-production-please"

    # Öffentliche Basis-URL (ngrok oder Produktions-Domain)
    # Wird in check_url / review_url verwendet damit n8n die API erreichen kann
    ngrok_public_url: str = ""

    @property
    def public_base_url(self) -> str:
        """Gibt die öffentlich erreichbare Basis-URL zurück."""
        return self.ngrok_public_url.rstrip("/") or "http://127.0.0.1:8001"


settings = Settings()
