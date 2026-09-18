from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
import os

from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from mpesa import stk_push

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "money_tracker_secret_key"
)

DATABASE = "money_tracker.db"


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    connection = sqlite3.connect(DATABASE)

    connection.row_factory = sqlite3.Row

    return connection


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or not password:
            return "All fields are required."

        password_hash = generate_password_hash(password)

        connection = get_db()
        cursor = connection.cursor()

        try:

            cursor.execute("""
                INSERT INTO users
                (
                    name,
                    email,
                    password,
                    is_admin,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                name,
                email,
                password_hash,
                0,
                1
            ))

            connection.commit()

        except sqlite3.IntegrityError:

            connection.close()

            return "Email already registered."

        connection.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        connection = get_db()
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                id,
                name,
                email,
                password,
                is_admin,
                is_active
            FROM users
            WHERE email=?
        """, (email,))

        user = cursor.fetchone()

        connection.close()

        if not user:
            return "Invalid email or password."

        if not check_password_hash(
            user["password"],
            password
        ):
            return "Invalid email or password."

        if user["is_active"] != 1:
            return (
                "Your account has been deactivated. "
                "Contact the administrator."
            )

        session["user_id"] = user["id"]
        session["user_email"] = user["email"]
        session["user_name"] = user["name"]
        session["is_admin"] = user["is_admin"]

        if user["is_admin"] == 1:
            return redirect(url_for("admin"))

        return redirect(url_for("dashboard"))

    return render_template("login.html")


# =========================================================
# USER DASHBOARD
# =========================================================

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]

    connection = get_db()
    cursor = connection.cursor()

    # -----------------------------------------------------
    # ADD MANUAL TRANSACTION
    # -----------------------------------------------------

    if request.method == "POST":

        try:

            transaction_type = request.form["type"]
            amount = float(request.form["amount"])
            description = request.form["description"].strip()

            if amount <= 0:
                connection.close()
                return "Amount must be greater than zero."

            if transaction_type not in ["Income", "Expense"]:
                connection.close()
                return "Invalid transaction type."

            cursor.execute("""
                INSERT INTO transactions
                (
                    user_email,
                    type,
                    amount,
                    description
                )
                VALUES (?, ?, ?, ?)
            """, (
                user_email,
                transaction_type,
                amount,
                description
            ))

            connection.commit()

        except (ValueError, KeyError):

            connection.close()

            return "Invalid transaction data."

    # -----------------------------------------------------
    # GET TRANSACTIONS
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            type,
            amount,
            description,
            date
        FROM transactions
        WHERE user_email=?
        ORDER BY date DESC
    """, (user_email,))

    transactions = cursor.fetchall()

    # -----------------------------------------------------
    # CALCULATE TOTALS
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            COALESCE(
                SUM(
                    CASE
                        WHEN type='Income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS total_income,

            COALESCE(
                SUM(
                    CASE
                        WHEN type='Expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS total_expenses

        FROM transactions
        WHERE user_email=?
    """, (user_email,))

    totals = cursor.fetchone()

    total_income = totals["total_income"]
    total_expenses = totals["total_expenses"]

    balance = total_income - total_expenses

    connection.close()

    return render_template(
        "dashboard.html",
        transactions=transactions,
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance
    )


# =========================================================
# M-PESA DEPOSIT PAGE
# =========================================================

@app.route("/deposit", methods=["GET", "POST"])
def deposit():

    if "user_email" not in session:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("deposit.html")

    phone = request.form.get(
        "phone",
        ""
    ).strip()

    amount_text = request.form.get(
        "amount",
        ""
    ).strip()

    if not phone:

        return render_template(
            "deposit.html",
            error="Please enter your M-Pesa phone number."
        )

    try:

        amount = float(amount_text)

    except ValueError:

        return render_template(
            "deposit.html",
            error="Invalid amount."
        )

    if amount <= 0:

        return render_template(
            "deposit.html",
            error="Amount must be greater than zero."
        )

    try:

        result = stk_push(
            phone_number=phone,
            amount=amount,
            account_reference="MoneyTracker",
            transaction_description="Money Tracker Deposit"
        )

        print("=" * 60)
        print("M-PESA STK RESPONSE")
        print(result)
        print("=" * 60)

        if str(
            result.get("ResponseCode", "")
        ) == "0":

            return render_template(
                "deposit.html",
                message=(
                    "STK Push sent successfully. "
                    "Check your phone and enter your M-Pesa PIN."
                ),
                result=result
            )

        return render_template(
            "deposit.html",
            error=result.get(
                "ResponseDescription",
                "M-Pesa request failed."
            ),
            result=result
        )

    except Exception as error:

        print("M-PESA ERROR:", error)

        return render_template(
            "deposit.html",
            error=str(error)
        )


