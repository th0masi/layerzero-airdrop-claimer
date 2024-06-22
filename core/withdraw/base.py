from ccxt import AuthenticationError
import ccxt
from core.exceptions import OkxNetworkDisabled
from data.config import API_KEY, API_SECRET, API_PASSWORD, API_PROXY
from loguru import logger


class Base:
    def __init__(self, name: str):
        self.cex_name = name

    def get_ccxt(self):
        try:
            if not API_KEY or not API_SECRET:
                raise Exception(f"Отсутствует api key или "
                                f"api secret для {self.cex_name.upper()}")

            exchange_options = {
                "apiKey": API_KEY,
                "secret": API_SECRET,
                "password": API_PASSWORD,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                },
            }

            if API_PROXY:
                exchange_options["proxies"] = {
                    "http": API_PROXY,
                    "https": API_PROXY,
                }

            exchange_class = getattr(ccxt, self.cex_name)
            exchange = exchange_class(exchange_options)

            return exchange

        except Exception as e:
            raise Exception(e)

    def check_auth(self):
        logger.info(
            f'OKX | Тестируем авторизацию...'
        )

        try:
            self.get_ccxt().fetch_balance()

            logger.success(
                f'OKX | Успешная авторизация'
            )

        except AuthenticationError as e:
            logger.error(
                f'OKX | Ошибка авторизации: {e}'
            )
            logger.error(
                'OKX | Проверьте корректно ли указаны API-KEY, '
                'API-SECRET или PASSWORD'
            )
            exit()

    @staticmethod
    def search_chain(
            chain: str,
            available_chains,
    ):
        prossible_names = {
            'arbitrum': 'ARBONE',
            'optimism': 'OPTIMISM',
            'base': 'Base',
        }
        api_chain_name = prossible_names.get(chain)

        if api_chain_name not in available_chains:
            logger.error(
                f"OKX | Сеть {chain.upper()} не найдена в API OKX"
            )
            return None

        details = available_chains[api_chain_name]

        if details['withdrawEnable']:
            chain_info = {
                'name': f"{chain.upper()} (ком.: {details['withdrawFee']}, "
                        f"мин. сумма: {details['withdrawMin']})",
                'chainKey': api_chain_name,
                'chainId': details['chainId'],
                'withdrawFee': details['withdrawFee'],
                'withdrawMin': details['withdrawMin']
            }
            return chain_info
        else:
            logger.warning(
                f"OKX | Вывод средств недоступен или временно "
                f"приостановлен в сети {chain.upper()}"
            )
            raise OkxNetworkDisabled
