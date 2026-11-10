import os, re, json, time, threading, hashlib, sqlite3, secrets
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from datetime import datetime, date
from functools import wraps
from flask import Flask, Response, jsonify, send_from_directory, render_template, request, redirect, url_for, session, flash, g, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------- environment ----------
ON_VERCEL = bool(os.environ.get("VERCEL"))

def _clean_db_url(url):
    if url.startswith("postgres://"): url = "postgresql://" + url[len("postgres://"):]
    parts = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(parts.query) if k != "supa"]  # extra param psycopg rejects
    return urlunsplit(parts._replace(query=urlencode(q)))

DATABASE_URL = _clean_db_url(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "")
USE_PG = bool(DATABASE_URL)
if USE_PG:
    import psycopg
    from psycopg.types.numeric import FloatLoader
    psycopg.adapters.register_loader("numeric", FloatLoader)
    DB_INTEGRITY = (sqlite3.IntegrityError, psycopg.errors.IntegrityError)
else:
    DB_INTEGRITY = (sqlite3.IntegrityError,)

CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
CLOUD_PRESET = os.environ.get("CLOUDINARY_UPLOAD_PRESET", "").strip()
CLOUD = {"name": CLOUD_NAME, "preset": CLOUD_PRESET} if CLOUD_NAME and CLOUD_PRESET else None

app = Flask(__name__, static_folder="public/static", static_url_path="/static")
_secret = os.environ.get("SECRET_KEY")
if not _secret:
    _secret = hashlib.sha256(("stark-store|" + DATABASE_URL).encode()).hexdigest() if DATABASE_URL else "change-this-secret-before-deploying-" + secrets.token_hex(16)
app.secret_key = _secret
app.config.update(MAX_CONTENT_LENGTH=400 * 1024 * 1024, SESSION_COOKIE_SECURE=ON_VERCEL, SESSION_COOKIE_SAMESITE="Lax")
app.config["UPLOAD_FOLDER"] = "/tmp/uploads" if ON_VERCEL else os.path.join(app.root_path, "public", "static", "uploads")
DB = os.path.join(app.root_path, "stark_store.db")
try: os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
except OSError: pass
ALLOWED = {"png", "jpg", "jpeg", "webp", "gif"}

# ---------- database layer: SQLite locally, Postgres (Neon / Vercel Postgres) when DATABASE_URL is set ----------
class PgRow:
    __slots__ = ("_names", "_values", "_map")
    def __init__(self, names, values): self._names, self._values, self._map = names, tuple(values), dict(zip(names, values))
    def __getitem__(self, k): return self._values[k] if isinstance(k, (int, slice)) else self._map[k]
    def keys(self): return list(self._names)
    def get(self, k, d=None): return self._map.get(k, d)
    def __iter__(self): return iter(self._values)
    def __len__(self): return len(self._values)

def _pg_row_factory(cursor):
    names = [c.name for c in (cursor.description or [])]
    return lambda values: PgRow(names, values)

_ID_TABLES = {"users", "products", "orders", "order_items", "reviews", "visits", "product_media", "order_messages"}

def pg_sql(sql):
    """Translate the app's SQLite-flavoured SQL to Postgres. Returns (sql, wants_returning_id)."""
    s = sql.replace("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
                    "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value")
    s = re.sub(r"\bLIKE\b", "ILIKE", s)
    s = s.replace("%", "%%").replace("?", "%s")
    m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", s, re.I)
    want = bool(m and m.group(1).lower() in _ID_TABLES and "ON CONFLICT" not in s.upper())
    if want: s = s.rstrip().rstrip(";") + " RETURNING id"
    return s, want

def pg_ddl(sql):
    s = re.sub(r"\bINTEGER PRIMARY KEY\b", "SERIAL PRIMARY KEY", sql)
    s = re.sub(r"\bREAL\b", "DOUBLE PRECISION", s)
    return re.sub(r"\bBLOB\b", "BYTEA", s)

class PgCursor:
    def __init__(self, cur, lastrowid=None): self._c, self.lastrowid, self.rowcount = cur, lastrowid, cur.rowcount
    def fetchone(self): return self._c.fetchone() if self._c.description else None
    def fetchall(self): return self._c.fetchall() if self._c.description else []
    def __iter__(self): return iter(self.fetchall())

_pool, _pool_lock = [], threading.Lock()

def _bad(c): return c.closed or getattr(c, "broken", False)

def _acquire():
    while True:
        with _pool_lock: c = _pool.pop() if _pool else None
        if c is None: return None
        if not _bad(c): return c

def _release(c):
    if not _bad(c):
        with _pool_lock:
            if len(_pool) < 4: _pool.append(c); return
    try: c.close()
    except Exception: pass

class PgConn:
    """Re-uses warm connections between requests and only opens a transaction for writes (fewer round trips)."""
    def __init__(self):
        self._used = self._in_tx = False
        self.conn = _acquire() or self._connect()
    def _connect(self):
        return psycopg.connect(DATABASE_URL, row_factory=_pg_row_factory, prepare_threshold=None, autocommit=True)
    def _run(self, s, params=()):
        try: return self.conn.execute(s, params)
        except (psycopg.OperationalError, psycopg.InterfaceError):
            if self._used or self._in_tx: raise
            try: self.conn.close()      # idle connection was closed by the server: reconnect once
            except Exception: pass
            self.conn = self._connect()
            return self.conn.execute(s, params)
    def _rollback(self):
        if self._in_tx:
            self._in_tx = False
            try: self.conn.execute("ROLLBACK")
            except Exception:
                try: self.conn.close()
                except Exception: pass
    def execute(self, sql, params=()):
        s, want = pg_sql(sql)
        try:
            if not self._in_tx and re.match(r"\s*(INSERT|UPDATE|DELETE)\b", s, re.I):
                self._run("BEGIN"); self._in_tx = True; self._used = True
            cur = self._run(s, tuple(params)); self._used = True
        except Exception:
            self._rollback(); raise
        last = None
        if want:
            r = cur.fetchone(); last = r[0] if r else None
        return PgCursor(cur, last)
    def executescript(self, script):
        for stmt in script.split(";"):
            if stmt.strip(): self.conn.execute(pg_ddl(stmt))
    def commit(self):
        if self._in_tx:
            self._in_tx = False; self.conn.execute("COMMIT")
    def close(self):
        self._rollback(); _release(self.conn)

def raw_conn():
    if USE_PG: return PgConn()
    c = sqlite3.connect(DB); c.execute("PRAGMA foreign_keys=ON"); return c

def db():
    if "db" not in g:
        if USE_PG: g.db = PgConn()
        else:
            g.db = sqlite3.connect(DB)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn: conn.close()

