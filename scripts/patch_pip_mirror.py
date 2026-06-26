"""Add pip mirror configuration to Dockerfile.backend (Russian network)."""
import sys
import io
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

REMOTE = "/opt/onyxvpn/Dockerfile.backend"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

sftp = client.open_sftp()
with sftp.open(REMOTE, "r") as f:
    content = f.read().decode("utf-8")
sftp.close()

# Insert pip mirror config before both pip install lines
# Pattern: from line "RUN pip install" we want to inject a pip.conf creation first
pip_conf_block = """# Use Aliyun pip mirror (Russian network can't reach files.pythonhosted.org)
RUN mkdir -p /etc && printf '[global]\\nindex-url = https://mirrors.aliyun.com/pypi/simple/\\ntrusted-host = mirrors.aliyun.com\\n' > /etc/pip.conf

"""

# Insert before any "RUN pip install" line
new_content = content.replace("RUN pip install --no-cache-dir --upgrade pip", pip_conf_block + "RUN pip install --no-cache-dir --upgrade pip")

if new_content == content:
    print("[FAIL] no pip install line found to patch")
    sys.exit(1)

sftp = client.open_sftp()
with sftp.open(REMOTE, "w") as f:
    f.write(new_content.encode("utf-8"))
sftp.close()

print("[OK] patched Dockerfile.backend with pip mirror")
# Verify
sftp = client.open_sftp()
with sftp.open(REMOTE, "r") as f:
    for i, line in enumerate(f.read().decode("utf-8").splitlines(), 1):
        if "pip" in line.lower() or "mirror" in line.lower() or "aliyun" in line.lower():
            print(f"{i}: {line}")
sftp.close()
client.close()
