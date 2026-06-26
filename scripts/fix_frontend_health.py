"""Check frontend healthcheck configuration and status."""
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

# Check docker-compose.yml for frontend healthcheck
print("=" * 60)
print("DOCKER-COMPOSE.YML HEALTHCHECK CONFIG")
print("=" * 60)
run("grep -A 10 'frontend:' /opt/onyxvpn/docker-compose.yml")

# Check frontend container detailed status
print("\n" + "=" * 60)
print("FRONTEND CONTAINER INSPECT")
print("=" * 60)
run("docker inspect onyxvpn-frontend --format '{{.State.Health.Status}} | ExitCode: {{.State.Health.Log[0].ExitCode}} | Output: {{.State.Health.Log[0].Output}}'")

# Check what's running inside frontend container
print("\n" + "=" * 60)
print("FRONTEND PROCESSES")
print("=" * 60)
run("docker exec onyxvpn-frontend ps aux 2>&1 | head -20")

# Check nginx config in frontend
print("\n" + "=" * 60)
print("FRONTEND NGINX CONFIG")
print("=" * 60)
run("docker exec onyxvpn-frontend cat /etc/nginx/conf.d/default.conf 2>&1 | head -30")

# Test frontend port directly
print("\n" + "=" * 60)
print("DIRECT FRONTEND TEST")
print("=" * 60)
run("curl -s -o /dev/null -w 'localhost:3000/ -> HTTP %{http_code}\\n' http://127.0.0.1:3000/")

# Frontend health endpoint
run("curl -s -o /dev/null -w 'localhost:3000/health -> HTTP %{http_code}\\n' http://127.0.0.1:3000/health 2>&1")

client.close()
