import json
import os
import re
import sys
from pathlib import Path
from typing import List

from eth_account import Account
from loguru import logger


def load_json(filepath: Path | str):
    with open(filepath, "r") as file:
        return json.load(file)


class ABI:
    TOKEN = load_json("core/abi/tokens.json")
    CLAIM = load_json("core/abi/claim.json")


def setup_logger():
    log_dir = 'logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger.remove()

    logger.add(
        sys.stdout,
        colorize=True,
        format=("<green>{time:DD.MM HH:mm:ss}</green> | "
                "<yellow>Thread ID: {thread.id}</yellow> - "
                "<level>{message}</level>"),
        level="INFO"
    )

    logger.add(
        os.path.join(log_dir, 'logfile.log'),
        format="{time:DD.MM HH:mm:ss} | "
               "{name} | "
               "Thread ID: {thread.id} - {message}",
        level="INFO",
        encoding='utf-8',
        errors='ignore'
    )


async def load_file(filename: str) -> List[str]:
    with open(filename, 'r') as file:
        return [line.strip() for line in file.readlines()]


def get_address_wallet(
        private_key: str
):
    """Получает адрес кошелька из приватного ключа"""
    if private_key.startswith("0x"):
        private_key = private_key[2:]

    if not re.match(r"^[0-9a-fA-F]{64}$", private_key):
        raise ValueError(
            "Неверный формат приватных ключей"
        )
    account = Account.from_key(private_key)
    return account.address


def convert_to_bytes(address: str) -> bytes:
    padded_address = address[2:].rjust(64, '0')
    return bytes.fromhex(padded_address)
