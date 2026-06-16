"""기관별 collector 레지스트리.

각 모듈은 collect(limit) -> list[dict] 를 구현.
"""
from . import adb, afdb, aiib, edcf, jica, koica, worldbank

REGISTRY = {
    "wb": worldbank.collect,
    "adb": adb.collect,
    "afdb": afdb.collect,
    "aiib": aiib.collect,
    "koica": koica.collect,
    "edcf": edcf.collect,
    "jica": jica.collect,
}

ALL_SOURCES = list(REGISTRY.keys())
