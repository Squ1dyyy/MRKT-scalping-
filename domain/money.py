from typing import NewType

Nano = NewType("Nano", int)
Ton = NewType("Ton", float)


def nano_to_ton(nano: int) -> float:
    return round(nano / 1e9, 3)


def ton_to_nano(ton: float) -> int:
    return round(ton * 1e9)
