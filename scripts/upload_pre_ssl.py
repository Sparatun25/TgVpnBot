"""Upload pre-SSL nginx config (HTTP only, no SSL yet)."""
import paramiko

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

LOCAL = "c:/Users/spara/Desktop/TgVpnBot/docker/nginx-host-pre-ssl.conf"
REMOTE = "/etc/nginx/sites-available/onyxvpn"

with open(LOCAL, "rb") as f:
    data = f.read().decode("utf-8")
escaped = data.replace("\\", "\\\\").replace("$", "\\$").replace("`", "\\`")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

cmd = f"cat > {REMOTE} <<'NGINX_EOF'\n{escaped}\nNGINX_EOF\n"
client.exec_command(cmd, timeout=30)
client.close()
print("[ok] uploaded pre-ssl config")
