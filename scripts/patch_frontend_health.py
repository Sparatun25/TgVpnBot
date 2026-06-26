"""Fix frontend healthcheck: use 127.0.0.1 instead of localhost (IPv6 issue)."""
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

# 1. Patch docker-compose.yml
print("=" * 60)
print("PATCHING DOCKER-COMPOSE.YML")
print("=" * 60)

old_check = 'test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost/"]'
new_check = 'test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://127.0.0.1/"]'

sftp = client.open_sftp()
with sftp.open("/opt/onyxvpn/docker-compose.yml", "r") as f:
    content = f.read().decode("utf-8")

if old_check in content:
    new_content = content.replace(old_check, new_check)
    with sftp.open("/opt/onyxvpn/docker-compose.yml", "w") as f:
        f.write(new_content.encode("utf-8"))
    print("[OK] docker-compose.yml patched")
else:
    print("[WARN] old healthcheck not found in docker-compose.yml - may already be patched")

sftp.close()

# 2. Patch Dockerfile.frontend (for consistency on future builds)
print("\n" + "=" * 60)
print("PATCHING DOCKERFILE.FRONTEND")
print("=" * 60)

old_dockerfile_check = "CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1"
new_dockerfile_check = "CMD wget --no-verbose --tries=1 --spider http://127.0.0.1/ || exit 1"

sftp = client.open_sftp()
with sftp.open("/opt/onyxvpn/Dockerfile.frontend", "r") as f:
    content = f.read().decode("utf-8")

if old_dockerfile_check in content:
    new_content = content.replace(old_dockerfile_check, new_dockerfile_check)
    with sftp.open("/opt/onyxvpn/Dockerfile.frontend", "w") as f:
        f.write(new_content.encode("utf-8"))
    print("[OK] Dockerfile.frontend patched")
else:
    print("[WARN] old healthcheck not found in Dockerfile.frontend - may already be patched")

sftp.close()

# 3. Restart frontend to pick up new healthcheck
print("\n" + "=" * 60)
print("RESTARTING FRONTEND")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose restart frontend 2>&1")

# 4. Wait and check status
import time
time.sleep(10)

print("\n" + "=" * 60)
print("FRONTEND STATUS AFTER FIX")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose ps frontend")

print("\n" + "=" * 60)
print("FRONTEND HEALTH (JSON)")
print("=" * 60)
run("docker inspect onyxvpn-frontend | python3 -c 'import json, sys; d=json.load(sys.stdin); h=d[0].get(\"State\",{}).get(\"Health\",{}); print(\"Status:\", h.get(\"Status\")); print(\"FailingStreak:\", h.get(\"FailingStreak\")); log=h.get(\"Log\",[]); print(\"Last log:\", json.dumps(log[-1] if log else {}, indent=2))'")

client.close()
