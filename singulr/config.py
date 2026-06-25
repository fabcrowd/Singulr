"""Application configuration from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


VERIFICATION_SENTENCE = (
    "Welcome to Singulr! I confirm that I am joining as myself, with 1 account only. "
    "I agree to the rules and will keep this account secure."
)


class Settings(BaseSettings):
    """Runtime settings loaded from `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    channel_id: int = 0
    log_channel_id: int = 0
    public_base_url: str = "http://localhost:8000"

    fingerprint_public_key: str = ""
    fingerprint_secret_key: str = ""

    database_url: str = "sqlite+aiosqlite:///./singulr.db"

    chain_rpc: str = "https://rpc.telcoin.network"
    chain_id: int = 2017
    chain_explorer: str = "https://telscan.io"
    contract_address: str = ""
    wallet_private_key: str = ""

    token_expiry_minutes: int = 10
    watcher_interval_minutes: int = 60
    keystroke_similarity_threshold: float = 0.85
    stylometry_similarity_threshold: float = 0.80
    ban_evasion_auto_deny_threshold: float = 0.92
    local_similarity_flag_threshold: float = 0.85
    default_security_preset: str = "balanced"
    default_network_registry_mode: str = "read"
    ban_decay_months: int = 6
    social_profile_provider: str = "none"
    mock_social_hard_user_ids: str = ""
    mock_social_soft_user_ids: str = ""

    trusted_channel_ids: str = ""

    admin_api_key: str = ""
    admin_telegram_id: int = 0
    admin_ops_chat_id: int = 0
    log_json: bool = False
    verify_rate_limit_per_minute: int = 30

    @property
    def chain_enabled(self) -> bool:
        """True when blockchain integration is configured."""
        return bool(self.contract_address and self.wallet_private_key)

    @property
    def bot_configured(self) -> bool:
        """True when Telegram bot token is set."""
        return bool(self.bot_token)

    @property
    def trusted_channel_id_list(self) -> list[int]:
        """Parsed TRUSTED_CHANNEL_IDS comma-separated list."""
        if not self.trusted_channel_ids.strip():
            return []
        return [int(part.strip()) for part in self.trusted_channel_ids.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
