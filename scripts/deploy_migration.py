"""Copy patched migration into running container, clear __pycache__, re-run alembic."""
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

cmds = [
    "cd /opt/onyxvpn",
    "/usr/local/bin/docker-compose exec -T backend rm -f /app/migrations/versions/__pycache__/2026-06-26_1114-e71938e50ad2_initial_schema.cpython-312.pyc 2>/dev/null; true",
    "/usr/local/bin/docker-compose exec -T backend rm -rf /app/migrations/versions/__pycache__",
    # Copy patched migration into container
    "HOST_FILE=/opt/onyxvpn/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py",
    "/usr/local/bin/docker-compose exec -T backend sh -c 'cat > /app/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py' < /opt/onyxvpn/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py",
    # Verify
    "/usr/local/bin/docker-compose exec -T backend wc -l /app/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py",
    "/usr/local/bin/docker-compose exec -T backend grep -c create_unique /app/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py",
    # Run migration
    "/usr/local/bin/docker-compose exec -T backend alembic upgrade head 2>&1 | tail -10",
]

for cmd in cmds:
    print(f"\n>>> {cmd[:80]}{'...' if len(cmd) > 80 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=60, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(f"[stderr] {err.rstrip()}")

client.close()
