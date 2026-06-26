"""Get full frontend section of docker-compose.yml and Dockerfile."""
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

# Full docker-compose.yml
print("=" * 60)
print("FULL DOCKER-COMPOSE.YML")
print("=" * 60)
run("cat /opt/onyxvpn/docker-compose.yml")

# Full Dockerfile.frontend
print("\n" + "=" * 60)
print("DOCKERFILE.FRONTEND")
print("=" * 60)
run("cat /opt/onyxvpn/Dockerfile.frontend")

# Get health status properly
print("\n" + "=" * 60)
print("FRONTEND HEALTH STATUS (JSON)")
print("=" * 60)
run("docker inspect onyxvpn-frontend | python3 -c 'import json, sys; d=json.load(sys.stdin); h=d[0].get(\"State\",{}).get(\"Health\",{}); print(json.dumps(h, indent=2))'")

client.close()
