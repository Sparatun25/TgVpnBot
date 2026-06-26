"""Force recreate frontend to pick up new healthcheck."""
import sys
import io
import paramiko
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

def run(cmd, timeout=30):
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(f"[stderr] {err.rstrip()}")
    return out

# Force recreate frontend to apply new healthcheck
print("=" * 60)
print("FORCE RECREATE FRONTEND")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose up -d --force-recreate --no-deps frontend 2>&1")

# Wait for healthcheck to run
print("\n>>> Waiting 15s for healthcheck to run...")
time.sleep(15)

print("\n" + "=" * 60)
print("FRONTEND STATUS AFTER RECREATE")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose ps frontend")

print("\n" + "=" * 60)
print("FRONTEND HEALTH (JSON)")
print("=" * 60)
run("docker inspect onyxvpn-frontend | python3 -c 'import json, sys; d=json.load(sys.stdin); h=d[0].get(\"State\",{}).get(\"Health\",{}); print(\"Status:\", h.get(\"Status\")); print(\"FailingStreak:\", h.get(\"FailingStreak\")); log=h.get(\"Log\",[]); print(\"Last log:\", json.dumps(log[-1] if log else {}, indent=2))'")

# Final check - all containers
print("\n" + "=" * 60)
print("ALL CONTAINERS")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose ps")

client.close()
