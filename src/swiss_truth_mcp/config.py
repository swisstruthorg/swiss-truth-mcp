from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "swisstruth2026"

    anthropic_api_key: str = ""
    anthropic_base_url: str = ""   # z.B. https://open-claude.com/v1 (leer = Standard api.anthropic.com)
    swiss_truth_api_key: str = "dev-key-change-in-prod"

    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # Confidence threshold for certified claims returned in search
    default_min_confidence: float = 0.8

    # TTL in days for certified claims before re-review is recommended
    default_ttl_days: int = 365

    # n8n webhook — wenn gesetzt, wird bei Claim-Zertifizierung ein Event gesendet
    n8n_webhook_url: str = ""

    # Anthropic API Timeout in Sekunden (verhindert Hänger bei API-Outage)
    anthropic_timeout_seconds: int = 30

    # Auth — JWT Secret Key (in Produktion unbedingt in .env setzen!)
    secret_key: str = "dev-secret-key-change-in-production-please"

    # Öffentliche Basis-URL (ngrok lokal ODER PUBLIC_BASE_URL in Produktion)
    ngrok_public_url: str = ""
    public_base_url_env: str = Field(default="", validation_alias="PUBLIC_BASE_URL")

    # Blockchain-Anchoring (Ethereum / Polygon / Base ...)
    eth_rpc_url: str = ""            # z.B. https://polygon-rpc.com
    eth_private_key: str = ""        # 0x... Wallet Private Key
    eth_chain_id: int = 137          # 137=Polygon, 1=Mainnet, 8453=Base
    eth_chain_name: str = "polygon"  # Anzeigebezeichnung

    @property
    def public_base_url(self) -> str:
        """Gibt die öffentlich erreichbare Basis-URL zurück.
        Priorität: NGROK_PUBLIC_URL → PUBLIC_BASE_URL → localhost-Fallback"""
        return (
            self.ngrok_public_url.rstrip("/")
            or self.public_base_url_env.rstrip("/")
            or "http://127.0.0.1:8001"
        )


settings = Settings()
