from dotenv import load_dotenv
load_dotenv()

from typing import cast
from datetime import datetime
import click
import os

from autotx.utils.ethereum.cached_safe_address import get_cached_safe_address
from autotx.utils.ethereum.helpers.fill_dev_account_with_tokens import fill_dev_account_with_tokens
from autotx.utils.is_dev_env import is_dev_env

from autotx.agents.ResearchTokensAgent import ResearchTokensAgent
from autotx.agents.SendTokensAgent import SendTokensAgent
from autotx.agents.SwapTokensAgent import SwapTokensAgent

from autotx.utils.constants import COINGECKO_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL_NAME
from autotx.utils.ethereum.networks import ChainId, NetworkInfo
from autotx.utils.ethereum.helpers.get_dev_account import get_dev_account
from autotx.AutoTx import AutoTx, Config
from autotx.utils.ethereum.agent_account import get_or_create_agent_account
from autotx.utils.ethereum.SafeManager import SafeManager
from autotx.utils.ethereum.send_native import send_native
from autotx.utils.ethereum.helpers.show_address_balances import show_address_balances
from autotx.utils.configuration import get_configuration


@click.group()
def main() -> None:
    pass

@main.command()
@click.argument('prompt', required=False)
@click.option("-n", "--non-interactive", is_flag=True, help="Non-interactive mode (will not expect further user input or approval)")
@click.option("-v", "--verbose", is_flag=True, help="Verbose mode")
@click.option("-l", "--logs", type=click.Path(exists=False, file_okay=False, dir_okay=True), help="Path to the directory where logs will be stored.")
@click.option("-r", "--max-rounds", type=int, help="Maximum number of rounds to run")
@click.option("-c", "--cache", is_flag=True, help="Use cache for LLM requests")
def run(prompt: str | None, non_interactive: bool, verbose: bool, logs: str | None, max_rounds: int | None, cache: bool | None) -> None:

    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d-%H-%M-%S-') + str(now.microsecond)
    logs_dir = os.path.join(logs, now_str) if logs is not None else None

    print("""
  /$$$$$$              /$$            /$$$$$$$$       
 /$$__  $$            | $$           |__  $$__/       
| $$  \ $$ /$$   /$$ /$$$$$$    /$$$$$$ | $$ /$$   /$$
| $$$$$$$$| $$  | $$|_  $$_/   /$$__  $$| $$|  $$ /$$/
| $$__  $$| $$  | $$  | $$    | $$  \ $$| $$ \  $$$$/ 
| $$  | $$| $$  | $$  | $$ /$$| $$  | $$| $$  >$$  $$ 
| $$  | $$|  $$$$$$/  |  $$$$/|  $$$$$$/| $$ /$$/\  $$
|__/  |__/ \______/    \___/   \______/ |__/|__/  \__/

Source: https://github.com/polywrap/AutoTx
Support: https://discord.polywrap.io
""")

    if prompt == None:
        prompt = click.prompt("What do you want to do?")

    (smart_account_addr, agent, client) = get_configuration()
    web3 = client.w3

    chain_id = web3.eth.chain_id

    network_info = NetworkInfo(chain_id)
    
    print(f"LLM model: {OPENAI_MODEL_NAME}")
    print(f"LLM API URL: {OPENAI_BASE_URL}")

    if is_dev_env():
        print(f"Connected to fork of {network_info.chain_id.name} network.")
    else:
        print(f"Connected to {network_info.chain_id.name} network.")

    print_agent_address()

    manager: SafeManager

    if smart_account_addr:
        if not SafeManager.is_valid_safe(client, smart_account_addr):
            raise Exception(f"Invalid safe address: {smart_account_addr}")

        print(f"Smart account connected: {smart_account_addr}")
        manager = SafeManager.connect(client, smart_account_addr, agent)

        manager.connect_tx_service(network_info.chain_id, network_info.transaction_service_url)
    else:
        print("No smart account connected, deploying a new one...")
        dev_account = get_dev_account()

        is_safe_deployed = get_cached_safe_address()
        manager = SafeManager.deploy_safe(client, dev_account, agent, [dev_account.address, agent.address], 1)
        print(f"Smart account deployed: {manager.address}")
        
        if not is_safe_deployed:
            fill_dev_account_with_tokens(client, dev_account, manager.address, network_info)
            print(f"Funds sent to smart account for testing purposes")

        print("=" * 50)
        print("Starting smart account balances:")
        show_address_balances(web3, network_info.chain_id, manager.address)
        print("=" * 50)

    get_llm_config = lambda: { 
        "cache_seed": 1 if cache else None, 
        "config_list": [
            {
                "model": OPENAI_MODEL_NAME, 
                "api_key": OPENAI_API_KEY,
                "base_url": OPENAI_BASE_URL
            }
        ]
    }
    agents = [
        SendTokensAgent(),
        SwapTokensAgent()
    ]

    if COINGECKO_API_KEY:
        agents.append(ResearchTokensAgent())

    autotx = AutoTx(
        manager,
        network_info,
        agents,
        Config(verbose=verbose, logs_dir=logs_dir, max_rounds=max_rounds),
        get_llm_config=get_llm_config,
    )

    result = autotx.run(cast(str, prompt), non_interactive)

    if result.total_cost_without_cache > 0:
        print(f"LLM cost: ${result.total_cost_without_cache:.2f} (Actual: ${result.total_cost_with_cache:.2f})")
        
    if not smart_account_addr:
        print("=" * 50)
        print("Final smart account balances:")
        show_address_balances(web3, network_info.chain_id, manager.address)
        print("=" * 50)

@main.group()
def agent() -> None:
    pass

@agent.command(name="address")
def agent_address() -> None:
    print_agent_address()

def print_agent_address() -> None:
    acc = get_or_create_agent_account()
    print(f"Agent address: {acc.address}")

if __name__ == "__main__":
    main()
