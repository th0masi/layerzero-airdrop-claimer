import aiosqlite
from core.enums import ClaimStatus


class Database:
    def __init__(self, db_name="claims.db"):
        self.db_name = db_name

    async def create_table(self):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS claims (
                    wallet_address TEXT PRIMARY KEY,
                    deposit_address TEXT,
                    allocation REAL,
                    claimed BOOLEAN,
                    claim_status TEXT
                )
            """)
            await db.commit()

    async def add_wallet(
            self,
            wallet_address,
            deposit_address,
            allocation=0.0,
            claimed=False,
            claim_status=ClaimStatus.PENDING
    ):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute("""
                INSERT OR REPLACE INTO claims (
                wallet_address, 
                deposit_address, 
                allocation, 
                claimed, 
                claim_status
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                wallet_address,
                deposit_address,
                allocation,
                claimed,
                claim_status.value
            ))
            await db.commit()

    async def update_claim_status(
            self,
            wallet_address,
            claim_status,
            allocation=None,
            claimed=None
    ):
        async with aiosqlite.connect(self.db_name) as db:
            if allocation is not None and claimed is not None:
                await db.execute("""
                    UPDATE claims
                    SET claim_status = ?, allocation = ?, claimed = ?
                    WHERE wallet_address = ?
                """, (claim_status.value, allocation, claimed, wallet_address))
            else:
                await db.execute("""
                    UPDATE claims
                    SET claim_status = ?
                    WHERE wallet_address = ?
                """, (claim_status.value, wallet_address))
            await db.commit()

    async def get_wallets_by_status(
            self,
            claim_status
    ):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT * FROM claims WHERE claim_status = ?
            """, (claim_status.value,)) as cursor:
                return await cursor.fetchall()

    async def get_all_wallets(self):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("SELECT * FROM claims") as cursor:
                return await cursor.fetchall()

    async def get_deposit_address(
            self,
            wallet_address
    ):
        async with aiosqlite.connect(self.db_name) as db:
            async with db.execute("""
                SELECT deposit_address FROM claims WHERE wallet_address = ?
            """, (wallet_address,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else None