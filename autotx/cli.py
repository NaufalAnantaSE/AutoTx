import click
from dotenv import load_dotenv

from autotx.utils.ethereum.constants import CHAIN_ID_TO_NETWORK_MAP
from autotx.utils.ethereum.helpers.get_dev_account import get_dev_account
load_dotenv()
from autotx.agents import SendTokensAgent
from autotx.agents import SwapTokensAgent
from autotx.AutoTx import AutoTx
from autotx.patch import patch_langchain
from autotx.utils.ethereum.agent_account import get_agent_account, create_agent_account, delete_agent_account
from autotx.utils.ethereum.SafeManager import SafeManager
from autotx.utils.ethereum.send_eth import send_eth
from autotx.utils.ethereum.helpers.show_address_balances import show_address_balances
from autotx.utils.configuration import get_configuration

patch_langchain()

@click.group()
def main():
    pass

@main.command()
@click.option("--prompt", prompt="Prompt", required=True, help="Prompt")
@click.option("-n", "--non-interactive", is_flag=True, help="Non-interactive mode (will not expect further user input or approval)")
def run(prompt: str, non_interactive: bool):
    (smart_account_addr, agent, client) = get_configuration()
    web3 = client.w3

    chain_id = web3.eth.chain_id
    print(f"Chain ID: {chain_id}")

    network_info = CHAIN_ID_TO_NETWORK_MAP.get(chain_id)

    if network_info is None:
        raise Exception(f"Chain ID {chain_id} is not supported")

    manager: SafeManager

    if smart_account_addr:
        if not SafeManager.is_valid_safe(client, smart_account_addr):
            raise Exception(f"Invalid safe address: {smart_account_addr}")

        print(f"Smart account connected: {smart_account_addr}")
        manager = SafeManager.connect(client, smart_account_addr, agent)

        manager.connect_tx_service(network_info.network, network_info.transaction_service_url)
    else:
        print("No smart account connected, deploying a new one...")
        dev_account = get_dev_account()

        manager = SafeManager.deploy_safe(client, dev_account, agent, [dev_account.address, agent.address], 1)
        print(f"Smart account deployed: {manager.address}")
        
        send_eth(dev_account, manager.address, int(10 * 10**18), web3)
        print(f"Sent 10 ETH to smart account for testing purposes")

    print("Starting smart account balances:")
    show_address_balances(web3, manager.address)

    autotx = AutoTx(manager, [
        SendTokensAgent.build_agent_factory(),
        SwapTokensAgent.build_agent_factory(client, manager.address),
    ], None)
    autotx.run(prompt, non_interactive)

    print("Final smart account balances:")
    show_address_balances(web3, manager.address)

@main.group()
def agent():
    pass

@agent.group(name="account")
def agent_account():
    pass

@agent_account.command(name="create")
def agent_account_create():
    acc = get_agent_account()

    if acc:
        print(f"Agent account already exists: {acc.address}.\nUse 'delete' command to delete it.")
        return

    print("Creating agent account...")

    acc = create_agent_account()

    print(f"Agent account created with address {acc.address}")

@agent_account.command(name="delete")
def agent_account_delete():
    print("Deleting agent account...")
    delete_agent_account()
    print("Agent account deleted")

@agent_account.command(name="info")
def agent_account_info():
    (_user, agent, client, _safe_address) = get_configuration()
    web3 = client.w3
    print(f"Agent address: {agent.address}")
    show_address_balances(web3, agent.address)

if __name__ == "__main__":
    main()