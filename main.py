from datetime import date
from pathlib import Path
import sqlite3
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("Expense Tracker")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "expenses.db"
CATEGORIES_PATH = BASE_DIR / "categories.json"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        # Expenses Table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL CHECK (amount >= 0),
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT ''
            )
            """
        )
        # Budgets Table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                monthly_limit REAL NOT NULL CHECK (monthly_limit >= 0)
            )
            """
        )


# =============================================================================
# RESOURCE: Categories Taxonomy
# =============================================================================
@mcp.resource("expense://categories", mime_type="application/json")
def categories() -> str:
    """Read canonical categories and subcategories from categories.json."""
    if CATEGORIES_PATH.exists():
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return '{"General": ["Miscellaneous"]}'


# =============================================================================
# TOOLS: Add, Read & List
# =============================================================================
@mcp.tool()
def add_expense(
    expense_date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = "",
) -> str:
    """
    Add a new expense.
    Args:
        expense_date: YYYY-MM-DD format.
        amount: Numerical amount spent (must be non-negative).
        category: Main category (e.g., food, transport).
        subcategory: Specific subcategory (e.g., groceries, cab_rides).
        note: Optional description or context.
    """
    try:
        date.fromisoformat(expense_date)
    except ValueError as exc:
        raise ValueError("expense_date must be in YYYY-MM-DD format") from exc

    if amount < 0:
        raise ValueError("amount must be non-negative")
    if not category.strip():
        raise ValueError("category must not be empty")

    norm_category = category.strip().lower()
    norm_subcategory = subcategory.strip().lower()

    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO expenses
               (date, amount, category, subcategory, note)
               VALUES (?, ?, ?, ?, ?)""",
            (expense_date, amount, norm_category, norm_subcategory, note.strip()),
        )
        expense_id = cur.lastrowid

    return f"Successfully added expense #{expense_id}: {expense_date}, ₹{amount:.2f}, {norm_category} ({norm_subcategory})"


@mcp.tool()
def get_expense_by_id(expense_id: int) -> dict:
    """Retrieve full details of a specific expense transaction by its ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, date, amount, category, subcategory, note FROM expenses WHERE id = ?",
            (expense_id,),
        ).fetchone()

    if not row:
        raise ValueError(f"Expense with ID #{expense_id} not found.")

    return dict(row)


@mcp.tool()
def list_expenses(start_date: str, end_date: str) -> list[dict]:
    """List all expenses within an inclusive date range (YYYY-MM-DD)."""
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD format") from exc
    if start > end:
        raise ValueError("start_date must be on or before end_date")

    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, date, amount, category, subcategory, note
               FROM expenses
               WHERE date BETWEEN ? AND ?
               ORDER BY date ASC, id ASC""",
            (start_date, end_date),
        ).fetchall()
    return [dict(row) for row in rows]


# =============================================================================
# TOOLS: Update & Delete
# =============================================================================
@mcp.tool()
def update_expense(
    expense_id: int,
    expense_date: Optional[str] = None,
    amount: Optional[float] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    """
    Update details of an existing expense by its ID.
    Only fields that are provided will be changed.
    """
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        if not existing:
            raise ValueError(f"Expense with ID #{expense_id} does not exist.")

        updates = []
        params = []

        if expense_date is not None:
            date.fromisoformat(expense_date)  # validate
            updates.append("date = ?")
            params.append(expense_date)

        if amount is not None:
            if amount < 0:
                raise ValueError("amount must be non-negative")
            updates.append("amount = ?")
            params.append(amount)

        if category is not None:
            updates.append("category = ?")
            params.append(category.strip().lower())

        if subcategory is not None:
            updates.append("subcategory = ?")
            params.append(subcategory.strip().lower())

        if note is not None:
            updates.append("note = ?")
            params.append(note.strip())

        if not updates:
            return f"No fields were provided to update for expense #{expense_id}."

        params.append(expense_id)
        sql = f"UPDATE expenses SET {', '.join(updates)} WHERE id = ?"
        conn.execute(sql, params)

    return f"Successfully updated expense #{expense_id}."


@mcp.tool()
def delete_expense(expense_id: int) -> str:
    """Delete an expense entry from the database using its unique ID."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        if cur.rowcount == 0:
            raise ValueError(f"No expense found with ID #{expense_id}.")

    return f"Expense #{expense_id} was successfully deleted."


# =============================================================================
# TOOLS: Analytics & Aggregation
# =============================================================================
@mcp.tool()
def summarize_expenses(
    start_date: str,
    end_date: str,
    category: Optional[str] = None,
) -> dict:
    """Calculate the total and count of expenses in an inclusive date range, optionally filtered by category."""
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("Dates must use YYYY-MM-DD format") from exc
    if start > end:
        raise ValueError("start_date must be on or before end_date")

    sql = """SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS count
             FROM expenses WHERE date BETWEEN ? AND ?"""
    params: list = [start_date, end_date]

    if category and category.strip():
        sql += " AND LOWER(category) = LOWER(?)"
        params.append(category.strip())

    with get_connection() as conn:
        row = conn.execute(sql, params).fetchone()

    return {
        "start_date": start_date,
        "end_date": end_date,
        "category": category,
        "total": round(float(row["total"]), 2),
        "count": int(row["count"]),
    }


@mcp.tool()
def get_top_spending_categories(start_date: str, end_date: str, limit: int = 5) -> list[dict]:
    """
    Returns categories ranked by highest total expenditure within a date range.
    Useful for seeing where most money is being spent.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT category, ROUND(SUM(amount), 2) AS total_spent, COUNT(*) AS transactions
               FROM expenses
               WHERE date BETWEEN ? AND ?
               GROUP BY category
               ORDER BY total_spent DESC
               LIMIT ?""",
            (start_date, end_date, limit),
        ).fetchall()

    return [dict(r) for r in rows]


# =============================================================================
# TOOLS: Budget Management
# =============================================================================
@mcp.tool()
def set_category_budget(category: str, monthly_limit: float) -> str:
    """Set or update a monthly budget ceiling for a specific category (e.g., food, entertainment)."""
    if monthly_limit < 0:
        raise ValueError("Monthly budget limit must be non-negative.")

    norm_category = category.strip().lower()
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO budgets (category, monthly_limit)
               VALUES (?, ?)
               ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit""",
            (norm_category, monthly_limit),
        )

    return f"Budget for '{norm_category}' set to ₹{monthly_limit:.2f}/month."


@mcp.tool()
def check_budget_status(year_month: str) -> list[dict]:
    """
    Compare current spending against set monthly budgets for a specific month.
    Args:
        year_month: In YYYY-MM format (e.g. '2026-03').
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT 
                b.category,
                b.monthly_limit,
                COALESCE(SUM(e.amount), 0) AS total_spent,
                ROUND(b.monthly_limit - COALESCE(SUM(e.amount), 0), 2) AS remaining_balance,
                CASE 
                    WHEN COALESCE(SUM(e.amount), 0) > b.monthly_limit THEN 'EXCEEDED'
                    ELSE 'WITHIN_BUDGET'
                END AS status
            FROM budgets b
            LEFT JOIN expenses e 
                ON b.category = e.category 
                AND strftime('%Y-%m', e.date) = ?
            GROUP BY b.category
            """,
            (year_month,),
        ).fetchall()

    return [dict(r) for r in rows]


# Initialize tables on load
init_db()

if __name__ == "__main__":
    mcp.run()