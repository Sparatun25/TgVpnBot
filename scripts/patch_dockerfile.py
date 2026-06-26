"""Patch Dockerfile.backend on server: replace docker-ce-cli with docker.io."""
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

# Read the file
sftp = client.open_sftp()
with sftp.open(REMOTE, "r") as f:
    content = f.read().decode("utf-8")
sftp.close()

# Replace the docker-ce-cli block with docker.io install via Debian mirror
old_block = """    && install -m 0755 -d /etc/apt/keyrings \\
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \\
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \\
    && apt-get update \\
    && apt-get install -y docker-ce-cli \\
    && rm -rf /var/lib/apt/lists/*"""

new_block = """    && apt-get install -y docker.io \\
    && rm -rf /var/lib/apt/lists/*"""

if old_block not in content:
    print("[FAIL] old_block not found in Dockerfile.backend")
    sys.exit(1)

new_content = content.replace(old_block, new_block)

# Write back
sftp = client.open_sftp()
with sftp.open(REMOTE, "w") as f:
    f.write(new_content.encode("utf-8"))
sftp.close()

print("[OK] patched Dockerfile.backend")
print("---verify---")
sftp = client.open_sftp()
with sftp.open(REMOTE, "r") as f:
    for i, line in enumerate(f.read().decode("utf-8").splitlines(), 1):
        if 28 <= i <= 35 or "docker" in line.lower():
            print(f"{i}: {line}")
sftp.close()

client.close()
