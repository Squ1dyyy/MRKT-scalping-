from typing import List

import yaml

from pool.account import AccountConfig, Role


def load_accounts(path: str) -> List[AccountConfig]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    accounts: List[AccountConfig] = []
    for raw in data.get("accounts", []):
        roles = Role(0)
        for r in raw.get("roles", []):
            try:
                roles |= Role[r.upper()]
            except KeyError as exc:
                raise ValueError(f"Unknown role '{r}' in accounts.yaml") from exc

        accounts.append(
            AccountConfig(
                name=raw["name"],
                auth_token=raw["auth_token"],
                roles=roles,
                proxy=raw.get("proxy"),
                rate_limit_rps=float(raw.get("rate_limit_rps", 2.0)),
                user_agent=raw.get("user_agent"),
                cf_impersonate=raw.get("cf_impersonate", "chrome"),
            )
        )

    if not accounts:
        raise ValueError("accounts.yaml contains no accounts")

    return accounts
