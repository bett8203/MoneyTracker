from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = "money_tracker_secret_key"


# =========================
# DATABASE CONNECTION
# =========================

def get_db():
    connection = sqlite3.connect("money_tracker.db")
    connection.row_factory = sqlite3.Row
    return connection


# =========================
# DATABASE SETUP
# =========================

def setup_database():

    connection = get_db()
    cursor = connection.cursor()

    # Check if is_active column already exists
    cursor.execute("PRAGMA table_info(users)")
    columns = [column["name"] for column in cursor.fetchall()]

    # Add is_active if it does not exist
    if "is_active" not in columns:

        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN is_active INTEGER DEFAULT 1
            """
        )

        # Make all existing users active
        cursor.execute(
            """
            UPDATE users
            SET is_active = 1
            WHERE is_active IS NULL
            """
        )

    connection.commit()
    connection.close()


# Run database setup
setup_database()


# =========================
# HOME
# =========================

@app.route("/")
def home():

    return render_template("index.html")


# =========================
# REGISTER
# =========================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        password_hash = generate_password_hash(password)

        connection = get_db()
        cursor = connection.cursor()

        try:

            cursor.execute(
                """
                INSERT INTO users
                (name, email, password, is_admin, is_active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    password_hash,
                    0,
                    1
                )
            )

            connection.commit()

        except sqlite3.IntegrityError:

            connection.close()

            return "Email already registered."

        connection.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# =========================
# LOGIN
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        connection = get_db()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM users
            WHERE email=?
            """,
            (email,)
        )

        user = cursor.fetchone()

        connection.close()

        if user:

            stored_password = user["password"]

            if check_password_hash(
                stored_password,
                password
            ):

                # Check if account is active
                if user["is_active"] != 1:

                    return """
                    <h3>Account Deactivated</h3>
                    <p>Your account has been deactivated by the administrator.</p>
                    <a href="/login">Back to Login</a>
                    """

                # Save login session
                session["user_email"] = user["email"]

                # Save admin status
                session["is_admin"] = user["is_admin"]

                return redirect(
                    url_for("dashboard")
                )

        return "Invalid email or password."

    return render_template("login.html")


# =========================
# USER DASHBOARD
# =========================

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]

    connection = get_db()
    cursor = connection.cursor()

    # =========================
    # ADD TRANSACTION
    # =========================

    if request.method == "POST":

        transaction_type = request.form["type"]
        amount = float(request.form["amount"])
        description = request.form["description"]

        cursor.execute(
            """
            INSERT INTO transactions
            (user_email, type, amount, description)
            VALUES (?, ?, ?, ?)
            """,
            (
                user_email,
                transaction_type,
                amount,
                description
            )
        )

        connection.commit()

    # =========================
    # GET TRANSACTIONS
    # =========================

    cursor.execute(
        """
        SELECT
            id,
            type,
            amount,
            description,
            date
        FROM transactions
        WHERE user_email=?
        ORDER BY date DESC
        """,
        (user_email,)
    )

    transactions = cursor.fetchall()

    # =========================
    # CALCULATE TOTALS
    # =========================

    cursor.execute(
        """
        SELECT
            SUM(
                CASE
                    WHEN type='Income'
                    THEN amount
                    ELSE 0
                END
            ),
            SUM(
                CASE
                    WHEN type='Expense'
                    THEN amount
                    ELSE 0
                END
            )
        FROM transactions
        WHERE user_email=?
        """,
        (user_email,)
    )

    totals = cursor.fetchone()

    total_income = totals[0] or 0
    total_expenses = totals[1] or 0

    balance = total_income - total_expenses

    connection.close()

    return render_template(
        "dashboard.html",
        transactions=transactions,
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance
    )


# =========================
# EDIT TRANSACTION
# =========================

@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]

    connection = get_db()
    cursor = connection.cursor()

    if request.method == "POST":

        transaction_type = request.form["type"]
        amount = float(request.form["amount"])
        description = request.form["description"]

        cursor.execute(
            """
            UPDATE transactions
            SET
                type=?,
                amount=?,
                description=?
            WHERE
                id=?
                AND user_email=?
            """,
            (
                transaction_type,
                amount,
                description,
                id,
                user_email
            )
        )

        connection.commit()
        connection.close()

        return redirect(
            url_for("dashboard")
        )

    cursor.execute(
        """
        SELECT *
        FROM transactions
        WHERE
            id=?
            AND user_email=?
        """,
        (id, user_email)
    )

    transaction = cursor.fetchone()

    connection.close()

    if not transaction:
        return "Transaction not found."

    return render_template(
        "edit.html",
        transaction=transaction
    )


# =========================
# DELETE TRANSACTION
# =========================

@app.route("/delete/<int:id>")
def delete(id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        DELETE FROM transactions
        WHERE
            id=?
            AND user_email=?
        """,
        (id, user_email)
    )

    connection.commit()
    connection.close()

    return redirect(
        url_for("dashboard")
    )


