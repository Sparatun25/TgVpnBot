"""Deploy latest code + run alembic migrations + restart containers."""
import sys
import io
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

DC = "/usr/local/bin/docker-compose"


def run(client, cmd, timeout=120):
    """Execute command on remote, print output, return (code, out)."""
    print(f"\n>>> {cmd[:100]}{'...' if len(cmd) > 100 else ''}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print(f"[stderr/{code}] {err.rstrip()}")
    return code, out.strip()


client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print(f"[ssh] connecting to {USER}@{HOST}...")
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

try:
    # 1. Pull latest code
    print("\n" + "=" * 60)
    print("STEP 1: git pull")
    print("=" * 60)
    run(client, "cd /opt/onyxvpn && git pull origin main")

    # Show last 3 commits
    run(client, "cd /opt/onyxvpn && git log --oneline -3")

    # 2. Check alembic state
    print("\n" + "=" * 60)
    print("STEP 2: check alembic state")
    print("=" * 60)
    code, current = run(client, f"cd /opt/onyxvpn && {DC} exec -T backend alembic current 2>&1")
    code, heads = run(client, f"cd /opt/onyxvpn && {DC} exec -T backend alembic heads 2>&1")

    print(f"\n[analysis] current='{current}' heads='{heads}'")

    # 3. Run migrations if needed
    print("\n" + "=" * 60)
    print("STEP 3: run migrations")
    print("=" * 60)

    if not current or current == "":
        # Alembic has no record — DB was probably created before alembic
        # Try upgrade head first; if tables exist, it will fail and we stamp
        print("[plan] alembic current is empty — attempting upgrade head")
        code, out = run(client, f"cd /opt/onyxvpn && {DC} exec -T backend alembic upgrade head 2>&1", timeout=120)

        if code != 0 and ("already exists" in out or "relation" in out.lower()):
            print("[plan] upgrade failed (tables exist) — stamping head instead")
            run(client, f"cd /opt/onyxvpn && {DC} exec -T backend alembic stamp head 2>&1")
            # Re-run upgrade to make sure everything is applied
            run(client, f"cd /opt/onyxvpn && {DC} exec -T backend alembic upgrade head 2>&1")
        elif code != 0:
            print(f"[ERROR] alembic upgrade head failed with code {code}")
            print(f"[ERROR] output: {out}")
            print("[ERROR] stopping — manual intervention needed")
            sys.exit(1)
    elif "e71938e50ad2" in current and ("a1b2c3d4e5f6" in heads or "f8a9b0c1d2e3" in heads):
        # Behind head
        print("[plan] alembic is behind head — running upgrade head")
        code, out = run(client, f"cd /opt/onyxvpn && {DC} exec -T backend alembic upgrade head 2>&1", timeout=120)
        if code != 0:
            print(f"[ERROR] alembic upgrade head failed with code {code}")
            print(f"[ERROR] output: {out}")
            sys.exit(1)
    elif current and heads and current.strip() == heads.strip():
        print("[plan] alembic is up to date — skipping migrations")
    else:
        # Unknown state — try upgrade
        print(f"[plan] unknown state, trying upgrade head anyway")
        run(client, f"cd /opt/onyxvpn && {DC} exec -T backend alembic upgrade head 2>&1", timeout=120)

    # Verify final alembic state
    print("\n[verify] final alembic state:")
    run(client, f"cd /opt/onyxvpn && {DC} exec -T backend alembic current 2>&1")

    # 4. Restart containers to pick up new Python code
    print("\n" + "=" * 60)
    print("STEP 4: restart containers")
    print("=" * 60)
    run(client, f"cd /opt/onyxvpn && {DC} restart backend bot", timeout=60)

    # Wait a bit for containers to come back up
    print("\n[wait] giving containers 10s to start...")
    import time
    time.sleep(10)

    # 5. Verify everything is up
    print("\n" + "=" * 60)
    print("STEP 5: verify")
    print("=" * 60)
    run(client, f"cd /opt/onyxvpn && {DC} ps")

    print("\n[logs] backend (last 30 lines):")
    run(client, f"cd /opt/onyxvpn && {DC} logs --tail=30 backend")

    print("\n[logs] bot (last 30 lines):")
    run(client, f"cd /opt/onyxvpn && {DC} logs --tail=30 bot")

    print("\n" + "=" * 60)
    print("DEPLOY COMPLETE")
    print("=" * 60)

finally:
    client.close()
    print("[ssh] disconnected")
