"""Deploy patched migration to container - v2 with persistent cd."""
import sys
import io
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

REMOTE_FILE = "/opt/onyxvpn/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

# Read patched file from host
with open("c:/Users/spara/Desktop/TgVpnBot/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py", "rb") as f:
    new_content = f.read().decode("utf-8")
escaped = new_content.replace("\\", "\\\\").replace("$", "\\$").replace("`", "\\`")

# 1. Write file to container using heredoc (avoiding stdin redirection issues)
write_cmd = f"""bash -c '
DC=/usr/local/bin/docker-compose
cd /opt/onyxvpn
$DC exec -T backend sh << INNER_EOF
cat > /app/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py << MIG_EOF
{escaped}
MIG_EOF
rm -rf /app/migrations/versions/__pycache__
wc -l /app/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py
grep -c create_unique /app/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py
INNER_EOF
'"""

print(">>> Writing patched migration into container...")
stdin, stdout, stderr = client.exec_command(write_cmd, timeout=60, get_pty=True)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
if out.strip():
    print(out.rstrip())
if err.strip():
    print(f"[stderr] {err.rstrip()}")

# 2. Run alembic upgrade head
print("\n>>> Running alembic upgrade head...")
alembic_cmd = "cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend alembic upgrade head 2>&1"
stdin, stdout, stderr = client.exec_command(alembic_cmd, timeout=60, get_pty=True)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
if out.strip():
    print(out.rstrip())
if err.strip():
    print(f"[stderr] {err.rstrip()}")

client.close()
