"""Check backend logs for the FIRST trial attempt error (before retry succeeded)."""
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

def run(cmd, timeout=60):
    print(f"\n>>> {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip() and "WARN" not in err:
        print(f"[stderr] {err.rstrip()}")
    return out

# Get full backend logs to see the trial activation sequence
print("=" * 60)
print("FULL BACKEND LOGS (last 500 lines)")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose logs --tail=500 backend 2>&1")

client.close()
