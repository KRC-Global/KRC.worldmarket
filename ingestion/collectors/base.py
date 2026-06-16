"""collector 공통 인터페이스.

각 기관 모듈은 `collect(limit: int) -> list[dict]` 를 구현한다.
반환 dict 는 normalize.normalize() 출력(= notices 행)이어야 한다.
"""
from __future__ import annotations

import requests

USER_AGENT = "balju-gonggo-bot/0.1 (+agriculture MDB tender aggregator)"
TIMEOUT = 30


def http_get(url: str, **kwargs) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    r = requests.get(url, headers=headers, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r
