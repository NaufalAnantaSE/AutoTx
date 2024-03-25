from gnosis.eth import EthereumClient
from gnosis.eth.oracles.uniswap_v3 import UniswapV3Oracle
import requests


from web3.contract.contract import Contract

from web3.types import TxParams
from autotx.utils.PreparedTx import PreparedTx
from autotx.utils.ethereum.constants import GAS_PRICE_MULTIPLIER

from autotx.utils.ethereum.mock_erc20 import MOCK_ERC20_ABI


SLIPPAGE = 0.05
SQRT_PRICE_LIMIT = 0


def get_swap_information(
    amount: int, token_in: Contract, token_out: Contract, price: int, exact_input: bool
):
    token_in_decimals = token_in.functions.decimals().call()
    token_out_decimals = token_out.functions.decimals().call()
    if exact_input:
        amount_compared_with_token = amount * price
        minimum_amount_out = int(amount_compared_with_token * 10**token_out_decimals)
        amount_out = int(minimum_amount_out - (minimum_amount_out * SLIPPAGE))
        return (amount_out, int(amount * 10**token_in_decimals), "exactInputSingle")
    else:
        amount_compared_with_token = amount / price
        max_amount_in = int(amount_compared_with_token * 10**token_in_decimals)
        amount_in = int(max_amount_in + (max_amount_in * SLIPPAGE))
        return (
            int(amount * 10**token_out_decimals),
            amount_in,
            "exactOutputSingle",
        )


def get_best_fee_tier(token_in_address: str, token_out_address: str) -> int:
    token_in_lower = token_in_address.lower()
    token_out_lower = token_out_address.lower()
    reversed = token_in_lower > token_out_lower

    (token0, token1) = (
        (token_out_lower, token_in_lower)
        if reversed
        else (token_in_lower, token_out_lower)
    )

    data = {
        "query": """
            query GetPools($token0: String, $token1: String) {
                pools(
                    where: {
                        token0: $token0
                        token1: $token1
                    }
                ) {
                    id
                    feeTier
                    sqrtPrice
                    liquidity
                    token0 {
                        id
                        symbol
                    }
                    token1 {
                        id
                        symbol
                    }
                }
            }
        """,
        "variables": {"token0": token0, "token1": token1},
    }
    url = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
    response = requests.post(url, json=data)

    if response.status_code == 200:
        if not "data" in response.json():
            raise Exception(f"Request failed with response: {response.json()}")
        pools = response.json()["data"]["pools"]

        max_liquidity_pool = max(pools, key=lambda x: int(x["liquidity"]))
        return int(max_liquidity_pool["feeTier"])
    else:
        raise Exception(f"Request failed with status code: {response.status_code}")


def build_swap_transaction(
    etherem_client: EthereumClient,
    amount: int,
    token_in_address: str,
    token_out_address: str,
    _from: str,
    exact_input: bool,
) -> list[PreparedTx]:
    uniswap = UniswapV3Oracle(etherem_client)
    web3 = etherem_client.w3

    token_in_is_eth = token_in_address == str(uniswap.weth_address)

    token_in = web3.eth.contract(address=token_in_address, abi=MOCK_ERC20_ABI)
    token_out = web3.eth.contract(address=token_out_address, abi=MOCK_ERC20_ABI)
    price = uniswap.get_price(token_in_address, token_out_address)
    (amount_out, amount_in, method) = get_swap_information(
        amount, token_in, token_out, price, exact_input
    )

    token_in_symbol = token_in.functions.symbol().call()
    token_out_symbol = token_out.functions.symbol().call()

    transactions: list[PreparedTx] = []
    if not token_in_is_eth:
        allowance = token_in.functions.allowance(_from, uniswap.router_address).call()
        if allowance < amount_in:
            tx = token_in.functions.approve(
                    uniswap.router_address, amount_in
                ).build_transaction(
                    {
                        "from": _from,
                        "gasPrice": int(web3.eth.gas_price * GAS_PRICE_MULTIPLIER),
                    }
                )
            transactions.append(
                PreparedTx(
                    f"Approve {amount_in} {token_in_symbol} to Uniswap",
                    tx,
                )
            )

    fee = get_best_fee_tier(token_in_address, token_out_address)
    swap_transaction = uniswap.router.functions[method](
        (
            token_in_address,
            token_out_address,
            fee,
            _from,
            amount_out if method == "exactOutputSingle" else amount_in,
            amount_in if method == "exactOutputSingle" else amount_out,
            SQRT_PRICE_LIMIT,
        )
    ).build_transaction(
        {
            "value": amount_in if token_in_is_eth else 0,
            "gas": None,
            "gasPrice": int(web3.eth.gas_price * GAS_PRICE_MULTIPLIER),
        }
    )
    transactions.append(
        PreparedTx(
            f"Swap {amount} {token_in_symbol} for {amount_out} {token_out_symbol}",
            swap_transaction,
        )
    )
    return transactions