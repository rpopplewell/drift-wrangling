import aiohttp
from driftpy.constants import PRICE_PRECISION
import json
import asyncio


ETH_PERP = "ETH-PERP"
BTC_PERP = "BTC-PERP"


class MarketClient:
    def __init__(self, url):
        self.url = url

    async def get(self, params):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(self.url, params=params) as resp:
                    if resp.status == 200:
                        res = json.loads(await resp.text())
                        return res  # Properly await the json parsing
                    else:
                        print(f"Failed to retrieve data: {resp.status}")
            except Exception as e:
                print(f"An error occurred: {e}")
                return None

    async def getMarketPrice(self, market_name: str):
        params = {"marketName": market_name, "depth": 1}
        resp = await self.get(params)
        if resp is not None:
            bid_price = resp["bids"][0]["price"]
            ask_price = resp["asks"][0]["price"]
            mean_price = ((int(bid_price) + int(ask_price)) / 2) / PRICE_PRECISION
            return mean_price
        else:
            # Handle the case where resp is None
            print("Failed to get market price.")
            return None

    async def getMarketPrices(self) -> list[float]:
        btc_price, eth_price = await asyncio.gather(
            self.getMarketPrice(BTC_PERP),
            self.getMarketPrice(ETH_PERP),
        )
        return [btc_price, eth_price]