# =========================================================
# M-PESA CALLBACK
# =========================================================

@app.route(
    "/mpesa/callback",
    methods=["POST"]
)
def mpesa_callback():

    try:

        data = request.get_json(
            silent=True
        )

        print("=" * 60)
        print("M-PESA CALLBACK")
        print(data)
        print("=" * 60)

        if not data:

            return jsonify({
                "ResultCode": 1,
                "ResultDesc": "No data received"
            })

        body = data.get(
            "Body",
            {}
        )

        callback = body.get(
            "stkCallback",
            {}
        )

        result_code = callback.get(
            "ResultCode"
        )

        result_description = callback.get(
            "ResultDesc"
        )

        print(
            "Result Code:",
            result_code
        )

        print(
            "Result Description:",
            result_description
        )

        # -------------------------------------------------
        # SUCCESSFUL PAYMENT
        # -------------------------------------------------

        if result_code == 0:

            print(
                "M-PESA PAYMENT SUCCESSFUL"
            )

            metadata = callback.get(
                "CallbackMetadata",
                {}
            )

            items = metadata.get(
                "Item",
                []
            )

            amount_paid = None
            mpesa_receipt = None
            phone_number = None

            for item in items:

                name = item.get("Name")
                value = item.get("Value")

                if name == "Amount":
                    amount_paid = value

                elif name == "MpesaReceiptNumber":
                    mpesa_receipt = value

                elif name == "PhoneNumber":
                    phone_number = value

            print(
                "Amount:",
                amount_paid
            )

            print(
                "Receipt:",
                mpesa_receipt
            )

            print(
                "Phone:",
                phone_number
            )

            # -------------------------------------------------
            # IMPORTANT
            # Deposit should eventually be recorded here.
            # -------------------------------------------------

        else:

            print(
                "M-PESA PAYMENT FAILED"
            )

        return jsonify({
            "ResultCode": 0,
            "ResultDesc": "Accepted"
        })

    except Exception as error:

        print(
            "CALLBACK ERROR:",
            error
        )

        return jsonify({
            "ResultCode": 1,
            "ResultDesc": "Callback error"
        })


# =========================================================
# EDIT TRANSACTION
# =========================================================

@app.route(
    "/edit/<int:id>",
    methods=["GET", "POST"]
)
def edit(id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]

    connection = get_db()
    cursor = connection.cursor()

    if request.method == "POST":

        try:

            transaction_type = request.form["type"]
            amount = float(request.form["amount"])
            description = request.form["description"].strip()

            if amount <= 0:
                connection.close()
                return "Amount must be greater than zero."

            if transaction_type not in [
                "Income",
                "Expense"
            ]:
                connection.close()
                return "Invalid transaction type."

            cursor.execute("""
                UPDATE transactions
                SET
                    type=?,
                    amount=?,
                    description=?
                WHERE
                    id=?
                    AND user_email=?
            """, (
                transaction_type,
                amount,
                description,
                id,
                user_email
            ))

            connection.commit()
            connection.close()

            return redirect(
                url_for("dashboard")
            )

        except (ValueError, KeyError):

            connection.close()

            return "Invalid transaction data."

    cursor.execute("""
        SELECT
            id,
            type,
            amount,
            description,
            date
        FROM transactions
        WHERE
            id=?
            AND user_email=?
    """, (
        id,
        user_email
    ))

    transaction = cursor.fetchone()

    connection.close()

    if not transaction:
        return "Transaction not found."

    return render_template(
        "edit.html",
        transaction=transaction
    )


# =========================================================
# DELETE TRANSACTION
# =========================================================

