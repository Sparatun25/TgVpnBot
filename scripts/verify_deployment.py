"""Verify migration success and deployment state."""
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

# 1. Check alembic current version
print("=" * 60)
print("ALEMBIC STATUS")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T -w /app backend alembic current 2>&1")

# 2. List tables in DB
print("\n" + "=" * 60)
print("DATABASE TABLES")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T postgres psql -U postgres -d onyxvpn -c '\\dt'")

# 3. Check container status
print("\n" + "=" * 60)
print("CONTAINER STATUS")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose ps")

# 4. Check backend logs for errors
print("\n" + "=" * 60)
print("BACKEND LOGS (last 50 lines)")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose logs --tail=50 backend")

# 5. Test API health
print("\n" + "=" * 60)
print("API HEALTH")
print("=" * 60)
run("curl -s -o /dev/null -w 'HTTP %{http_code} - %{time_total}s\\n' https://onyxvpnbot.ru/api/profile")

# 6. Check frontend
print("\n" + "=" * 60)
print("FRONTEND CHECK")
print("=" * 60)
run("curl -s -o /dev/null -w 'HTTP %{http_code} - %{time_total}s\\n' https://onyxvpnbot.ru/")

# 7. Check Amnezia container connectivity
print("\n" + "=" * 60)
print("AMNEZIA CONTAINER")
print("=" * 60)
run("docker ps -a --filter name=amnezia --format '{{.Names}} - {{.Status}}'")

# 8. Verify bot can be polled
print("\n" + "=" * 60)
print("BOT TOKEN CHECK")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose logs --tail=20 backend 2>&1 | grep -iE 'telegram|polling|bot' | head -10")

client.close()
