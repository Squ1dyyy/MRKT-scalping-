from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Telegram
    bot_token: str
    bot_chat_id: int = -0
    bot_channel: str = ""

    # Portals
    auth_portals: Optional[str] = None
    skip_portals: bool = False

    # Trading parameters
    convert_usdt: float = 1.8
    profit_percent: float = 0.15
    profit_percent_offer: float = 0.10
    min_price_ton: float = 1.0
    max_price_ton: float = 2000.0
    max_price_offer_ton: float = 500.0
    max_collection_stock: int = 3
    overstock_discount: float = 0.05
    portals_commission: float = 0.95
    offer_expire_minutes: int = 3
    order_up_price_nano: int = 1

    # Runtime
    time_sleep: int = 60
    black_list: List[str] = Field(default_factory=lambda: ["kissed frog"])

    # Files
    accounts_file: str = "accounts.yaml"
    session_file: str = "session.txt"
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/mrkt.log"

    @property
    def base_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent.parent

    def current_session(self) -> int:
        p = self.base_dir / self.session_file
        try:
            return int(p.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def increment_session(self) -> int:
        n = self.current_session() + 1
        p = self.base_dir / self.session_file
        p.write_text(str(n))
        return n