@app.route("/delete/<int:id>")
def delete(id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    user_email = session["user_email"]

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        DELETE FROM transactions
        WHERE
            id=?
            AND user_email=?
    """, (
        id,
        user_email
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("dashboard")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
def admin():

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    # -----------------------------------------------------
    # USERS
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            is_admin,
            is_active
        FROM users
        ORDER BY id DESC
    """)

    users = cursor.fetchall()

    # -----------------------------------------------------
    # ALL TRANSACTIONS
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            id,
            user_email,
            type,
            amount,
            description,
            date
        FROM transactions
        ORDER BY date DESC
    """)

    all_transactions = cursor.fetchall()

    # -----------------------------------------------------
    # TOTAL USERS
    # -----------------------------------------------------

    cursor.execute("""
        SELECT COUNT(*) AS total_users
        FROM users
    """)

    total_users = cursor.fetchone()["total_users"]

    # -----------------------------------------------------
    # TOTAL INCOME
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_income
        FROM transactions
        WHERE type='Income'
    """)

    total_income = cursor.fetchone()["total_income"]

    # -----------------------------------------------------
    # TOTAL EXPENSES
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            COALESCE(SUM(amount), 0) AS total_expenses
        FROM transactions
        WHERE type='Expense'
    """)

    total_expenses = cursor.fetchone()["total_expenses"]

    platform_balance = (
        total_income -
        total_expenses
    )

    # -----------------------------------------------------
    # COMMISSION BALANCE
    # -----------------------------------------------------

    cursor.execute("""
        SELECT
            commission_balance
        FROM platform_settings
        WHERE id=1
    """)

    commission_result = cursor.fetchone()

    commission_balance = (
        commission_result["commission_balance"]
        if commission_result
        else 0
    )

    connection.close()

    return render_template(
        "admin.html",
        users=users,
        all_transactions=all_transactions,
        total_users=total_users,
        total_income=total_income,
        total_expenses=total_expenses,
        platform_balance=platform_balance,
        commission_balance=commission_balance
    )


# =========================================================
# ADMIN - VIEW USER
# =========================================================

@app.route(
    "/admin/user/<int:user_id>"
)
def admin_user(user_id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            email,
            is_admin,
            is_active
        FROM users
        WHERE id=?
    """, (user_id,))

    user = cursor.fetchone()

    if not user:

        connection.close()

        return "User not found."

    cursor.execute("""
        SELECT
            id,
            type,
            amount,
            description,
            date
        FROM transactions
        WHERE user_email=?
        ORDER BY date DESC
    """, (
        user["email"],
    ))

    transactions = cursor.fetchall()

    cursor.execute("""
        SELECT

            COALESCE(
                SUM(
                    CASE
                        WHEN type='Income'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS total_income,

            COALESCE(
                SUM(
                    CASE
                        WHEN type='Expense'
                        THEN amount
                        ELSE 0
                    END
                ),
                0
            ) AS total_expenses

        FROM transactions
        WHERE user_email=?
    """, (
        user["email"],
    ))

    totals = cursor.fetchone()

    total_income = totals["total_income"]
    total_expenses = totals["total_expenses"]

    balance = (
        total_income -
        total_expenses
    )

    connection.close()

    return render_template(
        "admin_user.html",
        user=user,
        transactions=transactions,
        total_income=total_income,
        total_expenses=total_expenses,
        balance=balance
    )


