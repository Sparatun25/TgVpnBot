"""SSH helper for deployment to 72.56.96.52.

Usage:
    python scripts/ssh_helper.py "command1" "command2" ...
    python scripts/ssh_helper.py --upload local_path remote_path
"""
import sys
import os
import io
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
PORT = 22
USER = "root"
PASSWORD = os.environ.get("SSH_PASSWORD") or "n8L1JtNJXvL-t#"


def run_command(client, command, timeout=300):
    print(f"\n>>> {command}")
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if out:
        print(out.rstrip())
    if err:
        print(f"[stderr/{code}] {err.rstrip()}")
    return code, out, err


def upload_file(client, local_path, remote_path):
    sftp = client.open_sftp()
    try:
        sftp.put(local_path, remote_path)
        print(f"[upload] {local_path} -> {remote_path}")
    finally:
        sftp.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: ssh_helper.py <command> [<command>...]")
        print("       ssh_helper.py --upload <local> <remote>")
        sys.exit(1)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[ssh] connecting to {USER}@{HOST}:{PORT}...")
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=30)

    try:
        if sys.argv[1] == "--upload":
            upload_file(client, sys.argv[2], sys.argv[3])
            return

        for cmd in sys.argv[1:]:
            run_command(client, cmd)
    finally:
        client.close()
        print("[ssh] disconnected")


if __name__ == "__main__":
    main()
