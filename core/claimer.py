import time
import traceback
from typing import List

import eth_abi
from core.allocation import Allocation
from core.const import CHAINS_DATA, TOKEN_CONTRACT
from core.exceptions import NotEnoughtNative
from core.utils import ABI, convert_to_bytes
from core.w3 import Web3Manager
from core.withdraw.okx_ import Okx
from eth_abi.packed import encode_packed
from hexbytes import HexBytes
from loguru import logger
from web3 import Web3
from eth_abi import decode
from web3.middleware import geth_poa_middleware


class Claimer(Web3Manager):
    def __init__(
            self,
            chain: str,
            key: str,
            proxies: List[str]
    ):
        super().__init__(chain=chain, key=key)
        self.arb_provider = Web3(Web3.HTTPProvider(
            CHAINS_DATA.get('arbitrum').get('rpc')
        ))
        self.contract_address = CHAINS_DATA.get(
            self.chain
        ).get('contract_address')
        self.arb_donate_address = CHAINS_DATA.get(
            'arbitrum'
        ).get('donate_address')
        self.contract = self.provider.eth.contract(
            address=self.contract_address,
            abi=ABI.CLAIM,
        )
        self.proxies = proxies
        self.proof_url = (
            f'https://www.layerzero.foundation/'
            f'api/proof/{self.wallet}'
        )

    @staticmethod
    async def search_zro_balance_in_all_chains(wallet):
        chain_list = ['arbitrum', 'optimism', 'base']

        for chain in chain_list:
            provider = Web3(Web3.HTTPProvider(
                CHAINS_DATA.get(chain).get('rpc')
            ))
            provider.middleware_onion.inject(
                geth_poa_middleware,
                layer=0
            )

            token_contract = provider.eth.contract(
                address=provider.to_checksum_address(TOKEN_CONTRACT),
                abi=ABI.TOKEN,
            )
            balance = token_contract.functions.balanceOf(wallet).call()

            if balance > 0:
                return chain, balance

        return None, 0

    async def run(self, first_iter=True):
        response = await self.get_proof()

        amount_wei = int(response.get('amount'))
        proof_addresses = response.get('proof').split('|')
        donate_amount_wei = await self.get_amount_donate(
            allocation=amount_wei,
            first_iter=first_iter,
        )

        native_balance_wei = self.provider.eth.get_balance(self.wallet)
        _, fee_wei = await self.get_extra_bytes(amount_wei=amount_wei)
        txn_fee_wei = self.provider.to_wei(0.00004, 'ether')
        all_needed_wei = int(donate_amount_wei + fee_wei + txn_fee_wei)

        if native_balance_wei < all_needed_wei:
            needed_amount_wei = all_needed_wei - native_balance_wei
            needed_amount = self.provider.from_wei(needed_amount_wei, 'ether')
            logger.warning(
                f'{self.wallet} | Недостаточный баланc, '
                f'не хватает: {round(needed_amount, 5)} $ETH'
            )

            is_withdraw = Okx.run(
                token='ETH',
                wallet=self.wallet,
                chain=self.chain,
                amount=needed_amount,
            )

            if not is_withdraw:
                return False

        status = await self.claim(
            amount_wei=amount_wei,
            proof_addresses=proof_addresses,
            donate_amount_wei=donate_amount_wei
        )

        if status:
            logger.info(
                f'{self.wallet} | Ожидаем поступление $ZRO..'
            )
            zro_balance = 0

            while zro_balance == 0:
                zro_balance = await self.get_zro_balance()
                time.sleep(30)

            logger.success(
                f'{self.wallet} | {round(zro_balance / 10 ** 18, 2)} '
                f'$ZRO найдены на кошельке'
            )

        return status

    async def get_zro_balance(self):
        token_contract = self.provider.eth.contract(
            address=self.provider.to_checksum_address(TOKEN_CONTRACT),
            abi=ABI.TOKEN,
        )
        balance = token_contract.functions.balanceOf(self.wallet).call()

        return balance

    async def get_proof(self, response=None):
        try:
            request = Allocation(wallet=self.wallet, proxies=self.proxies)
            response = await request.send_request('GET', self.proof_url)
        except Exception as e:
            logger.error(
                f'{self.wallet} | Ошибка в запросе на получение proof: {e}'
            )

        return response

    async def is_claimed(self):
        function_selector = '0x7a692982000000000000000000000000'
        data = function_selector + encode_packed(
            ["address"],
            [self.wallet]
        ).hex()

        response = self.arb_provider.eth.call({
            'to': self.arb_provider.to_checksum_address(
                self.arb_donate_address
            ),
            'data': data
        })

        decoded_data = decode(
            ['uint256'],
            bytes.fromhex(response.hex()[2:])
        )

        if decoded_data[0] > 0:
            return True

        return False

    async def get_amount_donate(
            self,
            allocation,
            first_iter=True
    ):
        function_selector = '0xd6d754db'
        data = function_selector + encode_packed(
            ["uint256"],
            [allocation]
        ).hex()
        if first_iter:
            logger.info(
                f'{self.wallet} | Получаю сумму необходимого доната...'
            )

        try:
            response = self.arb_provider.eth.call({
                'to': self.arb_provider.to_checksum_address(
                    self.arb_donate_address
                ),
                'data': data
            })

            decoded_data = decode(
                ['uint256', 'uint256', 'uint256'],
                bytes.fromhex(response.hex()[2:])
            )

            stable_amount_wei = decoded_data[0]
            stable_amount = round(stable_amount_wei / 10 ** 6, 2)
            native_amount_wei = decoded_data[2]
            native_amount = round(native_amount_wei / 10 ** 18, 5)

            if first_iter:
                logger.info(
                    f'{self.wallet} | Сумма доната: {stable_amount} $USDT '
                    f'({native_amount} $ETH)'
                )

            return native_amount_wei

        except Exception as e:
            logger.error(
                f'Ошибка при вызове запросе доната: {e}'
            )
            raise e

    async def claim(
            self,
            donate_amount_wei: int,
            amount_wei: int,
            proof_addresses: List[str]
    ):
        try:
            extra_bytes, l0_fee = await self.get_extra_bytes(
                amount_wei=amount_wei
            )

            proof_bytes = [
                convert_to_bytes(addr) for addr in
                proof_addresses
            ]

            data = self.contract.encodeABI(
                fn_name='donateAndClaim',
                args=[
                    2,
                    donate_amount_wei,
                    amount_wei,
                    proof_bytes,
                    self.wallet,
                    extra_bytes,
                ]
            )

            contract_txn = self.build_tx(
                value=int(donate_amount_wei + l0_fee),
                data=data,
                to_address=self.provider.to_checksum_address(
                    self.contract_address
                ),
            )

            gas_price = self.provider.eth.gas_price
            gas_estimate = self.provider.eth.estimate_gas(contract_txn)
            total_gas_cost_wei = gas_price * gas_estimate

            native_balance_wei = self.provider.eth.get_balance(self.wallet)

            if native_balance_wei < total_gas_cost_wei:
                needed_amount_wei = total_gas_cost_wei - native_balance_wei
                logger.error(
                    f"{self.wallet} | Недостаточно нативок "
                    f"для клейма, ищу способ пополнить..."
                )
                raise NotEnoughtNative(needed_amount_wei)

            status, hash_ = self.sign_message(
                contract_txn=contract_txn
            )

            if status:
                logger.success(
                    f'{self.wallet} | Успешно заклеймили $ZRO\n'
                    f'{self.explorer}/{hash_}'
                )
            else:
                logger.error(
                    f'{self.wallet} | Ошибка при клейме $ZRO\n'
                    f'{self.explorer}/{hash_}')

            return status

        except Exception as e:
            traceback.print_exc()
            logger.error(f'{self.wallet} | Ошибка при клейме: {e}')

    async def get_extra_bytes(
            self,
            amount_wei=0,
            extra_bytes=b'',
            l0_fee=0
    ):
        if self.chain not in ['arbitrum']:
            function_selector = '0x73760a89'
            data = function_selector + encode_packed(
                ['uint256', 'uint256'],
                [CHAINS_DATA.get(
                    self.chain
                ).get('chain_0id'),
                 int(amount_wei)]
            ).hex()

            response = self.arb_provider.eth.call({
                'to': self.arb_provider.to_checksum_address(
                    self.arb_donate_address
                ),
                'data': data
            })

            gas_cost = int(eth_abi.decode(['uint256'], response)[0])
            adjusted_gas_cost_hex = hex(gas_cost)[2:].zfill(64)

            extra_bytes = f'000301002101{adjusted_gas_cost_hex}'

            l0_fee = await self.get_send_fee(
                amount_wei=amount_wei,
                extra_bytes=extra_bytes
            )
            l0_fee += gas_cost

        return HexBytes(extra_bytes), l0_fee

    async def get_send_fee(self, amount_wei, extra_bytes):
        data = '0x9baa23e6' + encode_packed(
            [
                'bytes12',
                'address',
                'uint256',
                'bytes32',
                'bytes32',
                'bytes',
                'bytes26'
            ],
            [
                b'\x00' * 12,
                self.wallet,
                int(amount_wei),
                b'\x00' * 31 + b'\x60',
                b'\x00' * 31 + b'\x26',
                HexBytes(extra_bytes),
                b'\x00' * 26
            ]
        ).hex()

        response = self.provider.eth.call({
            'to': self.contract.functions.claimContract().call(),
            'data': data
        })

        fee = int(eth_abi.decode(['uint256'], response)[0])

        return fee
