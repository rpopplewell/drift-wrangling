import json

from solana.rpc.async_api import AsyncClient
import asyncio
from driftpy.constants import PRICE_PRECISION, BASE_PRECISION
from anchorpy import Wallet
from driftpy.drift_client import DriftClient
from driftpy.drift_user import DriftUser
import driftpy.types as dptypes
from driftpy.keypair import load_keypair
from marketclient import MarketClient
import time
from solana.rpc.core import RPCException, UnconfirmedTxError

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
                compute_units=1_400_000,
                compute_units_price=1_600_000,
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
    ) -> list[dptypes.PerpPosition]:
        positions = self.drift_user.get_active_perp_positions()
        for pos in positions:
            if pos.base_asset_amount == 0:
                positions.remove(pos)

        return positions

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
        sig = None
        while sig == None:
            try:
                sig = await self.drift_client.place_perp_order(order)
            except (RPCException, UnconfirmedTxError):
                print("failed tx")

        print(sig)

    async def closePosition(self, pos: dptypes.PerpPosition) -> None:
        if pos.base_asset_amount > 0:
            direction = dptypes.PositionDirection.Short
        else:
            direction = dptypes.PositionDirection.Long

        order = dptypes.OrderParams(
            order_type=dptypes.OrderType.Market,
            base_asset_amount=pos.base_asset_amount,
            reduce_only=True,
            market_index=pos.market_index,
            direction=direction,
        )
        order.set_perp()
        sig = None
        while sig == None:
            try:
                sig = await self.drift_client.place_perp_order(order)
            except (RPCException, UnconfirmedTxError):
                print("failed tx")

        print(sig)

    async def closeAllPositions(self, positions: list[dptypes.PerpPosition]) -> None:
        for pos in positions:
            await self.closePosition(pos)

    def getPositionsState(self) -> tuple[float, float]:
        positionState = ()
        positions = self.getPositions()
        for pos in positions:
            if pos.market_index == BTC_PERP_MARKET_INDEX:
                positionState[0] = pos.base_asset_amount / BASE_PRECISION
            if pos.market_index == ETH_PERP_MARKET_INDEX:
                positionState[1] = pos.base_asset_amount / BASE_PRECISION

        return positionState

    # position state: (btc_base_amount, eth_base_amount)
    async def updatePositionState(self, newPositionState: tuple[float]):
        oldPositionState = self.getPositionsState()
        deltaPosition = [x[0] - x[1] for x in zip(newPositionState, oldPositionState)]
        for i, pos in enumerate(deltaPosition):
            if i == 0:
                marketindex = BTC_PERP_MARKET_INDEX
            elif i == 1:
                marketindex = ETH_PERP_MARKET_INDEX
            if pos >= 0:
                direction = dptypes.PositionDirection.Long
            elif pos < 0:
                direction = dptypes.PositionDirection.Short

            self.setPosition(marketindex, pos, direction)


async def main():
    cli = Client()
    await cli.create()
    amount_to_buy_in_dollars = 10
    import time

    start_time = time.time()
    btc_price, eth_price = await cli.getMarketPrices()
    print("--- %s seconds ---" % (time.time() - start_time))
    amount_to_buy_in_eth = amount_to_buy_in_dollars / eth_price

    print("START")

    await cli.setPosition(
        ETH_PERP_MARKET_INDEX,
        amount_to_buy_in_eth,
        dptypes.PositionDirection.Long,
    )
    time.sleep(10)

    positions = cli.getPositions()
    print(positions)

    await cli.closeAllPositions(positions)

    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
