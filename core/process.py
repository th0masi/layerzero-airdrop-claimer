import random
import time
import traceback
from typing import List

from core.allocation import Allocation
from core.claimer import Claimer
from core.database import Database
from core.enums import ClaimStatus
from core.exceptions import OkxNetworkDisabled
from core.transfer import Transfer
from core.utils import get_address_wallet
from data.config import CHAINS, ACCOUNT_DELAY, CLAIM_DELAY
from loguru import logger


async def initialize_database(
        db: Database,
        private_keys: List[str],
        deposit_addresses: List[str]
):
    await db.create_table()

    existing_wallets = [record[0] for record in await db.get_all_wallets()]

    for key, deposit_address in zip(private_keys, deposit_addresses):
        wallet = get_address_wallet(key)
        if wallet not in existing_wallets:
            await db.add_wallet(wallet, deposit_address)


async def process_wallets(
        private_keys: List[str],
        proxies: List[str],
        db: Database
):
    for index, key in enumerate(private_keys, start=1):
        wallet = get_address_wallet(key)

        logger.info(
            f'[{index}/{len(private_keys)}] Работаем с кошельком {wallet}'
        )

        wallet_data = await db.get_wallets_by_status(ClaimStatus.SUCCESS)
        if wallet_data and wallet in [w[0] for w in wallet_data]:
            logger.warning(
                f'{wallet} | Уже работали с кошельком, пропускаем...'
            )
            continue

        deposit_address = await db.get_deposit_address(wallet)
        if not deposit_address:
            logger.error(
                f'{wallet} | Не найден депозитный адрес в базе данных'
            )
            continue

        claim_status, allocation, is_transfer = await search_token(
            wallet=wallet,
            key=key,
            proxies=proxies,
            deposit_address=deposit_address,
        )

        if not is_transfer:
            claim_status, allocation = await claim(
                key=key,
                wallet=wallet,
                deposit_address=deposit_address,
                proxies=proxies,
            )

            if claim_status == ClaimStatus.SUCCESS:
                logger.success(
                    f'{wallet} | Успешно завершили работу с кошельком'
                )

            elif claim_status == ClaimStatus.WITHOUT_ALLOCATION:
                logger.warning(
                    f'{wallet} | На кошельке не найдена аллокация'
                )
                ti
            elif claim_status == ClaimStatus.ALREADY_CLAIMED:
                logger.info(
                    f'{wallet} | Дроп уже был заклеймлен на '
                    f'кошельке, пропускаем...'
                )
            else:
                logger.error(
                    f'{wallet} | Ошибка: неизвестный статус клейма'
                )

        await db.update_claim_status(
            wallet,
            claim_status,
            allocation=allocation,
            claimed=False if claim_status == ClaimStatus.ERROR else True
        )

        if claim_status == ClaimStatus.SUCCESS:
            amt_sleep = random.randint(*ACCOUNT_DELAY)
            logger.info(f'Сплю {amt_sleep} сек. между аккаунтами...')
            time.sleep(amt_sleep)
        else:
            time.sleep(2)

    logger.success(f'Завершили работу')


async def claim(
        key: str,
        wallet: str,
        deposit_address: str,
        proxies: List[str],
        allocation_amount=0,
):
    available_chains = ['arbitrum', 'base', 'optimism']
    random.shuffle(CHAINS)
    first_iter = True

    for chain in CHAINS:
        try:
            if chain not in available_chains:
                logger.error(
                    f'Неизвестная сеть в конфиге: {chain},'
                    f' доступные: {available_chains}'
                )

            claim_action = Claimer(
                chain=chain,
                key=key,
                proxies=proxies,
            )

            already_claimed = await claim_action.is_claimed()

            if already_claimed:
                logger.info(
                    f'{wallet} | Дроп уже заклеймлен, '
                    f'пропускаем кошелек...'
                )
                return ClaimStatus.ALREADY_CLAIMED, allocation_amount

            if first_iter:
                logger.info(
                    f'{wallet} | Выбрана рандомная сеть: {chain.upper()}'
                )
                logger.info(
                    f'{wallet} | Проверяю доступную аллокацию..'
                )
            else:
                logger.info(
                    f'{wallet} | Меняем сеть на {chain.upper()}'
                )

            action = Allocation(wallet=wallet, proxies=proxies)
            allocation_amount = await action.get_allocation()

            if allocation_amount is None:
                logger.error(
                    f'{wallet} | Ошибка при получении аллокации'
                )
                continue

            if float(allocation_amount) > 0:
                if first_iter:
                    logger.info(
                        f'{wallet} | Аллокация найдена: '
                        f'{allocation_amount} $ZRO'
                    )

                claim_status = await claim_action.run(first_iter)

                if not claim_status:
                    continue

                amt_sleep = random.randint(*CLAIM_DELAY)
                logger.info(f'Сплю {amt_sleep} сек. перед трансфером...')
                time.sleep(amt_sleep)

                transfer_action = Transfer(
                    chain=chain,
                    key=key,
                    deposit_address=deposit_address,
                    proxies=proxies,
                )

                status = await transfer_action.run()

                if status:
                    return ClaimStatus.SUCCESS, allocation_amount

            else:
                logger.warning(
                    f'{wallet} | Кошелек без аллокации, пропускаем...'
                )
                return ClaimStatus.WITHOUT_ALLOCATION, allocation_amount

        except OkxNetworkDisabled:
            continue

        except Exception as e:
            traceback.print_exc()
            logger.error(f'{wallet} | Ошибка при подготовке к клейму: {e}')
            continue

        first_iter = False

    return ClaimStatus.ERROR, allocation_amount


async def search_token(
        wallet: str,
        key: str,
        proxies: List[str],
        deposit_address: str,
        status: bool = False,
):
    logger.info(
        f'{wallet} | Ищем баланс $ZRO во всех сетях, '
        f'возможно дроп уже был заклеймлен...'
    )

    chain, amount_wei = await Claimer.search_zro_balance_in_all_chains(
        wallet=wallet,
    )
    allocation_amount = round(amount_wei / 10 ** 18, 2)

    if chain and allocation_amount:
        logger.info(
            f'{wallet} | Нашли {allocation_amount} $ZRO'
            f' в сети {chain.upper()}'
        )

        amt_sleep = random.randint(*CLAIM_DELAY)
        logger.info(f'Сплю {amt_sleep} сек. перед трансфером...')
        time.sleep(amt_sleep)

        transfer_action = Transfer(
            chain=chain,
            key=key,
            deposit_address=deposit_address,
            proxies=proxies,
        )

        status = await transfer_action.run()

        claim_status = ClaimStatus.SUCCESS
    else:
        logger.info(
            f'{wallet} | Баланс не найден'
        )
        claim_status = ClaimStatus.PENDING

    return claim_status, allocation_amount, status
