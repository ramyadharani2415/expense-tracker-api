# Expense Tracker REST API

**Live API:** https://expense-tracker-api-wngk.onrender.com (free hosting, the first request may take up to a minute to wake up)

A REST API built with Python, Flask and SQLite to manage personal expenses, with user registration, login and JWT authentication.

## Features
- User registration and login with password hashing and JWT token authentication
- Each user can access only their own expenses
- Create, read, update and delete expenses (CRUD)
- Filter expenses by category and month
- Summary endpoint with total spent and category-wise totals
- Input validation with proper HTTP status codes (200, 201, 400, 401, 404, 409)
- Raw SQL queries using Python's built-in `sqlite3` module (parameterized queries)
- 24 automated tests using pytest

## Tech Stack
Python, Flask, SQLite, JWT (PyJWT), REST API, pytest

## Setup
```bash
git clone https://github.com/ramyadharani2415/expense-tracker-api.git
cd expense-tracker-api
pip install -r requirements.txt
python app.py
```
The API runs at http://127.0.0.1:5000

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register` | Create an account (`username`, `password`) |
| POST | `/api/login` | Get a JWT token |
| GET | `/api/expenses` | List your expenses (optional `?category=Food&month=2026-10`) |
| GET | `/api/expenses/<id>` | Get one expense |
| POST | `/api/expenses` | Add an expense |
| PUT | `/api/expenses/<id>` | Update an expense |
| DELETE | `/api/expenses/<id>` | Delete an expense |
| GET | `/api/summary` | Total spent and category-wise totals (optional `?month=2026-10`) |

All `/api/expenses` and `/api/summary` requests need the header:
`Authorization: Bearer <token>`

## Example (PowerShell)

```powershell
# Register and log in
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/register -Method Post -ContentType "application/json" -Body '{"username":"ramya","password":"secret123"}'
$r = Invoke-RestMethod -Uri http://127.0.0.1:5000/api/login -Method Post -ContentType "application/json" -Body '{"username":"ramya","password":"secret123"}'
$h = @{ Authorization = "Bearer $($r.token)" }

# Add an expense
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/expenses -Method Post -Headers $h -ContentType "application/json" -Body '{"title":"Lunch","amount":150,"category":"Food","date":"2026-10-20"}'
```

Response (`201 Created`):
```json
{"id": 1, "title": "Lunch", "amount": 150.0, "category": "Food", "date": "2026-10-20"}
```

## Validation Rules
- `title` and `category` are required
- `amount` must be a number greater than 0
- `date` must be in `YYYY-MM-DD` format
- `username` needs 3+ characters and `password` 6+ characters

## Running Tests
```bash
python -m pytest
```
24 automated tests cover authentication, all endpoints, validation errors and 401/404 cases. Each test uses a temporary database, so real data is not affected.
