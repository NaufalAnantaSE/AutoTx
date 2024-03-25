from web3 import Web3
from web3.types import TxParams
from autotx.utils.ethereum.constants import GAS_PRICE_MULTIPLIER
from autotx.utils.ethereum.mock_erc20 import MOCK_ERC20_ABI


def build_approve_erc20(web3: Web3, token_address: str, spender: str, value: int):
    MockERC20 = web3.eth.contract(address=token_address, abi=MOCK_ERC20_ABI)

    tx: TxParams = MockERC20.functions.approve(spender, value).build_transaction()

    return tx