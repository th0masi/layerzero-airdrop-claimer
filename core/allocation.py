import uuid
import random
import aiohttp
from typing import List

from fake_useragent import UserAgent
from aiohttp import ClientTimeout
from aiohttp_socks import ProxyConnector
from better_proxy import Proxy
from loguru import logger


class Allocation:
    def __init__(self, wallet: str, proxies: List[str]):
        self.wallet = wallet
        self.proxies = proxies
        self.api_url = (
            f'https://www.layerzero.foundation/'
            f'api/allocation/{self.wallet}'
        )

    async def get_headers(self):
        ua = UserAgent()
        return {
            "Content-Type": 'application/json',
            "User-Agent": ua.random,
            "referer": self.api_url,
            "baggage": (
                f"sentry-environment=vercel-production,"
                f"sentry-release=8db980a63760b2e079aa1e8cc36420b60474005a,"
                f"sentry-public_key=7ea9fec73d6d676df2ec73f61f6d88f0,"
                f"sentry-trace_id={uuid.uuid4()}"
            )
        }

    async def send_request(self, method: str, url: str):
        headers = await self.get_headers()
        timeout = ClientTimeout(total=10)

        if not self.proxies:
            async with aiohttp.ClientSession(
                    timeout=timeout
            ) as session:
                async with session.request(
                        method,
                        url,
                        headers=headers
                ) as response:
                    return await response.json()

        random.shuffle(self.proxies)

        for proxy in self.proxies:
            proxy = Proxy.from_str(proxy)
            connector = ProxyConnector.from_url(proxy.as_url)

            async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout
            ) as session:
                try:
                    async with session.request(
                            method,
                            url,
                            headers=headers
                    ) as response:
                        return await response.json()
                except Exception:
                    continue

    async def get_allocation(self, response=None):
        try:
            response = await self.send_request('GET', self.api_url)
        except Exception as e:
            logger.error(
                f'{self.wallet} | Ошибка в запросе: {e}'
            )

        zro_amount = response.get(
            'zroAllocation', {}
        ).get(
            'asString', None
        )

        if zro_amount is None:
            logger.error(
                f'{self.wallet} | Ошибка в запросе, ответ: {response}'
            )

        return zro_amount
