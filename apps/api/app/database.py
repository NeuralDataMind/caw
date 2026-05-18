import asyncio
import random
import time
import asyncpg
from app.config import settings

class CircuitBreakerOpenException(Exception):
    pass

class ProductionCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_time: int = 10):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.failure_count = 0
        self.last_state_change = time.time()

    async def call(self, func, *args, **kwargs):
        current_time = time.time()
        
        if self.state == "OPEN" and (current_time - self.last_state_change) > self.recovery_time:
            self.state = "HALF-OPEN"
            self.last_state_change = current_time
            print("[CIRCUIT]: Transitioned to HALF-OPEN. Testing downstream database availability...")

        if self.state == "OPEN":
            raise CircuitBreakerOpenException("Circuit is OPEN. Load shedding active.")

        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=1.0)
        except (asyncio.TimeoutError, Exception) as e:
            self.handle_failure()
            raise e

    def handle_failure(self):
        self.failure_count += 1
        print(f"[CIRCUIT FAILURE]: Count = {self.failure_count}")
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.last_state_change = time.time()
            print("[CIRCUIT CRITICAL]: Failure threshold breached. Circuit TRIPPED OPEN.")

    def handle_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

db_breaker = ProductionCircuitBreaker()

# --- REAL ASYNC POSTGRESQL CONNECTION POOL POINTER ---
DB_POOL = None

async def get_db_pool():
    """Initializes and returns a reusable asynchronous connection pool thread matrix."""
    global DB_POOL
    if DB_POOL is None:
        # Open connection pool using validated environment variables
        DB_POOL = await asyncpg.create_pool(
            settings.DATABASE_URL, 
            min_size=5, 
            max_size=20
        )
        
        # Automatic Table Creation Execution Block (DDL Bootstrapper)
        async with DB_POOL.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS links (
                    short_code VARCHAR(12) PRIMARY KEY,
                    long_url TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS whitelisted_domains (
                    domain VARCHAR(255) PRIMARY KEY
                );
                -- Seed core default entries if table is completely empty
                INSERT INTO whitelisted_domains (domain) 
                VALUES ('localhost'), ('example.com'), ('api.caw.tech')
                ON CONFLICT DO NOTHING;
            """)
            print("[DATABASE INFRASTRUCTURE]: PostgreSQL schemas verified and seeded successfully.")
    return DB_POOL

# --- PRODUCTION READ / WRITE CONTROLLERS ---

async def db_get_long_url(short_code: str) -> str or None: # type: ignore
    """Queries live PostgreSQL table for matching token mappings."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT long_url FROM links WHERE short_code = $1", 
            short_code
        )

async def db_insert_link(short_code: str, long_url: str):
    """Commits a new shortened link record directly to persistent disk storage."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO links (short_code, long_url) VALUES ($1, $2) ON CONFLICT (short_code) DO NOTHING",
            short_code, long_url
        )
    return {"short_code": short_code, "long_url": long_url}

async def db_add_whitelisted_domain(domain: str) -> bool:
    """Inserts a new approved enterprise domain row dynamically at runtime."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO whitelisted_domains (domain) VALUES ($1) ON CONFLICT DO NOTHING",
            domain.lower().strip()
        )
    return True

async def db_is_domain_whitelisted(domain: str) -> bool:
    """Runs a highly indexed lookup verifying domain permission records."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchval(
            "SELECT domain FROM whitelisted_domains WHERE domain = $1",
            domain.lower().strip()
        )
        return record is not None

async def execute_db_transaction_with_jitter(short_code: str, long_url: str):
    base_backoff = 1.0
    jitter = random.uniform(-0.25, 0.25) 
    sleep_duration = max(0.1, base_backoff + jitter)
    await asyncio.sleep(sleep_duration)
    return await db_breaker.call(db_insert_link, short_code, long_url)
