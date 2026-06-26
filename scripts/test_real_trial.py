"""Test that backend can actually create VPN keys now (real trial activation)."""
import sys
import io
import paramiko
import json
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=60):
    print(f"\n>>> {cmd[:120]}{'...' if len(cmd) > 120 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip() and "WARN" not in err:
        print(f"[stderr] {err.rstrip()}")
    return out

# 1. Verify Docker socket access works from container
print("=" * 60)
print("VERIFY DOCKER ACCESS (post-fix)")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend id appuser 2>&1")
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend getent group docker")
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend stat -c 'Socket GID: %g' /var/run/docker.sock")
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend docker ps --format '{{.Names}} - {{.Status}}' 2>&1")

# 2. Test trial activation directly via API (using existing user from DB)
print("\n" + "=" * 60)
print("TEST TRIAL ACTIVATION VIA API")
print("=" * 60)
# Get user from DB
user_result = run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T postgres psql -U postgres -d onyxvpn -t -A -c 'SELECT id, tg_id FROM users LIMIT 1;'")
print(f"User from DB: {user_result.strip()}")

# We can't easily forge Telegram initData from here, so let's test the
# services/amnezia.py logic directly by exec-ing into the container
print("\n--- Testing amnezia.py create_client_key directly ---")
test_cmd = """cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend python -c '
import asyncio
import sys
sys.path.insert(0, "/app")
from services.amnezia import AmneziaService

async def test():
    svc = AmneziaService()
    try:
        result = await svc.create_client_key("Test User 99999")
        print("SUCCESS:")
        print(f"  client_pub_key: {result.get(\"client_pub_key\", \"\")[:30]}...")
        print(f"  vpn_url length: {len(result.get(\"vpn_url\", \"\"))}")
        print(f"  client_ip: {result.get(\"client_ip\", \"\")}")
        return result
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

result = asyncio.run(test())
' 2>&1"""
run(test_cmd, timeout=120)

# 3. Check DB after test
print("\n" + "=" * 60)
print("DB STATE AFTER TEST")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T postgres psql -U postgres -d onyxvpn -c 'SELECT id, user_id, uuid, plan_type, expires_at, is_active, created_at FROM subscriptions ORDER BY id;'")

client.close()
