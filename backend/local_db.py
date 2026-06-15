"""
LocalDB — a self-contained, zero-setup backend for LOCAL_MODE.

It implements the small subset of the Supabase Python client API that this
app actually uses, backed by a local SQLite file, plus a simple email/password
auth system with session tokens. This lets the whole app run on localhost with
no Supabase project, no Cloudflare R2, and (with mock transcription) no Gemini
key required.

Supported query API (mirrors supabase-py):
    db.table("t").select("*", count="exact").eq(c, v).gte(c, v)
                 .order(c, desc=True).limit(n).execute()  -> Result(.data, .count)
    db.table("t").insert({...}).execute()                 -> Result(.data)
    db.table("t").update({...}).eq(c, v).execute()        -> Result(.data)
    db.table("t").upsert({...}).execute()                 -> Result(.data)

Auth API (mirrors supabase-py auth):
    db.auth.sign_up({"email","password"})        -> obj.user.id / obj.user.email
    db.auth.sign_in_with_password({...})         -> obj.session.access_token / obj.user
    db.auth.get_user(token)                      -> obj.user (or obj.user is None)
"""
import hashlib
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from backend.config import settings

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(_hash_password(password, salt), stored)


_DDL = [
    """create table if not exists auth_users (
        id text primary key, email text unique, password_hash text, created_at text)""",
    """create table if not exists sessions (
        token text primary key, user_id text, created_at text)""",
    """create table if not exists user_profiles (
        id text primary key, email text unique, credits_minutes integer default 0,
        trial_used integer default 0, trial_ip text, is_active integer default 1,
        created_at text, updated_at text)""",
    """create table if not exists transcription_jobs (
        id text primary key, user_id text, status text default 'pending',
        progress_pct integer default 0, original_filename text, audio_r2_key text,
        duration_minutes real, credits_used integer, model_used text,
        transcript_bn text, transcript_en text, chunk_count integer,
        error_message text, respondent_meta text, created_at text, completed_at text)""",
    """create table if not exists credit_transactions (
        id text primary key, user_id text, minutes_added integer,
        transaction_type text, bkash_reference text, notes text,
        activated_by text, created_at text)""",
    """create table if not exists trial_ips (
        ip text primary key, email text, used_at text)""",
    """create table if not exists pending_payments (
        id text primary key, user_id text, bundle_name text, bundle_minutes integer,
        bundle_price_bdt real, bkash_trx_id text, status text default 'pending',
        admin_notes text, created_at text, resolved_at text)""",
    """create table if not exists service_requests (
        id text primary key, user_id text, service_type text, description text,
        estimated_size text, deadline text, contact_email text, contact_whatsapp text,
        attachment_r2_key text, status text default 'new', quoted_price text,
        admin_notes text, created_at text)""",
]


class _Result:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _Query:
    """Chainable query builder for one table."""

    def __init__(self, db: "LocalDB", table: str):
        self._db = db
        self._table = table
        self._mode = "select"
        self._payload = None
        self._filters = []          # list of (col, op, value)
        self._order = None
        self._desc = False
        self._limit = None
        self._count = False

    # ---- builders ----
    def select(self, *_cols, count=None):
        self._mode = "select"
        self._count = count == "exact"
        return self

    def insert(self, payload):
        self._mode = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._mode = "update"
        self._payload = payload
        return self

    def upsert(self, payload):
        self._mode = "upsert"
        self._payload = payload
        return self

    def delete(self):
        self._mode = "delete"
        return self

    def eq(self, col, val):
        self._filters.append((col, "=", val))
        return self

    def gte(self, col, val):
        self._filters.append((col, ">=", val))
        return self

    def order(self, col, desc=False):
        self._order = col
        self._desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    # ---- helpers ----
    def _where(self):
        if not self._filters:
            return "", []
        clauses, params = [], []
        for col, op, val in self._filters:
            clauses.append(f"{col} {op} ?")
            params.append(val)
        return " where " + " and ".join(clauses), params

    def _prep_row(self, row: dict, cols: set) -> dict:
        row = dict(row)
        if "id" in cols and not row.get("id"):
            row["id"] = str(uuid4())
        if "created_at" in cols and "created_at" not in row:
            row["created_at"] = _now()
        # Drop unknown keys, coerce booleans to 0/1
        clean = {}
        for k, v in row.items():
            if k not in cols:
                continue
            clean[k] = int(v) if isinstance(v, bool) else v
        return clean

    # ---- execution ----
    def execute(self):
        with _LOCK:
            cur = self._db.conn.cursor()
            cols = self._db.columns(self._table)

            if self._mode == "select":
                where, params = self._where()
                sql = f"select * from {self._table}{where}"
                if self._order:
                    sql += f" order by {self._order} {'desc' if self._desc else 'asc'}"
                if self._limit is not None:
                    sql += f" limit {int(self._limit)}"
                rows = [dict(r) for r in cur.execute(sql, params).fetchall()]
                count = None
                if self._count:
                    count = cur.execute(
                        f"select count(*) from {self._table}{where}", params
                    ).fetchone()[0]
                return _Result(rows, count)

            if self._mode in ("insert", "upsert"):
                payloads = self._payload if isinstance(self._payload, list) else [self._payload]
                inserted = []
                verb = "insert or replace into" if self._mode == "upsert" else "insert into"
                for p in payloads:
                    row = self._prep_row(p, cols)
                    keys = list(row.keys())
                    placeholders = ", ".join("?" for _ in keys)
                    cur.execute(
                        f"{verb} {self._table} ({', '.join(keys)}) values ({placeholders})",
                        [row[k] for k in keys],
                    )
                    inserted.append(row)
                self._db.conn.commit()
                return _Result(inserted)

            if self._mode == "update":
                row = self._prep_row(self._payload, cols)
                # don't auto-add id/created_at on update
                row = {k: v for k, v in row.items()
                       if k in cols and k not in ("id", "created_at")}
                where, params = self._where()
                sets = ", ".join(f"{k}=?" for k in row)
                cur.execute(
                    f"update {self._table} set {sets}{where}",
                    list(row.values()) + params,
                )
                self._db.conn.commit()
                return _Result([])

            if self._mode == "delete":
                where, params = self._where()
                cur.execute(f"delete from {self._table}{where}", params)
                self._db.conn.commit()
                return _Result([])

            return _Result([])