SCHEMA = """
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'customer', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, name TEXT NOT NULL, category TEXT DEFAULT 'General', description TEXT DEFAULT '', price REAL NOT NULL, discount REAL DEFAULT 0, stock INTEGER DEFAULT 0, image TEXT DEFAULT '', active INTEGER DEFAULT 1, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY, user_id INTEGER, customer_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL, address TEXT NOT NULL, total REAL NOT NULL, status TEXT DEFAULT 'Pending', created_at TEXT NOT NULL, payment_method TEXT DEFAULT 'Cash on Delivery', payment_status TEXT DEFAULT 'Unpaid', payment_reference TEXT DEFAULT '', FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS order_items(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, product_id INTEGER, product_name TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price REAL NOT NULL, FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, user_id INTEGER, customer_name TEXT NOT NULL, rating INTEGER NOT NULL, comment TEXT NOT NULL, approved INTEGER DEFAULT 0, created_at TEXT NOT NULL, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE, FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL);
        CREATE TABLE IF NOT EXISTS visits(id INTEGER PRIMARY KEY, visited_on TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS product_media(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL, filename TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'image', FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS order_messages(id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, sender TEXT NOT NULL, body TEXT DEFAULT '', image TEXT DEFAULT '', extra TEXT DEFAULT '', created_at TEXT NOT NULL, FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS chat_files(name TEXT PRIMARY KEY, mime TEXT NOT NULL DEFAULT 'image/jpeg', data BLOB NOT NULL);
        """

TABLE_COLUMNS = {
    "orders": {
        "payment_method": "TEXT DEFAULT 'Cash on Delivery'", "payment_status": "TEXT DEFAULT 'Unpaid'", "payment_reference": "TEXT DEFAULT ''",
        "address_confirmed": "INTEGER DEFAULT 0", "chat_state": "TEXT DEFAULT 'done'", "payment_screenshot": "TEXT DEFAULT ''",
        "customer_unread": "INTEGER DEFAULT 0", "agent_unread": "INTEGER DEFAULT 0",
    },
    "products": {"colors": "TEXT DEFAULT ''", "sizes": "TEXT DEFAULT ''"},
    "order_items": {"color": "TEXT DEFAULT ''", "size": "TEXT DEFAULT ''"},
}

def schema_ready(c):
    try:
        c.execute("SELECT agent_unread FROM orders LIMIT 1"); c.execute("SELECT 1 FROM chat_files LIMIT 1"); c.execute("SELECT 1 FROM product_media LIMIT 1")
        c.execute("SELECT colors, sizes FROM products LIMIT 1"); c.execute("SELECT color, size FROM order_items LIMIT 1")
        return bool(c.execute("SELECT id FROM users WHERE role='admin'").fetchone())
    except Exception:
        return False

def init_db():
    """Creates/updates tables. Returns False (and does nothing) when everything already exists."""
    c = raw_conn()
    try:
        if schema_ready(c): return False
        c.executescript(SCHEMA)
        for table, columns in TABLE_COLUMNS.items():
            if USE_PG:
                for column, definition in columns.items():
                    c.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
            else:
                have = {row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}
                for column, definition in columns.items():
                    if column not in have: c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@starkstore.local")
        admin_password = os.environ.get("ADMIN_PASSWORD") or (None if ON_VERCEL else "ChangeMe123!")
        exists = c.execute("SELECT id FROM users WHERE role='admin'").fetchone()
        if not exists and admin_password:
            c.execute("INSERT INTO users(name,email,password,role,created_at) VALUES(?,?,?,?,?)",
                      ("Stark Store Admin", admin_email.lower(), generate_password_hash(admin_password), "admin", datetime.now().isoformat(timespec="seconds")))
        elif not exists:
            print("WARNING: no admin account created. Set ADMIN_EMAIL and ADMIN_PASSWORD environment variables.")
        c.commit()
        return True
    finally:
        c.close()

def migrate_media():
    c = raw_conn()
    try:
        c.execute("INSERT INTO product_media(product_id,filename,kind) SELECT id,image,'image' FROM products WHERE image IS NOT NULL AND image!='' AND id NOT IN (SELECT product_id FROM product_media)")
        c.commit()
    finally:
        c.close()

_ready = False
@app.before_request
def ensure_ready():
    global _ready
    if request.endpoint == "static": return
    if ON_VERCEL and not USE_PG:
        return ("Stark Store is not configured yet: add a Postgres database (DATABASE_URL) to your Vercel project, then redeploy.", 503)
    if not _ready:
        try:
            _ready = True
            if init_db(): migrate_media()
        except Exception as e:
            app.logger.exception("database init failed")
            return ("Database is not ready: " + str(e)[:200], 503)

COLOR_HEX = {"red": "#dc2626", "black": "#111827", "white": "#ffffff", "offwhite": "#f5f1e6", "ivory": "#f8f4e3", "blue": "#2563eb", "navy": "#1e3a8a",
    "navyblue": "#1e3a8a", "skyblue": "#38bdf8", "green": "#16a34a", "olive": "#6b7a2a", "mint": "#86efac", "yellow": "#facc15", "mustard": "#d4a017",
    "lemon": "#fde047", "pink": "#ec4899", "hotpink": "#ff4fa3", "peach": "#fdba94", "coral": "#fb7185", "orange": "#f97316", "purple": "#9333ea",
    "lavender": "#c4b5fd", "violet": "#7c3aed", "maroon": "#7f1d1d", "burgundy": "#7f1d3a", "wine": "#6d1a36", "brown": "#7c4a2d", "chocolate": "#4b2e1f",
    "coffee": "#6f4e37", "beige": "#e7d3b0", "cream": "#fff3d6", "khaki": "#bda76a", "camel": "#c19a6b", "grey": "#6b7280", "gray": "#6b7280",
    "charcoal": "#374151", "silver": "#c0c0c0", "gold": "#d4af37", "teal": "#0d9488", "turquoise": "#14b8a6", "rust": "#b7410e", "firozi": "#14b8a6"}

def clean_options(raw):
    """'Red, black ,Red' -> 'Red,black'  (colours / sizes the admin typed)."""
    out, seen = [], set()
    for part in re.split(r"[,\n|]+", raw or ""):
        v = re.sub(r"\s+", " ", re.sub(r"[^\w\s\-/.&+()']", "", part)).strip()[:24]
        if v and v.lower() not in seen: seen.add(v.lower()); out.append(v)
    return ",".join(out[:15])

def opts(raw): return [x for x in (raw or "").split(",") if x]

def color_hex(name):
    words = re.findall(r"[a-z]+", (name or "").lower())
    for cand in ["".join(words)] + words[::-1]:
        if cand in COLOR_HEX: return COLOR_HEX[cand]
    return ""

def media_src(name, w=1200):
    """Public URL of a product image/video. Cloudinary images are resized (w = max width) and optimised."""
    if not name: return ""
    if name.startswith("https://"):
        if "res.cloudinary.com" in name:
            name = name.replace("/image/upload/", f"/image/upload/f_auto,q_auto,c_limit,w_{w}/", 1).replace("/video/upload/", "/video/upload/q_auto/", 1)
        return name
    return url_for("static", filename="uploads/" + name)

