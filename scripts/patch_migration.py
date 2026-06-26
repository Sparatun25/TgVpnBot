"""Fix initial migration: split users FK creation to satisfy PostgreSQL unique constraint requirement."""
import sys
import io
import paramiko

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HOST = "72.56.96.52"
USER = "root"
PASSWORD = "n8L1JtNJXvL-t#"

REMOTE = "/opt/onyxvpn/migrations/versions/2026-06-26_1114-e71938e50ad2_initial_schema.py"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, port=22, username=USER, password=PASSWORD, timeout=30)

sftp = client.open_sftp()
with sftp.open(REMOTE, "r") as f:
    content = f.read().decode("utf-8")
sftp.close()

# Step 1: Remove the FK from the CREATE TABLE statement for users
old_fk = "    sa.ForeignKeyConstraint(['referred_by_id'], ['users.tg_id'], ondelete='SET NULL'),\n"
new_content = content.replace(old_fk, "")

if new_content == content:
    print("[FAIL] FK line not found in migration")
    sys.exit(1)

# Step 2: After the unique index on tg_id is created, add the FK
old_block = "    op.create_index(op.f('ix_users_tg_id'), 'users', ['tg_id'], unique=True)\n"
new_block = """    op.create_index(op.f('ix_users_tg_id'), 'users', ['tg_id'], unique=True)
    # FK on referred_by_id → users.tg_id добавляется ПОСЛЕ создания unique index
    # (PostgreSQL требует UNIQUE/PRIMARY KEY на referenced column в момент
    # создания FOREIGN KEY; unique INDEX, добавленный после таблицы,
    # не подходит — нужно явно создать unique CONSTRAINT).
    op.create_unique_constraint('uq_users_tg_id', 'users', ['tg_id'])
    op.create_foreign_key(
        'fk_users_referred_by_id_tg_id',
        'users', 'users',
        ['referred_by_id'], ['tg_id'],
        ondelete='SET NULL',
    )
"""

new_content = new_content.replace(old_block, new_block)

if old_block not in content:
    # already patched
    print("[WARN] second replacement didn't match - migration may already be patched")
else:
    print("[OK] second replacement applied")

# Also update downgrade() to drop the FK and constraint
old_down = "    op.drop_index(op.f('ix_users_tg_id'), table_name='users')\n    op.drop_index(op.f('ix_users_referred_by_id'), table_name='users')\n    op.drop_table('users')"
new_down = """    op.drop_constraint('fk_users_referred_by_id_tg_id', 'users', type_='foreignkey')
    op.drop_constraint('uq_users_tg_id', 'users', type_='unique')
    op.drop_index(op.f('ix_users_tg_id'), table_name='users')
    op.drop_index(op.f('ix_users_referred_by_id'), table_name='users')
    op.drop_table('users')"""

new_content = new_content.replace(old_down, new_down)

sftp = client.open_sftp()
with sftp.open(REMOTE, "w") as f:
    f.write(new_content.encode("utf-8"))
sftp.close()

print("[OK] migration patched")
client.close()