# =========================
# ADMIN DASHBOARD
# =========================

@app.route("/admin")
def admin():

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    # =========================
    # GET USERS
    # =========================

    cursor.execute(
        """
        SELECT
            id,
            name,
            email,
            is_admin,
            is_active
        FROM users
        ORDER BY id DESC
        """
    )

    users = cursor.fetchall()

    # =========================
    # GET TRANSACTIONS
    # =========================

    cursor.execute(
        """
        SELECT
            id,
            user_email,
            type,
            amount,
            description,
            date
        FROM transactions
        ORDER BY date DESC
        """
    )

    all_transactions = cursor.fetchall()

    # =========================
    # TOTAL USERS
    # =========================

    cursor.execute(
        "SELECT COUNT(*) FROM users"
    )

    total_users = cursor.fetchone()[0]

    # =========================
    # TOTAL INCOME
    # =========================

    cursor.execute(
        """
        SELECT SUM(amount)
        FROM transactions
        WHERE type='Income'
        """
    )

    total_income = cursor.fetchone()[0] or 0

    # =========================
    # TOTAL EXPENSES
    # =========================

    cursor.execute(
        """
        SELECT SUM(amount)
        FROM transactions
        WHERE type='Expense'
        """
    )

    total_expenses = cursor.fetchone()[0] or 0

    # =========================
    # BALANCE
    # =========================

    platform_balance = total_income - total_expenses

    connection.close()

    return render_template(
        "admin.html",
        users=users,
        all_transactions=all_transactions,
        total_users=total_users,
        total_income=total_income,
        total_expenses=total_expenses,
        platform_balance=platform_balance
    )


# =========================
# ADMIN — VIEW USER
# =========================

@app.route("/admin/user/<int:user_id>")
def admin_user(user_id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            name,
            email,
            is_admin,
            is_active
        FROM users
        WHERE id=?
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:

        connection.close()

        return "User not found."

    cursor.execute(
        """
        SELECT
            id,
            type,
            amount,
            description,
            date
        FROM transactions
        WHERE user_email=?
        ORDER BY date DESC
        """,
        (user["email"],)
    )

    transactions = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            SUM(
                CASE
                    WHEN type='Income'
                    THEN amount
                    ELSE 0
                END
            ),
            SUM(
                CASE
                    WHEN type='Expense'
                    THEN amount
                    ELSE 0
                END
            )
        FROM transactions
        WHERE user_email=?
        """,
        (user["email"],)
    )

    totals = cursor.fetchone()

    total_income = totals[0] or 0
    total_expenses = totals[1] or 0

    balance = total_income - total_expenses

    connection.close()

    return render_template(
        "admin_user.html",
        user=user,
        transactions=transactions,
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance
    )


# =========================
# ADMIN — DEACTIVATE USER
# =========================

@app.route(
    "/admin/user/<int:user_id>/deactivate",
    methods=["POST"]
)
def deactivate_user(user_id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    # Get user
    cursor.execute(
        """
        SELECT email, is_admin
        FROM users
        WHERE id=?
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:

        connection.close()

        return "User not found."

    # Do not allow admin to deactivate themselves
    if user["email"] == session["user_email"]:

        connection.close()

        return "You cannot deactivate your own administrator account."

    # Do not deactivate another administrator
    if user["is_admin"] == 1:

        connection.close()

        return "Administrator accounts cannot be deactivated here."

    cursor.execute(
        """
        UPDATE users
        SET is_active=0
        WHERE id=?
        """,
        (user_id,)
    )

    connection.commit()
    connection.close()

    return redirect(url_for("admin"))


# =========================
# ADMIN — ACTIVATE USER
# =========================

@app.route(
    "/admin/user/<int:user_id>/activate",
    methods=["POST"]
)
def activate_user(user_id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id
        FROM users
        WHERE id=?
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:

        connection.close()

        return "User not found."

    cursor.execute(
        """
        UPDATE users
        SET is_active=1
        WHERE id=?
        """,
        (user_id,)
    )

    connection.commit()
    connection.close()

    return redirect(url_for("admin"))


# =========================
# LOGOUT
# =========================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================
# RUN APPLICATION
# =========================

if __name__ == "__main__":

    app.run(debug=True)