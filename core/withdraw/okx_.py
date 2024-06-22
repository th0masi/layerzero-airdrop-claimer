import random
import time

from _decimal import Decimal
from core.exceptions import OkxNetworkDisabled
from core.withdraw.base import Base
from data.config import WITHDRAW_DELAY
from loguru import logger


class Okx(Base):
    def __init__(
            self,
            address: str = None,
            token: str = None,
    ):
        super().__init__(
            name='okx'
        )
        self.address = address
        self.token = token.upper()
        self.exchange = self.get_ccxt()
        self.prossible_names = {
            'arbitrum': 'ETH-Arbitrum One',
            'optimism': 'OPTIMISM',
            'base': 'Base',
        }

    @staticmethod
    def run(
            token: str,
            wallet: str,
            chain: str,
            amount: float,
            status=False
    ):
        try:
            action = Okx(
                address=wallet,
                token=token.upper(),
            )
            action.check_auth()
            chains_list = action.get_chains_list()

            selected_chain = action.search_chain(
                chain=chain,
                available_chains=chains_list
            )

            logger.info(
                f'OKX | Будем выводить в {selected_chain["name"]}'
            )

            action = Okx(
                address=wallet,
                token=token.upper(),
            )

            status = action.withdraw(
                amount=amount,
                selected_chain=selected_chain,
            )

            if status:
                amt_sleep = random.randint(*WITHDRAW_DELAY)
                logger.info(f'Сплю {amt_sleep} сек. после вывода...')
                time.sleep(amt_sleep)

        except OkxNetworkDisabled:
            raise OkxNetworkDisabled

        except Exception as e:
            logger.error(f'При работе с OKX возникла ошибка: {e}')

        return status

    def withdraw(
            self,
            selected_chain,
            amount,
            status=False,
    ):
        amount = Decimal(str(amount))
        withdraw_fee = Decimal(selected_chain['withdrawFee'])
        amount += withdraw_fee
        amount = round(amount, 6)

        try:
            min_withdraw = float(selected_chain['withdrawMin'])

            if min_withdraw > amount:
                logger.warning(
                    f'OKX | Минимальная сумма для вывода: '
                    f'{amount}, меньше чем минимальная сумма '
                    f': {selected_chain["withdrawMin"]}'
                )
                amount = round(min_withdraw * random.uniform(1.001, 1.03), 6)

            withdrawal = self.exchange.withdraw(
                self.token,
                amount,
                self.address,
                params={
                    "chain": selected_chain['chainId'],
                    "fee": selected_chain['withdrawFee'],
                    "pwd": "-",
                },
            )
            withdrawal_id = withdrawal.get('info').get('wdId')

            if withdrawal_id:
                logger.info(
                    f'{self.address} | Отправил запрос на вывод '
                    f'{amount} ${self.token}, ID: {withdrawal_id}'
                )
                logger.info(
                    f'Ожидаю поступления депозита...'
                )

                status = self.check_withdraw_status(
                    id_=withdrawal_id,
                )

        except Exception as e:
            logger.error(
                f'{self.address} | Не удалось вывести '
                f'{amount} ${self.token}, ошибка: {e}'
            )

        finally:
            return status

    def get_chains_list(self):
        logger.info(f'OKX | Получаю данные о сетях для вывода...')
        self.exchange.load_markets()

        chains_info = {}

        if self.token in self.exchange.currencies:
            currency_info = self.exchange.currencies[self.token]
            networks = currency_info.get('networks', [])
            for network_key, network_info in networks.items():
                if 'info' in network_info and isinstance(network_info['info'],
                                                         dict):
                    info = network_info['info']
                    chain_id = network_info.get('id')
                    withdraw_enable = info.get('canWd', False)
                    withdraw_fee = network_info.get('fee', None)
                    withdraw_min = network_info.get('limits', {}).get(
                        'withdraw', {}).get('min', None)

                    chains_info[network_key] = {
                        'chainId': chain_id,
                        'withdrawEnable': withdraw_enable,
                        'withdrawFee': withdraw_fee,
                        'withdrawMin': withdraw_min,
                    }

        return chains_info

    def okx_hoover(
            self
    ) -> None:
        logger.info(f"OKX | Собираем балансы с суб-аккаунтов...")

        sub_accounts = self.exchange.private_get_users_subaccount_list()
        data = sub_accounts.get('data')

        if not data:
            raise Exception(f"в ответе API отсутствует "
                            f"data суб-аккаунтов")

        for acc in data:
            sub_acc_name = acc.get('subAcct')

            if not sub_acc_name:
                raise Exception(f"в ответе API отсутствует "
                                f"имена суб-аккаунтов")

            balance_list = self.exchange.private_get_asset_subaccount_balances(
                {'subAcct': sub_acc_name, 'type': 'funding'}
            )

            for balance_data in balance_list['data']:
                balance = balance_data.get('bal')
                token_name = balance_data.get('ccy')

                if balance and token_name:
                    transfer_params = {
                        'ccy': token_name,
                        'amt': balance,
                        'from': 6,
                        'to': 6,
                        'type': 2,
                        'subAcct': sub_acc_name
                    }
                    self.exchange.private_post_asset_transfer(transfer_params)

                    logger.success(f"OKX | Перевел {round(float(balance), 2)} "
                                   f"${token_name.upper()} на "
                                   f"основной аккаунт")

        logger.info(f'OKX | Выключил пылесос')
        time.sleep(1)

    def check_withdraw_status(
            self,
            id_: int,
            delay: tuple = (15, 40),
    ):
        start_time = time.time()

        while True:
            try:
                time.sleep(random.uniform(*delay))

                fetched_withdrawal = self.exchange.fetch_withdrawal(
                    id=id_
                )
                status_str = fetched_withdrawal.get('status')

                if status_str == 'ok':
                    return True

                elif status_str == 'failed':
                    return False

                if time.time() - start_time > 1800:
                    if status_str:
                        raise Exception(
                            f"Статус вывода #{id_} не изменился, "
                            f"после 20 минут ожидания. "
                            f"Статус: {status_str}"
                        )
                    else:
                        raise Exception(
                            f"В ответе API отсутствует статус для "
                            f"вывода #{id_} после 30 минут ожидания"
                        )

                time.sleep(60)

            except Exception:
                pass