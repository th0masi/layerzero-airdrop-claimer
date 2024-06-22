import traceback
from typing import List

from core.claimer import Claimer
from core.const import TOKEN_CONTRACT
from core.exceptions import NotEnoughtNative
from core.utils import ABI
from core.w3 import Web3Manager
from core.withdraw.okx_ import Okx
from loguru import logger


class Transfer(Web3Manager):
    def __init__(
            self,
            chain: str,
            key: str,
            deposit_address: str,
            proxies: List[str]
    ):
        super().__init__(chain=chain, key=key)
        self.proxies = proxies
        self.deposit_address = deposit_address
        self.token_contract_address = TOKEN_CONTRACT
        self.token_contract = self.provider.eth.contract(
                address=self.provider.to_checksum_address(
                    self.token_contract_address
                ),
                abi=ABI.TOKEN,
            )

    async def run(self, status=False):
        claimer_action = Claimer(
            key=self.key,
            chain=self.chain,
            proxies=self.proxies,
        )
        amount_wei = await claimer_action.get_zro_balance()
        amount = round(amount_wei / 10 ** 18, 2)

        logger.info(
            f'{self.wallet} | Отправляю {amount} '
            f'$ZRO на {self.deposit_address}'
        )
        try:
            if amount_wei:
                status = await self.transfer_tokens(amount_wei, amount)

        except NotEnoughtNative as e:
            needed_amount_wei = e.args[0]
            needed_amount = needed_amount_wei / 10 ** 18

            is_withdraw = Okx.run(
                token='ETH',
                wallet=self.wallet,
                chain=self.chain,
                amount=needed_amount,
            )

            if is_withdraw:
                logger.info(
                    f'{self.wallet} | Повторная попытка отправить $ZRO...'
                )
                await self.run()

        finally:
            return status

    async def transfer_tokens(
            self,
            amount_wei: int,
            amount: float,
    ):
        try:
            data = self.token_contract.encodeABI(
                fn_name='transfer',
                args=[
                    self.provider.to_checksum_address(
                        self.deposit_address
                    ),
                    int(amount_wei)
                ]
            )

            contract_txn = self.build_tx(
                data=data,
                to_address=self.token_contract_address,
            )

            gas_price = self.provider.eth.gas_price
            gas_estimate = self.provider.eth.estimate_gas(contract_txn)
            total_gas_cost_wei = gas_price * gas_estimate

            native_balance_wei = self.provider.eth.get_balance(self.wallet)

            if native_balance_wei < total_gas_cost_wei:
                needed_amount_wei = total_gas_cost_wei - native_balance_wei
                logger.error(
                    f"{self.wallet} | Недостаточно нативок "
                    f"для трансфера, ищу способ пополнить..."
                )
                raise NotEnoughtNative(needed_amount_wei)

            status, hash_ = self.sign_message(
                contract_txn=contract_txn
            )

            if status:
                logger.success(f'{self.wallet} | Успешно перевели {amount} '
                            f'$ZRO на {self.deposit_address}\n'
                            f'{self.explorer}/{hash_}')
            else:
                logger.error(f'{self.wallet} | Ошибка при отправке '
                             f'{amount} $ZRO на {self.deposit_address}\n'
                             f'{self.explorer}/{hash_}')

            return status

        except Exception as e:
            traceback.print_exc()
            logger.error(f'{self.wallet} | Ошибка при трансфере: {e}')

