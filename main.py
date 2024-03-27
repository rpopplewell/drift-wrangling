import json

from solana.rpc.async_api import AsyncClient
import asyncio
from driftpy.constants import PRICE_PRECISION
from anchorpy import Wallet
from driftpy.drift_client import DriftClient
from driftpy.drift_user import DriftUser
import driftpy.types as dptypes
from driftpy.keypair import load_keypair
from marketclient import MarketClient

ETH_PERP_MARKET_INDEX = 2
BTC_PERP_MARKET_INDEX = 1


class Client:
    drift_client: DriftClient
    drift_user: DriftUser
    market_client: MarketClient

    def __init__(self):
        pass

    async def create(self):
        with open("secrets.json", "r") as file:
            data = json.load(file)

        secret = data["PRIVATE_KEY"]
        rpc_url = data["RPC_URL"]
        dlob_url = data["REMOTE_DLOB_URL"]

        self.market_client = MarketClient(dlob_url)

        self.drift_client = DriftClient(
            AsyncClient(rpc_url),
            Wallet(load_keypair(secret)),
            "mainnet",
            tx_params=dptypes.TxParams(
                compute_units=1_000_000,
                compute_units_price=100_000,
            ),
        )
        await self.drift_client.add_user(0)
        await self.drift_client.subscribe()
        self.drift_user = self.drift_client.get_user()
        await self.drift_user.account_subscriber.fetch()

        return self

    async def getMarketPrices(self) -> tuple[float, float]:
        btc_price, eth_price = await asyncio.gather(
            self.market_client.getMarketPrice("BTC-PERP"),
            self.market_client.getMarketPrice("ETH-PERP"),
        )
        return btc_price, eth_price

    def getBalance(
        self,
    ):
        return self.drift_user.get_free_collateral() / PRICE_PRECISION

    def getPositions(
        self,
    ) -> tuple[float, float]:
        # IS LONG IF pos.base_asset_amount > 0, short if < 0
        positions = self.drift_user.get_active_perp_positions()
        for pos in positions:
            return (pos.base_asset_amount, pos.quote_asset_amount)

    async def setPosition(
        self, market_index: int, size: float, direction: dptypes.PositionDirection
    ) -> None:
        size_int = self.drift_client.convert_to_perp_precision(size)
        order = dptypes.OrderParams(
            order_type=dptypes.OrderType.Market,
            base_asset_amount=size_int,
            market_index=market_index,
            direction=direction,
        )
        order.set_perp()
        sig = await self.drift_client.place_perp_order(order)

        print(sig)

    async def closePosition(self, market_index: int) -> None:
        user_acc = self.drift_user.get_user_account()
        drift_pub_key = self.drift_client.get_user_account_public_key(0)
        sig = await self.drift_client.settle_pnl(drift_pub_key, user_acc, market_index)

        print(sig)


async def main():
    cli = Client()
    await cli.create()
    amount_to_buy_in_dollars = 10
    btc_price, eth_price = await cli.getMarketPrices()
    amount_to_buy_in_eth = amount_to_buy_in_dollars / eth_price

    # await cli.setPosition(
    #     ETH_PERP_MARKET_INDEX,
    #     amount_to_buy_in_eth,
    #     dptypes.PositionDirection.Long,
    # )

    # balance = cli.getBalance()
    # print(balance)
    positions = cli.getPositions()
    print(positions)

    await cli.closePosition(ETH_PERP_MARKET_INDEX)

    positions = cli.getPositions()
    print(positions)

    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
