"""Check if retry actually created a subscription record."""
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
    print(f"\n>>> {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip() and "WARN" not in err:
        print(f"[stderr] {err.rstrip()}")
    return out

# Check users and subscriptions tables
print("=" * 60)
print("USERS TABLE")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T postgres psql -U postgres -d onyxvpn -c 'SELECT id, tg_id, username, balance, created_at FROM users ORDER BY id;'")

print("\n" + "=" * 60)
print("SUBSCRIPTIONS TABLE")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T postgres psql -U postgres -d onyxvpn -c 'SELECT id, user_id, uuid, plan_type, expires_at, is_active, created_at FROM subscriptions ORDER BY id;'")

# Check amnezia container clients
print("\n" + "=" * 60)
print("AMNEZIA CLIENTS LIST")
print("=" * 60)
run("docker exec amnezia-awg2 cat /opt/amnezia/awg/clientsTable 2>&1 | head -20")

# Most recent logs
print("\n" + "=" * 60)
print("MOST RECENT BACKEND LOGS")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose logs --tail=30 backend 2>&1")

client.close()
