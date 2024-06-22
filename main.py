from core.database import Database
from core.process import process_wallets, initialize_database
from core.utils import load_file, setup_logger
import asyncio

from core.withdraw.okx_ import Okx
from loguru import logger


async def main():
    logger.info("Owner by Thor: https://t.me/thor_lab")
    keys = await load_file('data/private_keys.txt')
    deposit_addresses = await load_file('data/deposit_addresses.txt')
    proxies = await load_file('data/proxies.txt')
    db = Database()

    if not proxies:
        logger.warning(
            'Вы запустили чекер без прокси! Если не будет работать, '
            'добавьте их в PROXIES.TXT в любом формате'
        )

    if len(keys) != len(deposit_addresses):
        logger.error(
            f'Количество приватников: {len(keys)}, не совпадает с кол-вом '
            f'депозитных адресов: {len(deposit_addresses)}'
        )
        logger.error(
            f'Проверьте все еще раз и перезапустите софт'
        )
        exit(1)

    await initialize_database(
        db=db,
        private_keys=keys,
        deposit_addresses=deposit_addresses
    )

    await process_wallets(
        db=db,
        private_keys=keys,
        proxies=proxies
    )

    # Пылесос
    okx = Okx(token='ZRO')
    okx.okx_hoover()

if __name__ == '__main__':
    setup_logger()
    asyncio.run(main())
