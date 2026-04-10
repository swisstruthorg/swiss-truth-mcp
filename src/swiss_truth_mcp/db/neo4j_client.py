from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from typing import Optional
from neo4j import AsyncGraphDatabase, AsyncDriver

from swiss_truth_mcp.config import settings

_driver: Optional[AsyncDriver] = None


def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


async def close_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


@asynccontextmanager
async def get_session() -> AsyncGenerator:
    driver = get_driver()
    async with driver.session() as session:
        yield session
