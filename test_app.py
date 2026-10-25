import pytest

import app as expense_app


@pytest.fixture
def client(tmp_path):
    """Use a fresh temporary database for every test."""
    expense_app.DATABASE = str(tmp_path / "test.db")
    expense_app.init_db()
    expense_app.app.config["TESTING"] = True
    with expense_app.app.test_client() as client:
        yield client


def login_headers(client, username="ramya", password="secret123"):
    """Register a user, log in and return the Authorization header."""
    client.post("/api/register", json={"username": username, "password": password})
    token = client.post(
        "/api/login", json={"username": username, "password": password}
    ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth(client):
    return login_headers(client)


def add_expense(client, auth, title="Lunch", amount=150, category="Food", date="2026-10-20"):
    return client.post(
        "/api/expenses",
        json={"title": title, "amount": amount, "category": category, "date": date},
        headers=auth,
    )


# ---------- Home ----------
def test_home_returns_running_message(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "running" in response.get_json()["message"]


# ---------- Authentication ----------
def test_register_user(client):
    response = client.post("/api/register", json={"username": "ramya", "password": "secret123"})
    assert response.status_code == 201
    assert response.get_json()["username"] == "ramya"


def test_register_duplicate_username_returns_409(client):
    client.post("/api/register", json={"username": "ramya", "password": "secret123"})
    response = client.post("/api/register", json={"username": "ramya", "password": "other123"})
    assert response.status_code == 409


def test_register_with_short_password_returns_400(client):
    response = client.post("/api/register", json={"username": "ramya", "password": "123"})
    assert response.status_code == 400


def test_login_returns_token(client):
    client.post("/api/register", json={"username": "ramya", "password": "secret123"})
    response = client.post("/api/login", json={"username": "ramya", "password": "secret123"})
    assert response.status_code == 200
    assert "token" in response.get_json()


def test_login_with_wrong_password_returns_401(client):
    client.post("/api/register", json={"username": "ramya", "password": "secret123"})
    response = client.post("/api/login", json={"username": "ramya", "password": "wrong-pass"})
    assert response.status_code == 401


def test_expenses_without_token_returns_401(client):
    assert client.get("/api/expenses").status_code == 401
    assert client.get("/api/summary").status_code == 401


def test_expenses_with_invalid_token_returns_401(client):
    response = client.get("/api/expenses", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_users_cannot_see_each_others_expenses(client, auth):
    add_expense(client, auth, title="Ramya lunch")
    other = login_headers(client, username="other", password="secret456")
    assert client.get("/api/expenses", headers=other).get_json() == []
    assert client.get("/api/expenses/1", headers=other).status_code == 404
    assert client.delete("/api/expenses/1", headers=other).status_code == 404
    assert len(client.get("/api/expenses", headers=auth).get_json()) == 1


# ---------- Create and validation ----------
def test_create_expense(client, auth):
    response = add_expense(client, auth)
    assert response.status_code == 201
    data = response.get_json()
    assert data["id"] == 1
    assert data["title"] == "Lunch"
    assert data["amount"] == 150.0


def test_create_expense_with_invalid_data_returns_400(client, auth):
    response = client.post(
        "/api/expenses",
        json={"title": "", "amount": -5, "category": "Food", "date": "bad"},
        headers=auth,
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_amount_must_be_positive(client, auth):
    assert add_expense(client, auth, amount=0).status_code == 400


def test_date_must_be_valid_format(client, auth):
    assert add_expense(client, auth, date="20-10-2026").status_code == 400


# ---------- Read ----------
def test_list_expenses(client, auth):
    add_expense(client, auth, title="Lunch")
    add_expense(client, auth, title="Bus", category="Travel")
    response = client.get("/api/expenses", headers=auth)
    assert response.status_code == 200
    assert len(response.get_json()) == 2


def test_filter_by_category(client, auth):
    add_expense(client, auth, title="Lunch", category="Food")
    add_expense(client, auth, title="Bus", category="Travel")
    data = client.get("/api/expenses?category=Food", headers=auth).get_json()
    assert len(data) == 1
    assert data[0]["category"] == "Food"


def test_filter_by_month(client, auth):
    add_expense(client, auth, title="October lunch", date="2026-10-20")
    add_expense(client, auth, title="September dinner", date="2026-09-02")
    data = client.get("/api/expenses?month=2026-10", headers=auth).get_json()
    assert len(data) == 1
    assert data[0]["title"] == "October lunch"


def test_get_single_expense(client, auth):
    add_expense(client, auth)
    response = client.get("/api/expenses/1", headers=auth)
    assert response.status_code == 200
    assert response.get_json()["title"] == "Lunch"


def test_get_missing_expense_returns_404(client, auth):
    assert client.get("/api/expenses/99", headers=auth).status_code == 404


# ---------- Update and delete ----------
def test_update_expense(client, auth):
    add_expense(client, auth)
    response = client.put(
        "/api/expenses/1",
        json={"title": "Lunch with friends", "amount": 180,
              "category": "Food", "date": "2026-10-20"},
        headers=auth,
    )
    assert response.status_code == 200
    assert client.get("/api/expenses/1", headers=auth).get_json()["amount"] == 180.0


def test_update_missing_expense_returns_404(client, auth):
    response = client.put(
        "/api/expenses/99",
        json={"title": "x", "amount": 1, "category": "Food", "date": "2026-10-20"},
        headers=auth,
    )
    assert response.status_code == 404


def test_delete_expense(client, auth):
    add_expense(client, auth)
    assert client.delete("/api/expenses/1", headers=auth).status_code == 200
    assert client.get("/api/expenses/1", headers=auth).status_code == 404


def test_delete_missing_expense_returns_404(client, auth):
    assert client.delete("/api/expenses/99", headers=auth).status_code == 404


# ---------- Summary ----------
def test_summary_totals_and_categories(client, auth):
    add_expense(client, auth, amount=150, category="Food", date="2026-10-20")
    add_expense(client, auth, amount=40, category="Travel", date="2026-10-21")
    add_expense(client, auth, amount=200, category="Food", date="2026-09-02")
    data = client.get("/api/summary?month=2026-10", headers=auth).get_json()
    assert data["total_spent"] == 190.0
    assert data["expense_count"] == 2
    assert data["by_category"] == {"Food": 150.0, "Travel": 40.0}


def test_summary_without_month_covers_all(client, auth):
    add_expense(client, auth, amount=150)
    add_expense(client, auth, amount=200, date="2026-09-02")
    data = client.get("/api/summary", headers=auth).get_json()
    assert data["month"] == "all"
    assert data["total_spent"] == 350.0