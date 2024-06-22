import time
from typing import Dict, Any

from core.const import CHAINS_DATA
from core.utils import get_address_wallet
from loguru import logger
from web3 import Web3, exceptions


class Web3Manager:
    def __init__(
            self,
            chain: str,
            key: str,
    ):
        self.key = key
        self.wallet = get_address_wallet(self.key)
        self.chain = chain.lower()
        self.rpc = CHAINS_DATA.get(self.chain).get('rpc')
        self.explorer = CHAINS_DATA.get(self.chain).get('explorer')
        self.provider = Web3(Web3.HTTPProvider(self.rpc))

    def build_tx(
            self,
            value: int = 0,
            data=None,
            to_address: str = None,
    ):
        contract_txn = {
            "chainId": self.provider.eth.chain_id,
            "from": self.provider.to_checksum_address(
                self.wallet
            ),
            "nonce": self.provider.eth.get_transaction_count(
                self.wallet
            ),
        }

        if value:
            contract_txn.update({"value": int(value)})

        if data:
            contract_txn.update({"data": data})

        if to_address:
            contract_txn.update({"to": self.provider.to_checksum_address(
                to_address
            )})

        return contract_txn

    def sign_message(
            self,
            contract_txn: Dict[str, Any],
            gas_boost: float = 1.5,
    ):
        try:
            gas_limit = self.estimate_gas(
                contract_txn=contract_txn,
            )
            contract_txn['gas'] = int(gas_limit * gas_boost)

            self.add_price(
                chain=self.chain,
                contract_txn=contract_txn,
            )

            signed_txn = self.provider.eth.account.sign_transaction(
                contract_txn,
                self.key
            )
            tx_hash = self.provider.eth.send_raw_transaction(
                signed_txn.rawTransaction
            )
            hex_hash = self.provider.to_hex(tx_hash)

            logger.info(f'{self.wallet} | Отправил транзакцию, '
                        f'жду включения в блок...')

            status_tx = self.check_transaction_status(
                tx_hash=hex_hash
            )

            return status_tx, hex_hash

        except Exception as e:
            logger.error(f'Ошибка при подписи транзакции: {e}')

            return False, None

    def add_price(
            self,
            chain: str,
            contract_txn: Dict[str, Any],
    ) -> Dict[str, Any]:

        block = self.provider.eth.get_block('pending')
        base_fee = block['baseFeePerGas']

        tip = self.provider.eth.max_priority_fee

        if chain in ['avalanche', 'arbitrum']:
            tip = base_fee

        if chain in ['ethereum']:
            base_fee = 2

        max_fee = tip + base_fee - 1
        contract_txn['maxPriorityFeePerGas'] = tip
        contract_txn['maxFeePerGas'] = max_fee

        return contract_txn

    def estimate_gas(
            self,
            contract_txn: Dict[str, Any],
    ) -> int:
        try:
            base_gas_limit = self.provider.eth.estimate_gas(
                contract_txn
            )
            gas_limit = int(base_gas_limit)
            return gas_limit

        except Exception as e:
            raise Exception(
                f'При расчете GAS LIMIT возникла ошибка: {e}'
            )

    def check_transaction_status(
            self,
            tx_hash: hash,
            timeout: int = 1200,  # 20 мин
            poll_interval: int = 10
    ):
        time.sleep(10)
        total_wait_time = 0

        while total_wait_time < timeout:
            try:
                tx_receipt = self.provider.eth.get_transaction_receipt(tx_hash)

                if tx_receipt is None:
                    time.sleep(poll_interval)
                    total_wait_time += poll_interval
                else:
                    if tx_receipt["status"] == 1:
                        return True
                    elif tx_receipt["status"] == 0:
                        return False
                    else:
                        time.sleep(poll_interval)
                        total_wait_time += poll_interval

            except exceptions.TransactionNotFound:
                time.sleep(poll_interval)
                total_wait_time += poll_interval
            except ConnectionError as e:
                raise Exception(
                    f"ошибка подключения при "
                    f"проверки статуса транзакции: {e}\n "
                )
            except Exception as e:
                raise Exception(
                    f"произошла неизвестная ошибка "
                    f"при проверки статуса транзакции: {e}"
                )

        raise Exception(
            f"транзакция не была добавлена " 
            f"в блокчейн спустя {timeout} секунд"
        )