# =========================================================
# ADMIN - ACTIVATE USER
# =========================================================

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

    cursor.execute("""
        UPDATE users
        SET is_active=1
        WHERE id=?
    """, (
        user_id,
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN - DEACTIVATE USER
# =========================================================

@app.route(
    "/admin/user/<int:user_id>/deactivate",
    methods=["POST"]
)
def deactivate_user(user_id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    # Prevent admin from deactivating themselves
    if session.get("user_id") == user_id:

        return (
            "You cannot deactivate "
            "your own admin account."
        )

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE users
        SET is_active=0
        WHERE id=?
    """, (
        user_id,
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN - PAYMENT REQUESTS
# =========================================================

@app.route("/admin/requests")
def admin_requests():

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            user_email,
            request_type,
            phone_number,
            amount,
            commission_rate,
            commission_amount,
            net_amount,
            status,
            date
        FROM payment_requests
        ORDER BY date DESC
    """)

    requests = cursor.fetchall()

    connection.close()

    return render_template(
        "admin_requests.html",
        requests=requests
    )


# =========================================================
# ADMIN - APPROVE PAYMENT REQUEST
# =========================================================

@app.route(
    "/admin/request/<int:request_id>/approve",
    methods=["POST"]
)
def approve_request(request_id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    try:

        cursor.execute("""
            SELECT
                id,
                user_email,
                request_type,
                phone_number,
                amount,
                commission_rate,
                commission_amount,
                net_amount,
                status
            FROM payment_requests
            WHERE id=?
        """, (
            request_id,
        ))

        payment = cursor.fetchone()

        if not payment:
            return "Payment request not found."

        if payment["status"] != "Pending":
            return (
                "This request has "
                "already been processed."
            )

        # -------------------------------------------------
        # DEPOSIT
        # -------------------------------------------------

        if payment["request_type"] == "Deposit":

            cursor.execute("""
                INSERT INTO transactions
                (
                    user_email,
                    type,
                    amount,
                    description
                )
                VALUES (?, 'Income', ?, ?)
            """, (
                payment["user_email"],
                payment["amount"],
                "Approved deposit"
            ))

        # -------------------------------------------------
        # WITHDRAWAL
        # -------------------------------------------------

        elif payment["request_type"] == "Withdrawal":

            cursor.execute("""
                SELECT

                    COALESCE(
                        SUM(
                            CASE
                                WHEN type='Income'
                                THEN amount
                                ELSE 0
                            END
                        ),
                        0
                    ) AS total_income,

                    COALESCE(
                        SUM(
                            CASE
                                WHEN type='Expense'
                                THEN amount
                                ELSE 0
                            END
                        ),
                        0
                    ) AS total_expenses

                FROM transactions
                WHERE user_email=?
            """, (
                payment["user_email"],
            ))

            totals = cursor.fetchone()

            balance = (
                totals["total_income"] -
                totals["total_expenses"]
            )

            if payment["amount"] > balance:
                return "Insufficient user balance."

            # Deduct withdrawal
            cursor.execute("""
                INSERT INTO transactions
                (
                    user_email,
                    type,
                    amount,
                    description
                )
                VALUES (?, 'Expense', ?, ?)
            """, (
                payment["user_email"],
                payment["amount"],
                "Approved withdrawal"
            ))

            # Add commission
            cursor.execute("""
                UPDATE platform_settings
                SET commission_balance =
                    commission_balance + ?
                WHERE id=1
            """, (
                payment["commission_amount"],
            ))

        else:

            return "Invalid request type."

        # Mark request approved
        cursor.execute("""
            UPDATE payment_requests
            SET status='Approved'
            WHERE id=?
        """, (
            request_id,
        ))

        connection.commit()

    except Exception as error:

        connection.rollback()

        return (
            f"Error approving request: "
            f"{error}"
        )

    finally:

        connection.close()

    return redirect(
        url_for("admin_requests")
    )


# =========================================================
# ADMIN - REJECT PAYMENT REQUEST
# =========================================================

@app.route(
    "/admin/request/<int:request_id>/reject",
    methods=["POST"]
)
def reject_request(request_id):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            status
        FROM payment_requests
        WHERE id=?
    """, (
        request_id,
    ))

    payment = cursor.fetchone()

    if not payment:

        connection.close()

        return "Payment request not found."

    if payment["status"] != "Pending":

        connection.close()

        return (
            "This request has "
            "already been processed."
        )

    cursor.execute("""
        UPDATE payment_requests
        SET status='Rejected'
        WHERE id=?
    """, (
        request_id,
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("admin_requests")
    )


# =========================================================
# COMMISSION WALLET
# =========================================================

@app.route("/admin/commission")
def admin_commission():

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    # Current commission balance
    cursor.execute("""
        SELECT
            commission_balance
        FROM platform_settings
        WHERE id=1
    """)

    result = cursor.fetchone()

    commission_balance = (
        result["commission_balance"]
        if result
        else 0
    )

    # Withdrawal history
    cursor.execute("""
        SELECT
            id,
            phone_number,
            amount,
            status,
            date
        FROM commission_withdrawals
        ORDER BY date DESC
    """)

    withdrawals = cursor.fetchall()

    # Total approved withdrawals
    cursor.execute("""
        SELECT
            COALESCE(SUM(amount), 0)
            AS total_withdrawn
        FROM commission_withdrawals
        WHERE status='Approved'
    """)

    total_withdrawn = cursor.fetchone()[
        "total_withdrawn"
    ]

    connection.close()

    return render_template(
        "commission.html",
        commission_balance=commission_balance,
        withdrawals=withdrawals,
        total_withdrawn=total_withdrawn
    )


# =========================================================
# REQUEST COMMISSION WITHDRAWAL
# =========================================================

@app.route(
    "/admin/commission/withdraw",
    methods=["POST"]
)
def commission_withdraw():

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    phone_number = request.form[
        "phone_number"
    ].strip()

    try:

        amount = float(
            request.form["amount"]
        )

    except ValueError:

        return "Invalid withdrawal amount."

    if amount <= 0:
        return "Amount must be greater than zero."

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            commission_balance
        FROM platform_settings
        WHERE id=1
    """)

    result = cursor.fetchone()

    if not result:

        connection.close()

        return "Commission wallet not found."

    commission_balance = (
        result["commission_balance"]
    )

    if amount > commission_balance:

        connection.close()

        return "Insufficient commission balance."

    cursor.execute("""
        INSERT INTO commission_withdrawals
        (
            phone_number,
            amount,
            status
        )
        VALUES (?, ?, 'Pending')
    """, (
        phone_number,
        amount
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("admin_commission")
    )


# =========================================================
# APPROVE COMMISSION WITHDRAWAL
# =========================================================

@app.route(
    "/admin/commission/<int:withdrawal_id>/approve",
    methods=["POST"]
)
def approve_commission_withdrawal(
    withdrawal_id
):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    try:

        cursor.execute("""
            SELECT
                amount,
                status
            FROM commission_withdrawals
            WHERE id=?
        """, (
            withdrawal_id,
        ))

        withdrawal = cursor.fetchone()

        if not withdrawal:
            return (
                "Commission withdrawal "
                "not found."
            )

        if withdrawal["status"] != "Pending":
            return (
                "This withdrawal has "
                "already been processed."
            )

        cursor.execute("""
            SELECT
                commission_balance
            FROM platform_settings
            WHERE id=1
        """)

        result = cursor.fetchone()

        if not result:
            return "Commission wallet not found."

        balance = result[
            "commission_balance"
        ]

        if withdrawal["amount"] > balance:
            return "Insufficient commission balance."

        # Deduct commission
        cursor.execute("""
            UPDATE platform_settings
            SET commission_balance =
                commission_balance - ?
            WHERE id=1
        """, (
            withdrawal["amount"],
        ))

        # Mark approved
        cursor.execute("""
            UPDATE commission_withdrawals
            SET status='Approved'
            WHERE id=?
        """, (
            withdrawal_id,
        ))

        connection.commit()

    except Exception as error:

        connection.rollback()

        return f"Error: {error}"

    finally:

        connection.close()

    return redirect(
        url_for("admin_commission")
    )


# =========================================================
# REJECT COMMISSION WITHDRAWAL
# =========================================================

@app.route(
    "/admin/commission/<int:withdrawal_id>/reject",
    methods=["POST"]
)
def reject_commission_withdrawal(
    withdrawal_id
):

    if "user_email" not in session:
        return redirect(url_for("login"))

    if session.get("is_admin") != 1:
        return "Access denied. Admins only."

    connection = get_db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            status
        FROM commission_withdrawals
        WHERE id=?
    """, (
        withdrawal_id,
    ))

    withdrawal = cursor.fetchone()

    if not withdrawal:

        connection.close()

        return (
            "Commission withdrawal "
            "not found."
        )

    if withdrawal["status"] != "Pending":

        connection.close()

        return (
            "This withdrawal has "
            "already been processed."
        )

    cursor.execute("""
        UPDATE commission_withdrawals
        SET status='Rejected'
        WHERE id=?
    """, (
        withdrawal_id,
    ))

    connection.commit()
    connection.close()

    return redirect(
        url_for("admin_commission")
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )