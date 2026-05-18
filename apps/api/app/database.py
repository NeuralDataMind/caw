import asyncio
import random
import time
from fastapi import HTTPException, status

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
        
        # 1. State transition from OPEN to HALF-OPEN after cool-down
        if self.state == "OPEN" and (current_time - self.last_state_change) > self.recovery_time:
            self.state = "HALF-OPEN"
            self.last_state_change = current_time
            print("[CIRCUIT]: Transitioned to HALF-OPEN. Testing downstream dependency availability...")

        if self.state == "OPEN":
            raise CircuitBreakerOpenException("Circuit is OPEN. Load shedding active.")

        try:
            # Enforce strict execution timeout loop
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

# Global breaker instance protecting PostgreSQL pool sessions
db_breaker = ProductionCircuitBreaker()

# Simulated database connection write thread
async def db_insert_link(short_code: str, long_url: str):
    # In production, this executes: await database.execute(query)
    await asyncio.sleep(0.1)  # Simulate network hop latency
    return {"short_code": short_code, "long_url": long_url}

# Jittered retry mechanism helper for background workers or clients
async def execute_db_transaction_with_jitter(short_code: str, long_url: str):
    base_backoff = 1.0
    # Apply a randomized 500ms jitter window to prevent Thundering Herd collisions
    jitter = random.uniform(-0.25, 0.25) 
    sleep_duration = max(0.1, base_backoff + jitter)
    
    await asyncio.sleep(sleep_duration)
    return await db_breaker.call(db_insert_link, short_code, long_url)
# --- CACHE-ASIDE DATA PERSISTENCE PATCH ---
SIMULATED_DB = {}

async def db_get_long_url(short_code: str):
    """Simulates a database SELECT query to retrieve the original long URL."""
    await asyncio.sleep(0.1)  # Simulate database read network latency
    return SIMULATED_DB.get(short_code)

# Override original mock to write directly to the state machine
async def db_insert_link(short_code: str, long_url: str):
    await asyncio.sleep(0.1)  # Simulate database write network latency
    SIMULATED_DB[short_code] = long_url
    return {"short_code": short_code, "long_url": long_url}

# --- DYNAMIC DOMAIN STORAGE ENGINE ---
# Simulates a indexed SQL table 'whitelisted_domains'
DYNAMIC_DOMAINS_DB = {"localhost", "example.com", "api.caw.tech"}

async def db_add_whitelisted_domain(domain: str) -> bool:
    """Inserts a new approved domain target into the persistent database tier."""
    await asyncio.sleep(0.05)  # Simulate storage write latency
    DYNAMIC_DOMAINS_DB.add(domain.lower())
    return True

async def db_is_domain_whitelisted(domain: str) -> bool:
    """Performs an O(1) indexed lookup against the active domain whitelist."""
    await asyncio.sleep(0.05)  # Simulate storage read latency
    return domain.lower() in DYNAMIC_DOMAINS_DB
