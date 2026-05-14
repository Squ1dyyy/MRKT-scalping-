from dataclasses import dataclass
from enum import Flag, auto
from typing import Optional


class Role(Flag):
	SCANNER = auto()  # read-only: feed, collections, listings
	ORDERER = auto()  # create/cancel buy orders
	OFFERER = auto()  # create/cancel offers
	BUYER = auto()    # buy_gift (instant purchase)
	SELLER = auto()   # put gifts on sale
	WALLET = auto()   # balance, history, activities


@dataclass(frozen=True)
class AccountConfig:
	name: str
	auth_token: str
	roles: Role
	proxy: Optional[str] = None
	rate_limit_rps: float = 2.0
	user_agent: Optional[str] = None
	cf_impersonate: str = "chrome"

	def has_role(self, role: Role) -> bool:
		return bool(self.roles & role)