def media_poster(name, w=160):
    """Small still image for a Cloudinary video (so thumbnails do not download the video)."""
    if name.startswith("https://res.cloudinary.com") and "/video/upload/" in name:
        return re.sub(r"\.\w+$", ".jpg", name.replace("/video/upload/", f"/video/upload/so_0,f_jpg,q_auto,c_fill,w_{w},h_{w}/", 1))
    return ""

def _asset_version():
    v = (os.environ.get("VERCEL_GIT_COMMIT_SHA") or os.environ.get("VERCEL_DEPLOYMENT_ID") or "")[:12]
    if v: return v
    h = hashlib.md5()
    for f in ("site.css", "site.js", "chat.js"):
        try:
            with open(os.path.join(app.static_folder, f), "rb") as fh: h.update(fh.read())
        except OSError: pass
    return h.hexdigest()[:10]
ASSET_V = _asset_version()

def asset(filename):
    """Static file URL with a version, so browsers can cache it for a long time."""
    return url_for("static", filename=filename, v=ASSET_V)

app.jinja_env.globals.update(media_src=media_src, media_poster=media_poster, asset=asset, opts=opts, color_hex=color_hex)

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id") or session.get("role") != "admin":
            flash("Please sign in with your admin account.", "error")
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def current_user():
    if not session.get("user_id"): return None
    if "cu" not in g: g.cu = db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    return g.cu

@app.context_processor
def inject():
    u = current_user(); badges = {}; my_unread = 0
    if u and u["role"] == "admin":
        badges = {"admin_orders": db().execute("SELECT COUNT(*) FROM orders WHERE agent_unread=1").fetchone()[0],
                  "admin_reviews": db().execute("SELECT COUNT(*) FROM reviews WHERE approved=0").fetchone()[0]}
    else:
        conds, args = [], []
        if u: conds.append("user_id=?"); args.append(u["id"])
        ids = session.get("my_orders", [])
        if ids: conds.append("id IN (%s)" % ",".join("?" * len(ids))); args += ids
        if conds: my_unread = db().execute("SELECT COUNT(*) FROM orders WHERE customer_unread=1 AND (" + " OR ".join(conds) + ")", args).fetchone()[0]
    return {"current_user": u, "cart_count": sum(session.get("cart", {}).values()), "badges": badges, "my_unread": my_unread, "status_label": STATUS_LABEL, "cloud": CLOUD, "on_vercel": ON_VERCEL}

@app.before_request
def count_visit():
    if request.endpoint and not request.endpoint.startswith(("static", "api_")) and request.endpoint not in ("login", "register", "add_cart", "update_cart", "order_chat_post", "chat_file", "admin_reply"):
        today = date.today().isoformat()
        if session.get("visit_day") != today:
            db().execute("INSERT INTO visits(visited_on) VALUES(?)", (today,))
            db().commit(); session["visit_day"] = today

def parse_prices(form):
    """Admin enters original (cut) price + sale price; discount % is derived."""
    orig = float(form["price"])
    raw = form.get("sale_price", "").strip()
    sale = float(raw) if raw else orig
    if orig < 0 or sale < 0 or sale > orig: raise ValueError("sale price")
    return orig, ((1 - sale / orig) * 100 if orig > 0 and sale < orig else 0.0)

STATUS_LABEL = {"Pending": "Pending", "Confirmed": "Confirmed", "Shipped": "On its way", "Delivered": "Delivered", "Cancelled": "Cancelled"}
PAY_STATUSES = ("Unpaid", "Awaiting payment", "Awaiting verification", "Gateway setup required", "Paid", "Refunded")
PAY_METHODS = [
    ("cod", "Cash on Delivery", "Pay cash when your parcel arrives."),
    ("bank", "Bank Transfer", "Transfer to the store account. Details are shared in your order chat."),
    ("easypaisa", "Easypaisa", "Pay via Easypaisa. Details are shared in your order chat."),
    ("jazzcash", "JazzCash", "Pay via JazzCash. Details are shared in your order chat."),
    ("card", "Debit / Credit Card", "Online payment. Details are shared in your order chat."),
]
LABEL_KEY = {m[1]: m[0] for m in PAY_METHODS}
_b, _e, _j = (os.environ.get(k, "") for k in ("STARK_BANK_DETAILS", "STARK_EASYPAISA_NUMBER", "STARK_JAZZCASH_NUMBER"))
SETTING_DEFAULTS = {"pay_cod": "1", "pay_bank": "1" if _b else "0", "pay_easypaisa": "1" if _e else "0", "pay_jazzcash": "1" if _j else "0", "pay_card": "0",
                    "bank_name": "", "bank_title": "", "bank_number": _b, "ep_title": "", "ep_number": _e, "jc_title": "", "jc_number": _j,
                    "card_info": "", "support_name": "Stark Support"}
CHAT_DIR = "/tmp/private_uploads" if ON_VERCEL else os.path.join(app.root_path, "private_uploads")
try: os.makedirs(CHAT_DIR, exist_ok=True)
except OSError: pass
STATUS_MSG = {"Confirmed": "✅ Good news! Your order #{id} has been confirmed by our team.",
              "Shipped": "🚚 Your order #{id} is on its way! It will reach you soon.",
              "Delivered": "📦 Your order #{id} has been delivered. Thank you for shopping with Stark Store! 💜",
              "Cancelled": "❌ Your order #{id} has been cancelled. If this is a mistake, please message us here.",
              "Pending": "⏳ Your order #{id} is back to Pending."}
QUICK = {"await_address": [{"label": "✅ Confirm order & address", "action": "confirm_address"}, {"label": "✏️ Change address", "action": "change_address"}],
         "await_new_address": [{"label": "↩ Keep current address", "action": "cancel_change"}],
         "await_payment": [{"label": "💳 Show account details", "action": "show_payment"}]}
ACTION_TEXT = {"confirm_address": "✅ Confirm order & address", "change_address": "✏️ Change address", "cancel_change": "↩ Keep current address", "show_payment": "💳 Show account details"}
YES = {"yes", "y", "ok", "okay", "confirm", "confirmed", "ha", "han", "haan", "ji", "jee", "theek", "thik", "sahi", "correct", "done", "yes confirm"}

def now(): return datetime.now().isoformat(timespec="seconds")
def money(x): return f"Rs. {float(x):,.2f}"
def is_agent(): return bool(session.get("user_id")) and session.get("role") == "admin"

_settings_cache = {"t": 0.0, "v": None}

def get_settings():
    if _settings_cache["v"] is None or time.time() - _settings_cache["t"] > 30:
        st = dict(SETTING_DEFAULTS)
        for r in db().execute("SELECT key,value FROM settings"): st[r["key"]] = r["value"]
        _settings_cache.update(t=time.time(), v=st)
    return dict(_settings_cache["v"])

