"""Corrected backend test: create_client_key(user_id, is_trial, plan_type=None)."""
import sys
import io
import paramiko
import re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)


def run(cmd, timeout=120):
    print(f"\n>>> {cmd[:140]}{'...' if len(cmd) > 140 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    print(out)
    return out


# 1. Get real user_id from DB
print("=" * 60)
print("GET USER_ID FROM DB")
print("=" * 60)
user_cmd = (
    "cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T postgres "
    "psql -U postgres -d onyxvpn -t -A -c 'SELECT id FROM users LIMIT 1;'"
)
out = run(user_cmd, timeout=30)
real_user_id = None
for line in out.splitlines():
    stripped = line.strip()
    if stripped.isdigit():
        real_user_id = int(stripped)
        break
print(f"Real user_id from DB: {real_user_id}")

if real_user_id is None:
    print("No users in DB, aborting")
    client.close()
    sys.exit(1)

# 2. Call create_client_key — write Python script to a file on server, then exec it
print("\n" + "=" * 60)
print("TEST create_client_key(user_id, is_trial=True)")
print("=" * 60)

# Use SFTP to write a file, then docker cp it into the container
# Actually, easier: use stdin pipe via heredoc
python_body = """
import asyncio
import sys
sys.path.insert(0, "/app")
from services.amnezia import create_client_key

USER_ID = __UID__

async def test():
    try:
        result = await create_client_key(USER_ID, is_trial=True)
        vpn_url, client_pub = result
        print("===SUCCESS===")
        print(f"vpn_url_prefix={vpn_url[:30]}")
        print(f"vpn_url_length={len(vpn_url)}")
        print(f"client_pub={client_pub}")
        return client_pub
    except Exception as e:
        print(f"===FAILED===: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

cp = asyncio.run(test())
print("===END===")
print(cp or "NONE")
""".replace("__UID__", str(real_user_id))

# Write the script to /tmp on server, then docker cp into container
sftp = client.open_sftp()
remote_script_path = "/tmp/trial_test_inner.py"
with sftp.file(remote_script_path, "w") as f:
    f.write(python_body)
sftp.close()

# Copy into backend container and run
test_cmd = (
    f"docker cp /tmp/trial_test_inner.py onyxvpn-backend:/tmp/trial_test_inner.py && "
    f"cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend python /tmp/trial_test_inner.py 2>&1"
)
out = run(test_cmd, timeout=120)

# Parse client_pub from output (WireGuard pubkey is base64, ~44 chars)
client_pub = None
for line in out.splitlines():
    line = line.strip()
    if re.match(r"^[A-Za-z0-9+/]{43}=*$", line):
        client_pub = line
        break
print(f"\n>>> Captured client_pub: {client_pub}")

# 3. Check DB after test
print("\n" + "=" * 60)
print("DB STATE AFTER TEST")
print("=" * 60)
db_cmd = (
    "cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T postgres "
    "psql -U postgres -d onyxvpn -c "
    "'SELECT id, user_id, uuid, plan_type, expires_at, is_active, created_at FROM subscriptions ORDER BY id;'"
)
run(db_cmd, timeout=30)

# 4. Cleanup
if client_pub:
    print("\n" + "=" * 60)
    print("CLEANUP: revoke test key")
    print("=" * 60)
    cleanup_body = """
import asyncio
import sys
sys.path.insert(0, "/app")
from services.amnezia import revoke_client_key

PUB = "__PUB__"

async def cleanup():
    ok = await revoke_client_key(PUB, source="api", reason="test_cleanup")
    print(f"Revoke result: {ok}")

asyncio.run(cleanup())
""".replace("__PUB__", client_pub)

    sftp = client.open_sftp()
    with sftp.file("/tmp/cleanup_inner.py", "w") as f:
        f.write(cleanup_body)
    sftp.close()

    cleanup_cmd = (
        "docker cp /tmp/cleanup_inner.py onyxvpn-backend:/tmp/cleanup_inner.py && "
        "cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend python /tmp/cleanup_inner.py 2>&1"
    )
    run(cleanup_cmd, timeout=60)
else:
    print("\n>>> No client_pub captured, skipping cleanup")

# Cleanup temp files
run("rm -f /tmp/trial_test_inner.py /tmp/cleanup_inner.py", timeout=10)

client.close()
