import os
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Flask, jsonify, request, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
DATABASE = os.environ.get("DATABASE_PATH", "expenses.db")


# ---------- Database helpers ----------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DATABASE) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS users (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   username TEXT NOT NULL UNIQUE,
                   password_hash TEXT NOT NULL
               )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS expenses (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   user_id INTEGER NOT NULL,
                   title TEXT NOT NULL,
                   amount REAL NOT NULL,
                   category TEXT NOT NULL,
                   date TEXT NOT NULL,
                   FOREIGN KEY (user_id) REFERENCES users (id)
               )"""
        )


# ---------- Authentication ----------
def create_token(user_id):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=12),
    }
    return jwt.encode(payload, app.config["SECRET_KEY"], algorithm="HS256")


def token_required(view):
    """Allow the request only if it has a valid 'Authorization: Bearer <token>' header."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header."}), 401
        try:
            payload = jwt.decode(header[7:], app.config["SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired. Please log in again."}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token."}), 401
        g.user_id = int(payload["sub"])
        return view(*args, **kwargs)
    return wrapper


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    if len(username) < 3 or len(password) < 6:
        return jsonify({"error": "username needs 3+ characters and password 6+ characters."}), 400
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already taken."}), 409
    return jsonify({"id": cur.lastrowid, "username": username}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid username or password."}), 401
    return jsonify({"token": create_token(user["id"])})


# ---------- Validation ----------
def validate(data):
    """Return (clean_data, error_message)."""
    if not data:
        return None, "Request body must be JSON."
    title = str(data.get("title", "")).strip()
    category = str(data.get("category", "")).strip()
    date = str(data.get("date", "")).strip()
    if not title:
        return None, "title is required."
    if not category:
        return None, "category is required."
    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        return None, "amount must be a number."
    if amount <= 0:
        return None, "amount must be greater than 0."
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return None, "date must be in YYYY-MM-DD format."
    return {"title": title, "amount": amount, "category": category, "date": date}, None


def not_found():
    return jsonify({"error": "Expense not found."}), 404


# ---------- Expense routes (all need login) ----------
@app.route("/")
def home():
    return jsonify({"message": "Expense Tracker API is running.",
                    "endpoints": ["/api/register", "/api/login",
                                  "/api/expenses", "/api/summary"]})


@app.route("/api/expenses", methods=["GET"])
@token_required
def list_expenses():
    query = "SELECT * FROM expenses WHERE user_id = ?"
    params = [g.user_id]
    category = request.args.get("category")
    month = request.args.get("month")  # YYYY-MM
    if category:
        query += " AND category = ?"
        params.append(category)
    if month:
        query += " AND substr(date, 1, 7) = ?"
        params.append(month)
    query += " ORDER BY date DESC, id DESC"
    rows = get_db().execute(query, params).fetchall()
    return jsonify([{k: r[k] for k in ("id", "title", "amount", "category", "date")} for r in rows])


@app.route("/api/expenses/<int:expense_id>", methods=["GET"])
@token_required
def get_expense(expense_id):
    row = get_db().execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, g.user_id)
    ).fetchone()
    if not row:
        return not_found()
    return jsonify({k: row[k] for k in ("id", "title", "amount", "category", "date")})


@app.route("/api/expenses", methods=["POST"])
@token_required
def create_expense():
    data, error = validate(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO expenses (user_id, title, amount, category, date) VALUES (?, ?, ?, ?, ?)",
        (g.user_id, data["title"], data["amount"], data["category"], data["date"]),
    )
    db.commit()
    data["id"] = cur.lastrowid
    return jsonify(data), 201


@app.route("/api/expenses/<int:expense_id>", methods=["PUT"])
@token_required
def update_expense(expense_id):
    db = get_db()
    if not db.execute(
        "SELECT id FROM expenses WHERE id = ? AND user_id = ?", (expense_id, g.user_id)
    ).fetchone():
        return not_found()
    data, error = validate(request.get_json(silent=True))
    if error:
        return jsonify({"error": error}), 400
    db.execute(
        "UPDATE expenses SET title = ?, amount = ?, category = ?, date = ? "
        "WHERE id = ? AND user_id = ?",
        (data["title"], data["amount"], data["category"], data["date"], expense_id, g.user_id),
    )
    db.commit()
    data["id"] = expense_id
    return jsonify(data)


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
@token_required
def delete_expense(expense_id):
    db = get_db()
    cur = db.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, g.user_id)
    )
    db.commit()
    if cur.rowcount == 0:
        return not_found()
    return jsonify({"message": "Expense deleted."})


@app.route("/api/summary", methods=["GET"])
@token_required
def summary():
    month = request.args.get("month")  # optional YYYY-MM
    where, params = "WHERE user_id = ?", [g.user_id]
    if month:
        where += " AND substr(date, 1, 7) = ?"
        params.append(month)
    db = get_db()
    total = db.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count FROM expenses {where}", params
    ).fetchone()
    by_cat = db.execute(
        f"SELECT category, SUM(amount) AS total FROM expenses {where} "
        "GROUP BY category ORDER BY total DESC",
        params,
    ).fetchall()
    return jsonify({
        "month": month or "all",
        "total_spent": round(total["total"], 2),
        "expense_count": total["count"],
        "by_category": {r["category"]: round(r["total"], 2) for r in by_cat},
    })


init_db()

if __name__ == "__main__":
    app.run(debug=True)