def can_access(o):
    if not o: return False
    if is_agent(): return True
    if session.get("user_id") and o["user_id"] == session["user_id"]: return True
    return o["id"] in session.get("my_orders", [])

def add_msg(conn, oid, sender, body="", image="", extra=""):
    conn.execute("INSERT INTO order_messages(order_id,sender,body,image,extra,created_at) VALUES(?,?,?,?,?,?)", (oid, sender, body, image, extra, now()))

def pay_details(st, key):
    if key == "bank" and st["bank_number"]:
        return (f"🏦 Bank Transfer\nBank: {st['bank_name'] or '—'}\nAccount title: {st['bank_title'] or '—'}\nAccount / IBAN: {st['bank_number']}", st["bank_number"])
    if key == "easypaisa" and st["ep_number"]:
        return (f"📱 Easypaisa\nAccount title: {st['ep_title'] or '—'}\nNumber: {st['ep_number']}", st["ep_number"])
    if key == "jazzcash" and st["jc_number"]:
        return (f"📲 JazzCash\nAccount title: {st['jc_title'] or '—'}\nNumber: {st['jc_number']}", st["jc_number"])
    if key == "card" and st["card_info"].strip():
        return ("💳 " + st["card_info"].strip(), "")
    return ("", "")

def start_chat(conn, oid, name, phone, address, total, method_label, items):
    lines = "\n".join(f"• {n} × {q} — {money(p * q)}" for n, q, p in items)
    first = (name.split() or ["there"])[0]
    add_msg(conn, oid, "bot", f"Hi {first}! 👋 Thanks for shopping with Stark Store.\nYour order #{oid} has been received and is currently Pending.\n\n{lines}\n\nTotal: {money(total)}\nPayment: {method_label}")
    add_msg(conn, oid, "bot", f"📍 Delivery address:\n{address}\n📞 {phone}\n\nPlease confirm your order and delivery address so we can process it. If anything is wrong, tap “Change address”.")

def send_pay_details(conn, o, st, key):
    text, copy = pay_details(st, key)
    if text: add_msg(conn, o["id"], "bot", text, extra=copy)
    else:
        add_msg(conn, o["id"], "bot", "Our agent will share the account details here shortly. 🙏")
        conn.execute("UPDATE orders SET agent_unread=1 WHERE id=?", (o["id"],))

def confirm_address(conn, o, st, key):
    oid = o["id"]
    conn.execute("UPDATE orders SET address_confirmed=1 WHERE id=?", (oid,))
    if key == "cod":
        conn.execute("UPDATE orders SET chat_state='done', status=CASE WHEN status='Pending' THEN 'Confirmed' ELSE status END WHERE id=?", (oid,))
        add_msg(conn, oid, "bot", f"✅ Thank you! Your address is confirmed and your order #{oid} is now Confirmed.\nPayment: Cash on Delivery. Please keep {money(o['total'])} ready. We'll update you here when it's on its way. 🚚")
    else:
        conn.execute("UPDATE orders SET chat_state='await_payment' WHERE id=?", (oid,))
        add_msg(conn, oid, "bot", f"✅ Address confirmed, thank you!\n\nTo complete your order, please send {money(o['total'])} to this account:")
        send_pay_details(conn, o, st, key)
        add_msg(conn, oid, "bot", "After paying, please send a screenshot of the payment here using the 📎 button. Our agent will verify it and confirm your order.")

def bot_reply(conn, o, text, action, image):
    oid, state, st = o["id"], o["chat_state"], get_settings()
    key = LABEL_KEY.get(o["payment_method"], "cod")
    t = (text or "").strip().lower().rstrip("!. ")
    if o["status"] == "Cancelled": return
    if state == "await_address":
        if action == "confirm_address" or (not image and t in YES): confirm_address(conn, o, st, key)
        elif action == "change_address":
            conn.execute("UPDATE orders SET chat_state='await_new_address' WHERE id=?", (oid,))
            add_msg(conn, oid, "bot", "No problem ✏️ Please type your full correct delivery address (house, street, area, city).")
        elif text or image: add_msg(conn, oid, "bot", "Please tap “✅ Confirm order & address” (or type YES) to continue, or “✏️ Change address”.")
    elif state == "await_new_address":
        if action == "cancel_change":
            conn.execute("UPDATE orders SET chat_state='await_address' WHERE id=?", (oid,))
            add_msg(conn, oid, "bot", f"Okay, keeping:\n{o['address']}\n\nShall I confirm the order with this address?")
        elif text and not action:
            conn.execute("UPDATE orders SET address=?, chat_state='await_address' WHERE id=?", (text.strip(), oid))
            add_msg(conn, oid, "bot", f"Thanks! Your delivery address is now:\n{text.strip()}\n\nIs this correct? Tap “✅ Confirm order & address” to proceed.")
    elif state == "await_payment":
        if action == "show_payment": send_pay_details(conn, o, st, key)
        elif image:
            conn.execute("UPDATE orders SET chat_state='payment_review', payment_screenshot=?, payment_status='Awaiting verification' WHERE id=?", (image, oid))
            add_msg(conn, oid, "bot", "📸 Screenshot received, thank you! Our agent will verify your payment and confirm your order shortly. You'll get an update right here.")
        elif text: add_msg(conn, oid, "bot", "Please upload your payment screenshot with the 📎 button. Need the account details again? Tap “💳 Show account details”.")
    elif state == "payment_review":
        if image: add_msg(conn, oid, "bot", "Added ✅ Our agent will review everything shortly.")
        elif text:
            last = conn.execute("SELECT sender,body FROM order_messages WHERE order_id=? AND sender!='customer' ORDER BY id DESC LIMIT 1", (oid,)).fetchone()
            if not last or "agent will reply" not in last["body"]:
                add_msg(conn, oid, "bot", "Thanks! Our agent will reply here soon. 🙏")

MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}

def save_chat_image(f):
    if not f or not f.filename: return ""
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    head = f.stream.read(12); f.stream.seek(0)
    ok = head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8")) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    f.stream.seek(0, 2); size = f.stream.tell(); f.stream.seek(0)
    if size > 8 * 1024 * 1024: raise ValueError("Image is too large (max 8 MB).")
    if ext not in ALLOWED or not ok: raise ValueError("Please attach a JPG, PNG, WEBP or GIF image.")
    name = secrets.token_hex(16) + "." + ext
    if USE_PG: db().execute("INSERT INTO chat_files(name,mime,data) VALUES(?,?,?)", (name, MIME[ext], f.stream.read()))
    else: f.save(os.path.join(CHAT_DIR, name))
    return name

def msg_json(oid, r):
    return {"id": r["id"], "sender": r["sender"], "body": r["body"], "extra": r["extra"], "time": r["created_at"][11:16],
            "image": url_for("chat_file", oid=oid, name=r["image"]) if r["image"] else ""}

