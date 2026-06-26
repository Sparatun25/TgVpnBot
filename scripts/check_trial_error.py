"""Check backend logs for trial activation errors."""
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

# Get last 200 lines of backend logs to see trial activation errors
print("=" * 60)
print("BACKEND LOGS (last 200 lines)")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose logs --tail=200 backend")

# Search for trial-related errors specifically
print("\n" + "=" * 60)
print("TRIAL/AMNEZIA RELATED LOGS")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose logs backend 2>&1 | grep -iE 'trial|amnezia|subscription|error|exception|traceback' | tail -50")

client.close()