class _Auth:
    """Minimal local auth: email/password with session tokens, no email verification."""

    def __init__(self, db: "LocalDB"):
        self._db = db

    def sign_up(self, creds: dict):
        email = (creds.get("email") or "").strip().lower()
        password = creds.get("password") or ""
        if not email or not password:
            raise Exception("Email and password are required.")
        with _LOCK:
            cur = self._db.conn.cursor()
            existing = cur.execute(
                "select id from auth_users where email=?", (email,)
            ).fetchone()
            if existing:
                raise Exception("User already registered")
            uid = str(uuid4())
            cur.execute(
                "insert into auth_users (id, email, password_hash, created_at) values (?,?,?,?)",
                (uid, email, _hash_password(password), _now()),
            )
            self._db.conn.commit()
        return SimpleNamespace(user=SimpleNamespace(id=uid, email=email))

    def sign_in_with_password(self, creds: dict):
        email = (creds.get("email") or "").strip().lower()
        password = creds.get("password") or ""
        with _LOCK:
            cur = self._db.conn.cursor()
            row = cur.execute(
                "select id, email, password_hash from auth_users where email=?", (email,)
            ).fetchone()
            if not row or not _verify_password(password, row["password_hash"]):
                raise Exception("Invalid login credentials")
            token = secrets.token_urlsafe(32)
            cur.execute(
                "insert into sessions (token, user_id, created_at) values (?,?,?)",
                (token, row["id"], _now()),
            )
            self._db.conn.commit()
        return SimpleNamespace(
            session=SimpleNamespace(access_token=token),
            user=SimpleNamespace(id=row["id"], email=row["email"]),
        )

    def get_user(self, token: str):
        if not token:
            return SimpleNamespace(user=None)
        with _LOCK:
            cur = self._db.conn.cursor()
            row = cur.execute(
                "select u.id as id, u.email as email from sessions s "
                "join auth_users u on u.id = s.user_id where s.token=?",
                (token,),
            ).fetchone()
        if not row:
            return SimpleNamespace(user=None)
        return SimpleNamespace(user=SimpleNamespace(id=row["id"], email=row["email"]))

    def sign_out(self, *_a, **_k):
        return None


class LocalDB:
    """Drop-in stand-in for the Supabase client used in LOCAL_MODE."""

    def __init__(self, path: str | None = None):
        path = path or settings.LOCAL_DB_PATH
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with _LOCK:
            for stmt in _DDL:
                self.conn.execute(stmt)
            # Lightweight migrations: add columns introduced after a DB was
            # first created (ALTER is a no-op-with-error if it already exists).
            for table, col, typ in [
                ("transcription_jobs", "respondent_meta", "text"),
                ("user_profiles", "is_active", "integer default 1"),
            ]:
                try:
                    self.conn.execute(f"alter table {table} add column {col} {typ}")
                except Exception:
                    pass
            self.conn.commit()
        self._cols_cache: dict[str, set] = {}
        self.auth = _Auth(self)

    def columns(self, table: str) -> set:
        if table not in self._cols_cache:
            rows = self.conn.execute(f"pragma table_info({table})").fetchall()
            self._cols_cache[table] = {r["name"] for r in rows}
        return self._cols_cache[table]

    def table(self, name: str) -> _Query:
        return _Query(self, name)