def product_price(p):
    return round(float(p["price"]) * (1 - float(p["discount"] or 0) / 100), 2)

@app.route("/")
def home():
    products = db().execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC LIMIT 8").fetchall()
    categories = db().execute("SELECT DISTINCT category FROM products WHERE active=1 ORDER BY category").fetchall()
    return render_template("home.html", products=products, categories=categories)

@app.route("/shop")
def shop():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    sql = "SELECT * FROM products WHERE active=1"
    args = []
    if q: sql += " AND (name LIKE ? OR description LIKE ?)"; args += [f"%{q}%", f"%{q}%"]
    if category: sql += " AND category=?"; args.append(category)
    sql += " ORDER BY id DESC"
    products = db().execute(sql, args).fetchall()
    categories = db().execute("SELECT DISTINCT category FROM products WHERE active=1 ORDER BY category").fetchall()
    return render_template("shop.html", products=products, categories=categories, q=q, selected_category=category)

@app.route("/product/<int:pid>", methods=["GET", "POST"])
def product_detail(pid):
    p = db().execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    if not p: abort(404)
    if request.method == "POST":
        rating = int(request.form.get("rating", 5))
        comment = request.form.get("comment", "").strip()
        name = request.form.get("customer_name", "").strip()
        if not name and current_user(): name = current_user()["name"]
        if not name or not comment or rating not in range(1, 6):
            flash("Please enter your name, rating and review.", "error")
        else:
            uid = session.get("user_id")
            db().execute("INSERT INTO reviews(product_id,user_id,customer_name,rating,comment,approved,created_at) VALUES(?,?,?,?,?,?,?)",
                         (pid, uid, name, rating, comment, 0, datetime.now().isoformat(timespec="seconds")))
            db().commit()
            flash("Thanks! Your review will appear after admin approval.", "success")
        return redirect(url_for("product_detail", pid=pid))
    reviews = db().execute("SELECT * FROM reviews WHERE product_id=? AND approved=1 ORDER BY id DESC", (pid,)).fetchall()
    return render_template("product.html", p=p, reviews=reviews, media=product_media(pid, p["image"]))

def cart_key(pid, color="", size=""): return f"{pid}|{color}|{size}"

def parse_key(key):
    parts = (str(key).split("|") + ["", ""])[:3]
    return parts[0], parts[1], parts[2]

def variant_label(color, size): return ", ".join(x for x in (color, size) if x)

def get_cart():
    """Cart as {key: qty}; key = 'productId|colour|size' (older carts without options are upgraded)."""
    return {(k if "|" in k else k + "||"): int(v) for k, v in session.get("cart", {}).items()}

def cart_lines():
    lines = []
    for key, qty in get_cart().items():
        pid, color, size = parse_key(key)
        p = db().execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
        if p: lines.append({"key": key, "p": p, "color": color, "size": size, "variant": variant_label(color, size), "qty": qty})
    return lines

def cart_snapshot():
    items, total = [], 0
    for l in cart_lines():
        p = l["p"]; price = product_price(p); total += price * l["qty"]
        items.append({"id": p["id"], "key": l["key"], "name": p["name"], "variant": l["variant"], "qty": l["qty"], "price": price, "line": round(price * l["qty"], 2),
                      "image": media_src(p["image"], 160) if p["image"] else "", "url": url_for("product_detail", pid=p["id"])})
    return {"items": items, "total": round(total, 2), "count": sum(i["qty"] for i in items)}

@app.get("/api/cart")
def api_cart():
    return jsonify(cart_snapshot())

@app.route("/cart")
def cart():
    items, total = [], 0
    for l in cart_lines():
        price = product_price(l["p"]); line = price * l["qty"]; total += line
        items.append({"key": l["key"], "product": l["p"], "variant": l["variant"], "qty": l["qty"], "price": price, "line": line})
    return render_template("cart.html", items=items, total=round(total,2))

@app.post("/cart/add/<int:pid>")
def add_cart(pid):
    p = db().execute("SELECT * FROM products WHERE id=? AND active=1", (pid,)).fetchone()
    if not p: abort(404)
    colors, sizes = opts(p["colors"]), opts(p["sizes"])
    color = request.form.get("color", "").strip() if colors else ""
    size = request.form.get("size", "").strip() if sizes else ""
    err = "Please select a colour." if colors and color not in colors else "Please select a size." if sizes and size not in sizes else ""
    wants_json = request.headers.get("X-Requested-With") == "fetch"
    cart = get_cart(); key = cart_key(pid, color, size)
    room = max(0, p["stock"] - sum(q for k, q in cart.items() if k != key and parse_key(k)[0] == str(pid)))
    if not err and room <= 0: err = "Sorry, this item is out of stock."
    if err:
        if wants_json: return jsonify(ok=False, message=err), 400
        flash(err, "error"); return redirect(url_for("product_detail", pid=pid))
    try: add = max(1, int(request.form.get("quantity", 1)))
    except ValueError: add = 1
    cart[key] = min(cart.get(key, 0) + add, room)
    session["cart"] = cart
    if request.form.get("buy"):
        return redirect(url_for("checkout"))
    if wants_json:
        label = variant_label(color, size)
        return jsonify(ok=True, message=p["name"] + (f" ({label})" if label else "") + " added to your bag", **cart_snapshot())
    flash("Added to your cart.", "success")
    return redirect(request.referrer or url_for("shop"))

