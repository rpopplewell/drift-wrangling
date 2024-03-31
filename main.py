import json

from solana.rpc.async_api import AsyncClient
from solders.signature import Signature
from solders.rpc.responses import GetTransactionResp
import re
from solana.rpc.api import Client as SolClient
from driftpy.constants import PRICE_PRECISION, BASE_PRECISION
from solana.rpc.core import RPCException, UnconfirmedTxError
from driftpy.drift_client import DriftClient
from driftpy.drift_user import DriftUser
import driftpy.types as dptypes
from driftpy.keypair import load_keypair
from marketclient import MarketClient
from anchorpy import Wallet
import time
import asyncio

ETH_PERP_MARKET_INDEX = 2
BTC_PERP_MARKET_INDEX = 1
STRING_TO_CHECK = "Program dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH"


class Client:
    drift_client: DriftClient
    drift_user: DriftUser
    market_client: MarketClient
    sol_client: SolClient

    def __init__(self):
        pass

    async def create(self):
        with open("secrets.json", "r") as file:
            data = json.load(file)

        secret = data["PRIVATE_KEY"]
        rpc_url = data["RPC_URL"]
        dlob_url = data["REMOTE_DLOB_URL"]

        self.sol_client = SolClient(rpc_url)

        self.market_client = MarketClient(dlob_url)

        self.drift_client = DriftClient(
            AsyncClient(rpc_url),
            Wallet(load_keypair(secret)),
            "mainnet",
            tx_params=dptypes.TxParams(
                compute_units=2_000_000,
                compute_units_price=7_000_000,
            ),
        )
        await self.drift_client.add_user(0)
        await self.drift_client.subscribe()
        self.drift_user = self.drift_client.get_user()
        await self.drift_user.account_subscriber.fetch()

        return self

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
            except RPCException as e:
                if "Order Amount Too Small" in str(e) or "0x17ab" in str(e):
                    print("Order amount too small, skipping...")
                    break
                elif "Blockhash not found" in str(e):
                    print("blockhash not found")
            except UnconfirmedTxError as e:
                tx_sig = str(e).split(" ")[-1]
                print()
                ok = self.CheckTx(tx_sig)
                if ok:
                    break

        if sig:
            print(sig)

    async def closePosition(self, pos: dptypes.PerpPosition) -> None:
        if pos.base_asset_amount > 0:
            direction = dptypes.PositionDirection.Short
        else:
            direction = dptypes.PositionDirection.Long

        order = dptypes.OrderParams(
            order_type=dptypes.OrderType.Market,
            base_asset_amount=abs(pos.base_asset_amount),
            reduce_only=True,
            market_index=pos.market_index,
            direction=direction,
        )
        order.set_perp()
        sig = None
        while sig == None:
            try:
                sig = await self.drift_client.place_perp_order(order)
            except (RPCException, UnconfirmedTxError) as e:
                print("failed tx: " + str(e))

        print(sig)

    async def closeAllPositions(self, positions: list[dptypes.PerpPosition]) -> None:
        for pos in positions:
            await self.closePosition(pos)

    def getPositionState(self) -> tuple[float, float]:
        positions = self.getPositions()
        btc_amount = 0
        eth_amount = 0
        for pos in positions:
            if pos.market_index == BTC_PERP_MARKET_INDEX:
                btc_amount = pos.base_asset_amount / BASE_PRECISION
            if pos.market_index == ETH_PERP_MARKET_INDEX:
                eth_amount = pos.base_asset_amount / BASE_PRECISION

        return btc_amount, eth_amount

    # position state: (btc_base_amount, eth_base_amount)
    async def updatePositionState(self, newPositionState: tuple[float]):
        oldPositionState = self.getPositionState()
        deltaPosition = [x[0] - x[1] for x in zip(newPositionState, oldPositionState)]
        calls = []

        for i, pos in enumerate(deltaPosition):
            if i == 0:
                marketindex = BTC_PERP_MARKET_INDEX
            elif i == 1:
                marketindex = ETH_PERP_MARKET_INDEX

            if pos >= 0:
                direction = dptypes.PositionDirection.Long
            elif pos < 0:
                direction = dptypes.PositionDirection.Short

            call = self.setPosition(marketindex, abs(pos), direction)
            calls.append(call)

        await asyncio.gather(*calls)

    async def sendTx(self, func, order):
        sig = None
        while sig == None:
            try:
                sig = await func(order)
            except RPCException as e:
                if "Order Amount Too Small" in str(e) or "0x17ab" in str(e):
                    print("Order amount too small, skipping...")
                    break
                else:
                    print("failed tx: " + str(e))
            except UnconfirmedTxError as e:
                tx_sig = str(e).split(" ")[-1]
                print()
                ok = self.CheckTx(tx_sig)
                if ok:
                    break
                else:
                    print("failed tx: " + str(e))

        if sig:
            print(sig)

    def CheckTx(self, sig: str):
        tx_sig = Signature.from_string(sig)
        res: GetTransactionResp = None
        for i in range(1, 10):
            try:
                res = self.sol_client.get_transaction(
                    tx_sig, max_supported_transaction_version=0
                )
            except Exception as e:
                print(f"Error: Can't verify tx Exception: {e}")
                pass
            if res is not None:
                my_regex = STRING_TO_CHECK + " success"
                match = re.search(my_regex, res.to_json())
                if match:
                    print(f"Tx succeeded")
                    return True
                else:
                    print(f"Tx failed")
                    return False

            time.sleep(2)

        print(f"Tx not confirmed")
        return False


async def main():
    cli = Client()
    await cli.create()
    amount_to_buy_in_dollars = 10
    import time

    start_time = time.time()
    btc_price, eth_price = await cli.market_client.getMarketPrices()
    print("--- %s seconds ---" % (time.time() - start_time))
    amount_to_buy_in_eth = amount_to_buy_in_dollars / eth_price
    amount_to_buy_in_btc = amount_to_buy_in_dollars / btc_price

    print("START")

    new_pos_state = (amount_to_buy_in_btc, -amount_to_buy_in_eth)
    print("NEW POS STATE: ", new_pos_state)
    await cli.updatePositionState(new_pos_state)

    # await cli.closeAllPositions()

    # positions = cli.getPositions()
    # print(positions)

    # await cli.closeAllPositions(positions)

    # print(cli.getPositionState())
    # time.sleep(10)

    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
