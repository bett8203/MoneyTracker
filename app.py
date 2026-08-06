from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3

app = Flask(__name__)
app.secret_key = "money_tracker_secret_key"


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        connection = sqlite3.connect("money_tracker.db")
        cursor = connection.cursor()

        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (name, email, password)
        )

        connection.commit()
        connection.close()

        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        connection = sqlite3.connect("money_tracker.db")
        cursor = connection.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE email=? AND password=?",
            (email, password)
        )

        user = cursor.fetchone()
        connection.close()

        if user:
            session["user_email"] = email
            return redirect(url_for("dashboard"))
        else:
            return "Invalid email or password."

    return render_template("login.html")


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]

    connection = sqlite3.connect("money_tracker.db")
    cursor = connection.cursor()

    if request.method == "POST":
        transaction_type = request.form["type"]
        amount = float(request.form["amount"])
        description = request.form["description"]

        cursor.execute(
            """
            INSERT INTO transactions (user_email, type, amount, description)
            VALUES (?, ?, ?, ?)
            """,
            (user_email, transaction_type, amount, description)
        )

        connection.commit()

    cursor.execute("""
        SELECT id, type, amount, description, date
        FROM transactions
        WHERE user_email=?
        ORDER BY date DESC
    """, (user_email,))
    transactions = cursor.fetchall()

    cursor.execute("""
        SELECT
            SUM(CASE WHEN type='Income' THEN amount ELSE 0 END),
            SUM(CASE WHEN type='Expense' THEN amount ELSE 0 END)
        FROM transactions
        WHERE user_email=?
    """, (user_email,))
    totals = cursor.fetchone()

    total_income = totals[0] if totals[0] else 0
    total_expenses = totals[1] if totals[1] else 0
    balance = total_income - total_expenses

    connection.close()

    return render_template(
        "dashboard.html",
        transactions=transactions,
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance
    )


@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit(id):
    connection = sqlite3.connect("money_tracker.db")
    cursor = connection.cursor()

    if request.method == "POST":
        transaction_type = request.form["type"]
        amount = float(request.form["amount"])
        description = request.form["description"]

        cursor.execute("""
            UPDATE transactions
            SET type=?, amount=?, description=?
            WHERE id=?
        """, (transaction_type, amount, description, id))

        connection.commit()
        connection.close()

        return redirect(url_for("dashboard"))

    cursor.execute("SELECT * FROM transactions WHERE id=?", (id,))
    transaction = cursor.fetchone()

    connection.close()

    return render_template("edit.html", transaction=transaction)


@app.route("/delete/<int:id>")
def delete(id):
    connection = sqlite3.connect("money_tracker.db")
    cursor = connection.cursor()

    cursor.execute("DELETE FROM transactions WHERE id=?", (id,))

    connection.commit()
    connection.close()

    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)