"""Upload nginx config via stdin heredoc (works around paramiko SFTP quirks)."""
import sys
import paramiko

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

LOCAL = "c:/Users/spara/Desktop/TgVpnBot/docker/nginx-host.conf"
REMOTE = "/etc/nginx/sites-available/onyxvpn"

with open(LOCAL, "rb") as f:
    data = f.read().decode("utf-8")

# Escape for heredoc-safe use: backticks, $, \
escaped = data.replace("\\", "\\\\").replace("$", "\\$").replace("`", "\\`")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

cmd = f"cat > {REMOTE} <<'NGINX_EOF'\n{escaped}\nNGINX_EOF\n"
stdin, stdout, stderr = client.exec_command(cmd, timeout=30, get_pty=True)
out = stdout.read().decode("utf-8", errors="replace")
err = stderr.read().decode("utf-8", errors="replace")
code = stdout.channel.recv_exit_status()
print(f"[exit {code}]")
if out:
    print(out)
if err:
    print(f"[stderr] {err}")

# Verify
stdin, stdout, stderr = client.exec_command(f"ls -la {REMOTE} && head -5 {REMOTE}", timeout=10)
print("---verify---")
print(stdout.read().decode("utf-8", errors="replace"))

client.close()
