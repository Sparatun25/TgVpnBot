"""Rebuild backend image (bakes in patched migration) and run alembic upgrade."""
import sys
import io
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

# 1. Verify patched migration on host
print(">>> Verifying patched migration on host...")
cmd = "grep -n -E 'create_unique_constraint|create_foreign_key|referred_by_id' /opt/onyxvpn/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py"
stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
print(stdout.read().decode("utf-8", errors="replace"))

# 2. Rebuild backend
print("\n>>> Rebuilding backend image (this may take a few minutes)...")
cmd = "cd /opt/onyxvpn && /usr/local/bin/docker-compose build backend 2>&1 | tail -30"
stdin, stdout, stderr = client.exec_command(cmd, timeout=600, get_pty=True)
out = stdout.read().decode("utf-8", errors="replace")
print(out)

# 3. Restart backend
print("\n>>> Restarting backend...")
cmd = "cd /opt/onyxvpn && /usr/local/bin/docker-compose up -d backend 2>&1"
stdin, stdout, stderr = client.exec_command(cmd, timeout=60, get_pty=True)
out = stdout.read().decode("utf-8", errors="replace")
print(out)

# 4. Wait for container ready
print("\n>>> Waiting for backend to be ready...")
import time
time.sleep(5)

# 5. Run alembic upgrade head (with proper cwd)
print("\n>>> Running alembic upgrade head...")
cmd = "cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T -w /app backend alembic upgrade head 2>&1"
stdin, stdout, stderr = client.exec_command(cmd, timeout=120, get_pty=True)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
print(out)
if err.strip():
    print(f"[stderr] {err.rstrip()}")

client.close()