@app.post("/cart/update")
def update_cart():
    cart = get_cart()
    for field, value in request.form.items():
        if not field.startswith("qty_"): continue
        key = field[4:]
        if key not in cart: continue
        try: qty = max(0, min(99, int(value)))
        except ValueError: qty = 1
        if qty == 0: cart.pop(key, None); continue
        pid = parse_key(key)[0]
        p = db().execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()
        if p: qty = min(qty, max(1, p["stock"] - sum(q for k, q in cart.items() if k != key and parse_key(k)[0] == pid)))
        cart[key] = qty
    session["cart"] = cart
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, **cart_snapshot())
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if not get_cart(): return redirect(url_for("shop"))
    st = get_settings()
    methods = [m for m in PAY_METHODS if st.get("pay_" + m[0]) == "1"] or [PAY_METHODS[0]]
    if request.method == "POST":
        name, email = request.form.get("name", "").strip(), request.form.get("email", "").strip().lower()
        phone, address = request.form.get("phone", "").strip(), request.form.get("address", "").strip()
        method = request.form.get("payment_method", "cod")
        if not all([name, email, phone, address]) or method not in {m[0] for m in methods}:
            flash("Please complete all checkout fields and choose a valid payment method.", "error")
            return redirect(url_for("checkout"))
        lines = cart_lines(); need = {}
        for l in lines: need[l["p"]["id"]] = need.get(l["p"]["id"], 0) + l["qty"]
        if len(lines) != len(get_cart()) or any(need[l["p"]["id"]] > l["p"]["stock"] for l in lines):
            flash("A product is unavailable or has insufficient stock. Please update your cart.", "error")
            return redirect(url_for("cart"))
        items, total = [], 0
        for l in lines:
            price = product_price(l["p"]); total += price * l["qty"]; items.append((l["p"], l["qty"], price, l["color"], l["size"]))
        method_label = dict((m[0], m[1]) for m in PAY_METHODS)[method]
        payment_status = "Unpaid" if method == "cod" else "Awaiting payment"
        conn = db()
        cur = conn.execute("""INSERT INTO orders(user_id,customer_name,email,phone,address,total,status,created_at,payment_method,payment_status,payment_reference,chat_state,agent_unread)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (session.get("user_id"), name, email, phone, address, round(total, 2), "Pending", now(), method_label, payment_status, "", "await_address", 1))
        oid = cur.lastrowid
        for p, qty, price, color, size in items:
            conn.execute("INSERT INTO order_items(order_id,product_id,product_name,quantity,unit_price,color,size) VALUES(?,?,?,?,?,?,?)", (oid, p["id"], p["name"], qty, price, color, size))
            conn.execute("UPDATE products SET stock=stock-? WHERE id=?", (qty, p["id"]))
        start_chat(conn, oid, name, phone, address, round(total, 2), method_label, [(p["name"] + (f" ({variant_label(c, z)})" if c or z else ""), q, pr) for p, q, pr, c, z in items])
        conn.commit(); session["cart"] = {}
        ids = session.get("my_orders", []); ids.append(oid); session["my_orders"] = ids[-50:]
        return redirect(url_for("order_chat", oid=oid, new=1))
    return render_template("checkout.html", payment_methods=methods, summary=cart_snapshot())

# ---------- customer: order history + chat ----------
@app.get("/orders")
def my_orders():
    conds, args = [], []
    if session.get("user_id"): conds.append("user_id=?"); args.append(session["user_id"])
    ids = session.get("my_orders", [])
    if ids: conds.append("id IN (%s)" % ",".join("?" * len(ids))); args += ids
    rows = []
    if conds:
        for o in db().execute("SELECT * FROM orders WHERE " + " OR ".join(conds) + " ORDER BY id DESC", args).fetchall():
            its = db().execute("SELECT product_name,quantity,color,size FROM order_items WHERE order_id=?", (o["id"],)).fetchall()
            rows.append({"o": o, "items": ", ".join(f"{i['product_name']}{' (' + variant_label(i['color'], i['size']) + ')' if i['color'] or i['size'] else ''} ×{i['quantity']}" for i in its)})
    return render_template("orders.html", rows=rows)

@app.get("/orders/<int:oid>")
def order_chat(oid):
    o = db().execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if is_agent() and o: return redirect(url_for("admin_order", oid=oid))
    if not can_access(o):
        flash("Please log in to view this order.", "error"); return redirect(url_for("login", next=request.path))
    items = db().execute("SELECT * FROM order_items WHERE order_id=?", (oid,)).fetchall()
    steps = [("Pending", "Order placed"), ("Confirmed", "Confirmed"), ("Shipped", "On its way"), ("Delivered", "Delivered")]
    return render_template("order_chat.html", o=o, items=items, steps=steps, new=bool(request.args.get("new")))

@app.post("/orders/<int:oid>/chat")
def order_chat_post(oid):
    conn = db(); o = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not can_access(o) or is_agent(): abort(404)
    text = request.form.get("text", "").strip()[:1000]; action = request.form.get("action", "")
    if action not in ACTION_TEXT: action = ""
    try: img = save_chat_image(request.files.get("image"))
    except ValueError as e: return jsonify(ok=False, error=str(e)), 400
    if not (text or img or action): return jsonify(ok=False, error="Empty message"), 400
    add_msg(conn, oid, "customer", text or ACTION_TEXT.get(action, ""), img)
    conn.execute("UPDATE orders SET agent_unread=1 WHERE id=?", (oid,))
    bot_reply(conn, o, text, action, img); conn.commit()
    return jsonify(ok=True)

@app.get("/api/orders/<int:oid>/messages")
def api_order_messages(oid):
    conn = db(); o = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not can_access(o): abort(404)
    agent = is_agent(); after = request.args.get("after", 0, type=int)
    col = "agent_unread" if agent else "customer_unread"
    if o[col]:
        conn.execute("UPDATE orders SET %s=0 WHERE id=?" % col, (oid,)); conn.commit()
    rows = conn.execute("SELECT * FROM order_messages WHERE order_id=? AND id>? ORDER BY id", (oid, after)).fetchall()
    quick = [] if (agent or o["status"] == "Cancelled") else QUICK.get(o["chat_state"], [])
    return jsonify(messages=[msg_json(oid, r) for r in rows], status=o["status"], status_label=STATUS_LABEL.get(o["status"], o["status"]),
                   payment_status=o["payment_status"], state=o["chat_state"], quick=quick, support=get_settings()["support_name"])

@app.get("/files/<int:oid>/<name>")
def chat_file(oid, name):
    o = db().execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not can_access(o): abort(404)
    if not db().execute("SELECT 1 FROM order_messages WHERE order_id=? AND image=?", (oid, name)).fetchone(): abort(404)
    if USE_PG:
        row = db().execute("SELECT mime,data FROM chat_files WHERE name=?", (name,)).fetchone()
        if not row: abort(404)
        return Response(bytes(row["data"]), mimetype=row["mime"], headers={"Cache-Control": "private, max-age=86400"})
    return send_from_directory(CHAT_DIR, name)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name=request.form.get("name","").strip(); email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        if not name or not email or len(password)<8:
            flash("Enter your name, valid email and a password of at least 8 characters.", "error")
        else:
            try:
                cur=db().execute("INSERT INTO users(name,email,password,role,created_at) VALUES(?,?,?,?,?)",(name,email,generate_password_hash(password),"customer",datetime.now().isoformat(timespec="seconds")))
                db().commit(); session.update(user_id=cur.lastrowid, role="customer")
                flash("Welcome to Stark Store!", "success"); return redirect(url_for("home"))
            except DB_INTEGRITY: flash("That email is already registered.", "error")
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower(); password=request.form.get("password","")
        user=db().execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if user and check_password_hash(user["password"],password):
            keep=session.get("my_orders",[]); session.clear(); session.update(user_id=user["id"],role=user["role"],my_orders=keep)
            return redirect(url_for("admin") if user["role"]=="admin" else request.args.get("next") or url_for("home"))
        flash("Email or password is incorrect.", "error")
    return render_template("auth.html", mode="login")

@app.get("/logout")
def logout():
    session.clear(); return redirect(url_for("home"))

@app.route("/admin")
@admin_required
def admin():
    conn=db()
    stats={
      "sales": conn.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE status!='Cancelled'").fetchone()[0],
      "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
      "products": conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
      "visits": conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0],
      "customers": conn.execute("SELECT COUNT(*) FROM users WHERE role='customer'").fetchone()[0],
      "pending": conn.execute("SELECT COUNT(*) FROM orders WHERE status='Pending'").fetchone()[0]
    }
    orders=conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 8").fetchall()
    products=conn.execute("SELECT * FROM products ORDER BY id DESC LIMIT 8").fetchall()
    reviews=conn.execute("SELECT COUNT(*) FROM reviews WHERE approved=0").fetchone()[0]
    return render_template("admin.html",stats=stats,orders=orders,products=products,pending_reviews=reviews)

VIDEO_EXT = {"mp4", "webm", "mov", "m4v"}
class MediaError(ValueError): pass

def save_media(f):
    """Validate and store one product image or video. Returns (filename, kind) or None."""
    if not f or not f.filename: return None
    ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    head = f.stream.read(12); f.stream.seek(0, 2); size = f.stream.tell(); f.stream.seek(0)
    if ext in ALLOWED:
        kind, limit = "image", 8 * 1024 * 1024
        ok = head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"GIF8")) or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    elif ext in VIDEO_EXT:
        kind, limit = "video", 100 * 1024 * 1024
        ok = head[4:8] == b"ftyp" or head[:4] == b"\x1a\x45\xdf\xa3"
    else:
        raise MediaError(f"“{f.filename}” is not supported. Use JPG, PNG, WEBP, GIF images or MP4, WEBM, MOV videos.")
    if not ok: raise MediaError(f"“{f.filename}” does not look like a valid {kind} file.")
    if size > limit: raise MediaError(f"“{f.filename}” is too large (max 8 MB per image, 100 MB per video).")
    name = secrets.token_hex(12) + "." + ext
    f.save(os.path.join(app.config["UPLOAD_FOLDER"], name))
    return name, kind

def drop_file(name):
    if name.startswith("http"): return  # remote (Cloudinary) file: nothing on disk
    try: os.remove(os.path.join(app.config["UPLOAD_FOLDER"], name))
    except OSError: pass

def cloud_media_from_form():
    """Files the browser already uploaded straight to Cloudinary (JSON list of urls)."""
    raw = request.form.get("media_urls", "").strip()
    if not raw: return []
    try: items = json.loads(raw)
    except ValueError: raise MediaError("The upload data was invalid. Please try again.")
    prefix = f"https://res.cloudinary.com/{CLOUD_NAME}/"
    out = []
    for it in (items if isinstance(items, list) else [])[:12]:
        url = str(it.get("url", "")) if isinstance(it, dict) else ""
        if not CLOUD_NAME or not url.startswith(prefix): raise MediaError("Invalid media URL.")
        out.append((url, "video" if "/video/upload/" in url else "image"))
    return out

def save_media_files(files):
    if ON_VERCEL and any(f and f.filename for f in files):
        raise MediaError("On Vercel, product images and videos are uploaded through Cloudinary (see the README setup).")
    out = []
    try:
        for f in files[:12]:
            r = save_media(f)
            if r: out.append(r)
    except ValueError:
        for n, _ in out: drop_file(n)
        raise
    return out

def product_media(pid, cover=""):
    rows = db().execute("SELECT * FROM product_media WHERE product_id=? ORDER BY id", (pid,)).fetchall()
    return sorted(rows, key=lambda m: 0 if m["filename"] == cover else 1)

@app.route("/admin/products", methods=["GET","POST"])
@admin_required
def admin_products():
    if request.method=="POST":
        try:
            media=cloud_media_from_form()+save_media_files(request.files.getlist("media"))
            image=next((n for n,k in media if k=="image"),"")
            cur=db().execute("INSERT INTO products(name,category,description,price,discount,stock,image,created_at,colors,sizes) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (request.form["name"].strip(),request.form.get("category","General").strip(),request.form.get("description","").strip(),
               *parse_prices(request.form),
               max(0,int(request.form.get("stock",0))),image,datetime.now().isoformat(timespec="seconds"),
               clean_options(request.form.get("colors")),clean_options(request.form.get("sizes"))))
            for n,k in media: db().execute("INSERT INTO product_media(product_id,filename,kind) VALUES(?,?,?)",(cur.lastrowid,n,k))
            db().commit(); flash("Product published.", "success")
        except MediaError as e: flash(str(e), "error")
        except (ValueError,KeyError): flash("Please check the details: sale price must not be higher than the original price, and use JPG/PNG/WEBP images.", "error")
        return redirect(url_for("admin_products"))
    products=db().execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return render_template("admin_products.html",products=products)

@app.route("/admin/products/<int:pid>/edit", methods=["GET","POST"])
@admin_required
def edit_product(pid):
    p=db().execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
    if not p: abort(404)
    if request.method=="POST":
        try:
            media=cloud_media_from_form()+save_media_files(request.files.getlist("media"))
            image=p["image"] or next((n for n,k in media if k=="image"),"")
            for n,k in media: db().execute("INSERT INTO product_media(product_id,filename,kind) VALUES(?,?,?)",(pid,n,k))
            db().execute("UPDATE products SET name=?,category=?,description=?,price=?,discount=?,stock=?,image=?,active=?,colors=?,sizes=? WHERE id=?",
              (request.form["name"].strip(),request.form.get("category","General").strip(),request.form.get("description","").strip(),
               *parse_prices(request.form),
               max(0,int(request.form.get("stock",0))),image,1 if request.form.get("active") else 0,
               clean_options(request.form.get("colors")),clean_options(request.form.get("sizes")),pid))
            db().commit(); flash("Product updated.", "success"); return redirect(url_for("admin_products"))
        except MediaError as e: flash(str(e), "error")
        except (ValueError,KeyError): flash("Please check the details: sale price must not be higher than the original price.", "error")
    return render_template("edit_product.html",p=p,media=product_media(pid,p["image"]))

@app.post("/admin/products/<int:pid>/delete")
@admin_required
def delete_product(pid):
    for m in db().execute("SELECT filename FROM product_media WHERE product_id=?",(pid,)).fetchall(): drop_file(m["filename"])
    db().execute("DELETE FROM product_media WHERE product_id=?",(pid,)); db().execute("DELETE FROM products WHERE id=?",(pid,)); db().commit()
    flash("Product deleted.", "success"); return redirect(url_for("admin_products"))

@app.post("/admin/products/<int:pid>/media/<int:mid>/delete")
@admin_required
def delete_media(pid, mid):
    m = db().execute("SELECT * FROM product_media WHERE id=? AND product_id=?", (mid, pid)).fetchone()
    if not m: abort(404)
    db().execute("DELETE FROM product_media WHERE id=?", (mid,)); drop_file(m["filename"])
    p = db().execute("SELECT image FROM products WHERE id=?", (pid,)).fetchone()
    if p and p["image"] == m["filename"]:
        nxt = db().execute("SELECT filename FROM product_media WHERE product_id=? AND kind='image' ORDER BY id LIMIT 1", (pid,)).fetchone()
        db().execute("UPDATE products SET image=? WHERE id=?", (nxt["filename"] if nxt else "", pid))
    db().commit(); flash("File removed.", "success")
    return redirect(url_for("edit_product", pid=pid))

@app.post("/admin/products/<int:pid>/media/<int:mid>/cover")
@admin_required
def cover_media(pid, mid):
    m = db().execute("SELECT * FROM product_media WHERE id=? AND product_id=? AND kind='image'", (mid, pid)).fetchone()
    if not m: abort(404)
    db().execute("UPDATE products SET image=? WHERE id=?", (m["filename"], pid)); db().commit(); flash("Cover image updated.", "success")
    return redirect(url_for("edit_product", pid=pid))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    status = request.args.get("status", "")
    counts = {r[0]: r[1] for r in db().execute("SELECT status,COUNT(*) FROM orders GROUP BY status").fetchall()}
    if status in STATUS_LABEL: orders = db().execute("SELECT * FROM orders WHERE status=? ORDER BY agent_unread DESC, id DESC", (status,)).fetchall()
    else: status = ""; orders = db().execute("SELECT * FROM orders ORDER BY agent_unread DESC, id DESC").fetchall()
    return render_template("admin_orders.html", orders=orders, counts=counts, total_all=sum(counts.values()), current=status)

@app.get("/admin/orders/<int:oid>")
@admin_required
def admin_order(oid):
    o = db().execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o: abort(404)
    items = db().execute("SELECT * FROM order_items WHERE order_id=?", (oid,)).fetchall()
    return render_template("admin_order.html", o=o, items=items, status_options=list(STATUS_LABEL.items()), pay_options=PAY_STATUSES)

@app.post("/admin/orders/<int:oid>/reply")
@admin_required
def admin_reply(oid):
    conn = db()
    if not conn.execute("SELECT 1 FROM orders WHERE id=?", (oid,)).fetchone(): abort(404)
    text = request.form.get("text", "").strip()[:1000]
    try: img = save_chat_image(request.files.get("image"))
    except ValueError as e: return jsonify(ok=False, error=str(e)), 400
    if not (text or img): return jsonify(ok=False, error="Empty message"), 400
    add_msg(conn, oid, "agent", text, img)
    conn.execute("UPDATE orders SET customer_unread=1, agent_unread=0 WHERE id=?", (oid,)); conn.commit()
    return jsonify(ok=True)

@app.post("/admin/orders/<int:oid>/status")
@admin_required
def order_status(oid):
    conn = db(); o = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o: abort(404)
    status = request.form.get("status", o["status"]); pay = request.form.get("payment_status", o["payment_status"])
    if status not in STATUS_LABEL or pay not in PAY_STATUSES: abort(400)
    conn.execute("UPDATE orders SET status=?,payment_status=? WHERE id=?", (status, pay, oid))
    changed = False
    if pay == "Paid" and o["payment_status"] != "Paid": add_msg(conn, oid, "system", "✅ Your payment has been verified. Thank you!"); changed = True
    if status != o["status"]: add_msg(conn, oid, "system", STATUS_MSG[status].format(id=oid)); changed = True
    if status != "Pending" and o["chat_state"] in ("await_payment", "payment_review", "await_new_address"):
        conn.execute("UPDATE orders SET chat_state='done' WHERE id=?", (oid,))
    if changed: conn.execute("UPDATE orders SET customer_unread=1 WHERE id=?", (oid,))
    conn.commit(); flash("Order updated.", "success")
    return redirect(url_for("admin_order", oid=oid) if request.form.get("from") == "detail" else url_for("admin_orders"))

@app.post("/admin/orders/<int:oid>/verify")
@admin_required
def verify_payment(oid):
    conn = db(); o = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not o: abort(404)
    conn.execute("UPDATE orders SET payment_status='Paid', chat_state='done', status=CASE WHEN status='Pending' THEN 'Confirmed' ELSE status END, customer_unread=1 WHERE id=?", (oid,))
    add_msg(conn, oid, "system", "✅ Your payment has been verified.")
    if o["status"] == "Pending": add_msg(conn, oid, "system", STATUS_MSG["Confirmed"].format(id=oid))
    conn.commit(); flash("Payment verified and order confirmed.", "success")
    return redirect(url_for("admin_order", oid=oid))

@app.route("/admin/payments", methods=["GET", "POST"])
@admin_required
def admin_payments():
    if request.method == "POST":
        conn = db()
        for k in SETTING_DEFAULTS:
            v = ("1" if request.form.get(k) else "0") if k.startswith("pay_") else request.form.get(k, "").strip()[:500]
            conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, v))
        conn.commit(); _settings_cache["v"] = None
        f = request.form
        for flag, field, label in (("pay_bank", "bank_number", "Bank Transfer"), ("pay_easypaisa", "ep_number", "Easypaisa"), ("pay_jazzcash", "jc_number", "JazzCash"), ("pay_card", "card_info", "Card / Online")):
            if f.get(flag) and not f.get(field, "").strip(): flash(f"{label} is ON but has no account details yet.", "error")
        flash("Payment settings saved.", "success")
        return redirect(url_for("admin_payments"))
    return render_template("admin_payments.html", s=get_settings())

@app.route("/admin/reviews")
@admin_required
def admin_reviews():
    reviews=db().execute("SELECT r.*,p.name AS product_name FROM reviews r JOIN products p ON p.id=r.product_id ORDER BY r.id DESC").fetchall()
    return render_template("admin_reviews.html",reviews=reviews)

@app.post("/admin/reviews/<int:rid>/approve")
@admin_required
def approve_review(rid):
    db().execute("UPDATE reviews SET approved=1 WHERE id=?",(rid,)); db().commit()
    return redirect(url_for("admin_reviews"))

@app.post("/admin/reviews/<int:rid>/delete")
@admin_required
def delete_review(rid):
    db().execute("DELETE FROM reviews WHERE id=?",(rid,)); db().commit()
    return redirect(url_for("admin_reviews"))

@app.route("/admin/analytics")
@admin_required
def analytics():
    rows=db().execute("SELECT visited_on,COUNT(*) AS visits FROM visits GROUP BY visited_on ORDER BY visited_on DESC LIMIT 14").fetchall()
    top=db().execute("SELECT product_name,SUM(quantity) AS sold FROM order_items GROUP BY product_name ORDER BY sold DESC LIMIT 5").fetchall()
    return render_template("analytics.html",rows=rows,top=top)

@app.errorhandler(413)
def too_large(_): return "Upload is too large. Images: max 8 MB each, videos: max 100 MB each.", 413

if __name__ == "__main__":
    if init_db(): migrate_media()
    app.run(debug=os.environ.get("FLASK_DEBUG")=="1", host="127.0.0.1", port=int(os.environ.get("PORT",5000)))
