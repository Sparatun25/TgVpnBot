"""Diagnose Docker socket permission issue."""
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
    print(f"\n>>> {cmd[:120]}{'...' if len(cmd) > 120 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    if out.strip():
        print(out.rstrip())
    if err.strip() and "WARN" not in err:
        print(f"[stderr] {err.rstrip()}")
    return out

# 1. Check recent logs to see if retry succeeded
print("=" * 60)
print("RECENT BACKEND LOGS (last 100 lines)")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose logs --tail=100 backend 2>&1 | grep -iE 'trial|amnezia|subscription|/health|trial|client_key|/api/' | tail -40")

# 2. Check Docker socket permissions on host
print("\n" + "=" * 60)
print("DOCKER SOCKET ON HOST")
print("=" * 60)
run("ls -la /var/run/docker.sock")
run("stat /var/run/docker.sock")
run("getent group docker")

# 3. Check docker-entrypoint.sh
print("\n" + "=" * 60)
print("DOCKER-ENTRYPOINT.SH (on server)")
print("=" * 60)
run("cat /opt/onyxvpn/docker-entrypoint.sh")

# 4. Check actual GID of docker socket and groups in container
print("\n" + "=" * 60)
print("INSIDE BACKEND CONTAINER")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend id appuser 2>&1")
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend cat /etc/group | grep -E 'docker|appuser'")
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend ls -la /var/run/docker.sock 2>&1")
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend stat /var/run/docker.sock 2>&1")

# 5. Test docker access from container
print("\n" + "=" * 60)
print("TEST DOCKER ACCESS FROM CONTAINER")
print("=" * 60)
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend sudo -u appuser docker ps 2>&1")
run("cd /opt/onyxvpn && /usr/local/bin/docker-compose exec -T backend sudo -u appuser docker exec amnezia-awg2 echo 'WORKS' 2>&1")

client.close()
