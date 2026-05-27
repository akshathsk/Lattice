"""
Knowledge Graph Lattice — Startup Script
-----------------------------------------
Run this once before starting the backend server.

What it does:
  1. Starts FalkorDB, PostgreSQL, and MongoDB Docker containers (if not running)
  2. Waits for all three to be healthy
  3. Seeds PostgreSQL with structured contract data (idempotent)
  4. Seeds MongoDB with unstructured legal documents (idempotent)
  5. Initialises FalkorDB vector indexes and schema
  6. Prints a ready summary

Usage:
  python backend/startup.py
  python backend/startup.py --no-docker   # skip Docker management (containers already running)
  python backend/startup.py --no-seed     # skip PostgreSQL seeding
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path

# ── load .env if present ──────────────────────────────────────────────────────
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"  Loaded env from {env_file}")

# ── config ────────────────────────────────────────────────────────────────────
DOCKER_HOST     = os.getenv("DOCKER_HOST", f"unix://{Path.home()}/.docker/run/docker.sock")
FALKORDB_HOST   = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT   = int(os.getenv("FALKORDB_PORT", 6379))
PG_HOST         = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT         = int(os.getenv("POSTGRES_PORT", 5432))
PG_DB           = os.getenv("POSTGRES_DB", "contracts")
PG_USER         = os.getenv("POSTGRES_USER", "lattice")
PG_PASS         = os.getenv("POSTGRES_PASSWORD", "lattice123")
MONGO_HOST      = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT      = int(os.getenv("MONGO_PORT", 27017))
MONGO_DB        = os.getenv("MONGO_DB", "contracts_docs")
SEED_ON_STARTUP = os.getenv("SEED_ON_STARTUP", "true").lower() == "true"
CONNECTORS_DIR  = Path(__file__).parent / "connectors"

DOCKER_ENV = {**os.environ, "DOCKER_HOST": DOCKER_HOST}

# ── helpers ───────────────────────────────────────────────────────────────────

def banner(text: str):
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")

def ok(msg: str):   print(f"  ✓  {msg}")
def err(msg: str):  print(f"  ✗  {msg}")
def info(msg: str): print(f"  ·  {msg}")

def run(cmd: str, capture=True) -> tuple[int, str]:
    result = subprocess.run(
        cmd, shell=True, capture_output=capture,
        text=True, env=DOCKER_ENV
    )
    return result.returncode, (result.stdout + result.stderr).strip()

def container_running(name: str) -> bool:
    code, out = run(f'docker ps --filter name=^{name}$ --filter status=running --format "{{{{.Names}}}}"')
    return name in out

def wait_for(name: str, check_fn, timeout=30, interval=2):
    info(f"Waiting for {name} to be ready ...")
    for _ in range(timeout // interval):
        if check_fn():
            return True
        time.sleep(interval)
    return False

# ── step 1: Docker containers ─────────────────────────────────────────────────

def ensure_falkordb():
    banner("FalkorDB")
    if container_running("falkordb"):
        ok("Container already running")
        return True

    info("Starting falkordb/falkordb container ...")
    code, out = run(
        "docker run -d --name falkordb "
        f"-p {FALKORDB_PORT}:6379 -p 7687:7687 "
        "falkordb/falkordb:latest"
    )
    if code != 0:
        # container may exist but be stopped — try starting it
        code2, out2 = run("docker start falkordb")
        if code2 != 0:
            err(f"Failed to start FalkorDB: {out}\n{out2}")
            return False

    def falkordb_ready():
        try:
            import falkordb as fdb
            db = fdb.FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
            db.select_graph("__ping__").query("RETURN 1")
            return True
        except Exception:
            return False

    if wait_for("FalkorDB", falkordb_ready):
        ok(f"FalkorDB ready at {FALKORDB_HOST}:{FALKORDB_PORT}")
        return True
    else:
        err("FalkorDB did not become ready in time")
        return False


def ensure_postgres():
    banner("PostgreSQL")
    if container_running("lattice-postgres"):
        ok("Container already running")
        return True

    info("Starting postgres:16-alpine container ...")
    code, out = run(
        "docker run -d --name lattice-postgres "
        f"-e POSTGRES_DB={PG_DB} "
        f"-e POSTGRES_USER={PG_USER} "
        f"-e POSTGRES_PASSWORD={PG_PASS} "
        f"-p {PG_PORT}:5432 "
        "postgres:16-alpine"
    )
    if code != 0:
        code2, _ = run("docker start lattice-postgres")
        if code2 != 0:
            err(f"Failed to start PostgreSQL: {out}")
            return False

    def pg_ready():
        try:
            import psycopg2
            conn = psycopg2.connect(
                host=PG_HOST, port=PG_PORT,
                dbname=PG_DB, user=PG_USER, password=PG_PASS,
                connect_timeout=2
            )
            conn.close()
            return True
        except Exception:
            return False

    if wait_for("PostgreSQL", pg_ready, timeout=40):
        ok(f"PostgreSQL ready at {PG_HOST}:{PG_PORT}/{PG_DB}")
        return True
    else:
        err("PostgreSQL did not become ready in time")
        return False

# ── step 2: MongoDB container ─────────────────────────────────────────────────

def ensure_mongo():
    banner("MongoDB")
    if container_running("lattice-mongo"):
        ok("Container already running")
        return True

    info("Starting mongo:7.0 container ...")
    code, out = run(
        "docker run -d --name lattice-mongo "
        f"-p {MONGO_PORT}:27017 "
        "mongo:7.0"
    )
    if code != 0:
        code2, _ = run("docker start lattice-mongo")
        if code2 != 0:
            err(f"Failed to start MongoDB: {out}")
            return False

    def mongo_ready():
        try:
            import pymongo
            client = pymongo.MongoClient(
                host=MONGO_HOST, port=MONGO_PORT,
                serverSelectionTimeoutMS=2000
            )
            client.server_info()
            client.close()
            return True
        except Exception:
            return False

    if wait_for("MongoDB", mongo_ready, timeout=30):
        ok(f"MongoDB ready at {MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}")
        return True
    else:
        err("MongoDB did not become ready in time")
        return False


# ── step 3: seed MongoDB ──────────────────────────────────────────────────────

def seed_mongo():
    banner("Seeding MongoDB")
    import pymongo
    import importlib.util

    seed_file = CONNECTORS_DIR / "mongo" / "seed.py"
    if not seed_file.exists():
        err(f"Seed file not found: {seed_file}")
        return False

    try:
        # dynamically import seed_mongo.py and call its seed() function
        spec = importlib.util.spec_from_file_location("mongo_seed", seed_file)
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        client = pymongo.MongoClient(host=MONGO_HOST, port=MONGO_PORT)
        db     = client[MONGO_DB]
        results = mod.seed(db)
        client.close()

        for coll, res in results.items():
            if res.get("skipped"):
                ok(f"{coll}: already seeded ({res['count']} docs)")
            else:
                ok(f"{coll}: inserted {res['count']} docs")

        return True

    except Exception as e:
        err(f"MongoDB seeding failed: {e}")
        return False


# ── step 4: seed PostgreSQL ───────────────────────────────────────────────────

def seed_postgres():
    banner("Seeding PostgreSQL")
    import psycopg2

    sql_file = CONNECTORS_DIR / "postgres" / "seed.sql"
    if not sql_file.exists():
        err(f"Seed file not found: {sql_file}")
        return False

    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT,
            dbname=PG_DB, user=PG_USER, password=PG_PASS
        )
        conn.autocommit = True
        cursor = conn.cursor()

        sql = sql_file.read_text()
        cursor.execute(sql)

        # print row counts
        for table in ["parties", "contracts", "contract_parties", "clauses", "obligations", "regulations"]:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            ok(f"{table}: {count} rows")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        err(f"Seeding failed: {e}")
        return False

# ── step 3: initialise FalkorDB indexes ──────────────────────────────────────

def init_falkordb():
    banner("Initialising FalkorDB")
    import falkordb as fdb

    try:
        db = fdb.FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        g  = db.select_graph("lattice")

        # chunk vector index (768-dim cosine — sentence-transformers default)
        try:
            g.query("""
                CREATE VECTOR INDEX FOR (c:Chunk) ON (c.embedding)
                OPTIONS {dimension: 768, similarityFunction: 'cosine'}
            """)
            ok("Chunk vector index created (dim=768, cosine)")
        except Exception as e:
            if "already indexed" in str(e).lower():
                ok("Chunk vector index already exists")
            else:
                raise

        # entity vector index (for dedup)
        try:
            g.query("""
                CREATE VECTOR INDEX FOR (e:Entity) ON (e.embedding)
                OPTIONS {dimension: 768, similarityFunction: 'cosine'}
            """)
            ok("Entity vector index created (dim=768, cosine)")
        except Exception as e:
            if "already indexed" in str(e).lower():
                ok("Entity vector index already exists")
            else:
                raise

        # initialise schema tracking key in Redis
        import redis
        r = redis.Redis(host=FALKORDB_HOST, port=FALKORDB_PORT)
        if not r.exists("lattice:schema:labels"):
            r.sadd("lattice:schema:labels",
                   "Person", "Organization", "Location",
                   "Product", "Event", "Concept", "Date", "Technology",
                   # legal domain seeds
                   "Contract", "Clause", "Obligation", "Regulation", "Party")
            ok("Schema label seed set initialised")
        else:
            ok("Schema label seed set already exists")

        if not r.exists("lattice:schema:rel_types"):
            r.sadd("lattice:schema:rel_types",
                   "PARTY_TO", "GOVERNS", "REFERENCES", "OBLIGATES",
                   "SIGNED_BY", "MENTIONS", "RELATED_TO")
            ok("Schema relation type seed set initialised")
        else:
            ok("Schema relation type seed set already exists")

        ok(f"FalkorDB graph 'lattice' ready at {FALKORDB_HOST}:{FALKORDB_PORT}")
        return True

    except Exception as e:
        err(f"FalkorDB init failed: {e}")
        return False

# ── step 4: summary ───────────────────────────────────────────────────────────

def print_summary(results: dict):
    banner("Startup Summary")
    all_ok = all(results.values())
    for step, status in results.items():
        symbol = "✓" if status else "✗"
        print(f"  {symbol}  {step}")
    print()
    if all_ok:
        print("  🚀  All systems ready. You can now start the backend server:")
        print("       uvicorn backend.main:app --reload")
    else:
        print("  ⚠️   Some steps failed. Check the output above.")
    print()

# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Lattice startup script")
    parser.add_argument("--no-docker", action="store_true", help="Skip Docker container management")
    parser.add_argument("--no-seed",   action="store_true", help="Skip PostgreSQL seeding")
    args = parser.parse_args()

    print("\n  Knowledge Graph Lattice — Startup")

    results = {}

    if not args.no_docker:
        results["FalkorDB container"]   = ensure_falkordb()
        results["PostgreSQL container"] = ensure_postgres()
        results["MongoDB container"]    = ensure_mongo()
    else:
        info("Skipping Docker management (--no-docker)")

    if not args.no_seed and SEED_ON_STARTUP:
        results["PostgreSQL seed"] = seed_postgres()
        results["MongoDB seed"]    = seed_mongo()
    else:
        info("Skipping seed (--no-seed or SEED_ON_STARTUP=false)")

    results["FalkorDB indexes & schema"] = init_falkordb()

    print_summary(results)
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
