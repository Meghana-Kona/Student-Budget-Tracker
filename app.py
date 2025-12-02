# app.py — Clean, professional, and fully integrated with your database.py schema
from flask import Flask, render_template, request, redirect, session, flash, url_for
from database import get_db, init_db
from datetime import datetime, timedelta
import os, re, uuid
import easyocr
from flask_bcrypt import Bcrypt
from werkzeug.utils import secure_filename

# -------------------------
# Configuration
# -------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "supersecret123")
bcrypt = Bcrypt(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXT = {"png", "jpg", "jpeg", "bmp", "tiff"}

# -------------------------
# Helpers
# -------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT

def parse_items_from_text(text):
    items = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    line_re = re.compile(r'(.+?)[\:\-\—\s]{1,}\s*([0-9]{1,3}(?:[,\s][0-9]{3})*(?:\.[0-9]{2})?)')
    for ln in lines:
        m = line_re.search(ln)
        if m:
            try:
                items.append({"name": m.group(1).strip(), "amount": float(m.group(2).replace(',', ''))})
            except:
                pass
    return items

def guess_category(text):
    text = (text or "").lower()
    mapping = {
        "Food": ["pizza", "burger", "chips", "juice", "milk", "meal", "dosa", "idli", "kfc"],
        "Books": ["book", "pen", "notebook"],
        "Transport": ["bus", "uber", "ola", "fuel", "taxi"],
        "Shopping": ["cloth", "amazon", "flipkart", "shopping"],
        "Medical": ["tablet", "medicine", "clinic", "doctor"],
        "Personal Care": ["hair", "salon", "shampoo"],
        "Electronics": ["charger", "earphone", "laptop", "mobile"],
    }
    for cat, keys in mapping.items():
        if any(k in text for k in keys):
            return cat
    return "Other"

def apply_recurring(user_id):
    conn = get_db()
    cursor = conn.cursor()

    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT * FROM recurring_expenses WHERE user_id=?", (user_id,))
    recs = cursor.fetchall()

    for r in recs:

        # Skip paused recurring items
        if r["status"] == "paused":
            continue

        # Corrected here (NO `.get()`)
        if r["next_date"] == today:

            cursor.execute("""
                INSERT INTO expenses (user_id, category, amount, description, date)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, r["category"], r["amount"], r["title"] + " (Recurring)", today))

            # Compute next deduction date
            if r["frequency"] == "daily":
                next_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
            elif r["frequency"] == "weekly":
                next_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
            else:  # monthly
                next_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

            cursor.execute("UPDATE recurring_expenses SET next_date=? WHERE id=?", (next_date, r["id"]))

    conn.commit()


# -------------------------
# Public Routes: Home / Auth
# -------------------------
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not (name and email and password):
            flash("All fields required.", "error")
            return redirect("/signup")
        hashed = bcrypt.generate_password_hash(password).decode("utf-8")
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        if cursor.fetchone():
            flash("Email already exists!", "error"); return redirect("/signup")
        cursor.execute("INSERT INTO users (name,email,password) VALUES (?, ?, ?)", (name, email, hashed))
        conn.commit()
        flash("Account created! Please login.", "success"); return redirect("/login")
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        conn = get_db(); cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cursor.fetchone()
        if user and bcrypt.check_password_hash(user["password"], password):
            session["user_id"]=user["id"]; session["username"]=user["name"]
            flash("Logged in successfully!", "success"); return redirect("/home2")
        flash("Invalid email or password!", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect("/")

# -------------------------
# Dashboard home2
# -------------------------
@app.route("/home2", methods=["GET","POST"])
def home2():
    if "user_id" not in session:
        return redirect("/login")
    user_id = session["user_id"]

    # apply recurring deductions first
    apply_recurring(user_id)

    conn = get_db(); cursor = conn.cursor()

    # Add allowance from dashboard form
    if request.method == "POST" and "allowance_amount" in request.form:
        try:
            amt = float(request.form.get("allowance_amount",0))
        except:
            flash("Invalid amount", "danger"); return redirect("/home2")
        if amt > 0:
            date = datetime.now().strftime("%Y-%m-%d")
            cursor.execute("INSERT INTO allowances (user_id, amount, date) VALUES (?, ?, ?)", (user_id, amt, date))
            conn.commit()
            flash("Allowance added!", "success")
        return redirect("/home2")

    # totals
    # Total allowances EVER added
    # TOTAL ALLOWANCES EVER ADDED
    cursor.execute("SELECT SUM(amount) AS t FROM allowances WHERE user_id=?", (user_id,))
    total_allow = cursor.fetchone()["t"] or 0

# TOTAL EXPENSES (manual + recurring)
    cursor.execute("SELECT SUM(amount) AS t FROM expenses WHERE user_id=?", (user_id,))
    total_exp = cursor.fetchone()["t"] or 0

# TOTAL GOAL SAVINGS
    cursor.execute("SELECT SUM(saved_amount) AS t FROM goals WHERE user_id=?", (user_id,))
    total_saved = cursor.fetchone()["t"] or 0

# FINAL BALANCE
    balance = total_allow - total_exp - total_saved


    # previews
    cursor.execute("SELECT * FROM recurring_expenses WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
    recurring_preview = cursor.fetchall()
    cursor.execute("SELECT * FROM category_limits WHERE user_id=?", (user_id,))
    limits = cursor.fetchall()
    cursor.execute("SELECT * FROM goals WHERE user_id=?", (user_id,))
    goals = cursor.fetchall()

    return render_template("home2.html",
                       total_allow=round(total_allow,2),
                       total_expenses=round(total_exp,2),
                       total_saved_in_goals=round(total_saved,2),
                       balance=round(balance,2),
                       recurring_preview=recurring_preview,
                       limits=limits,
                       goals=goals)



# -------------------------
# Log expense
# -------------------------
@app.route("/log_expense", methods=["GET","POST"])
def log_expense():
    if "user_id" not in session:
        return redirect("/login")
    user_id = session["user_id"]
    apply_recurring(user_id)
    conn = get_db(); cursor = conn.cursor()

    if request.method=="POST" and "expense_amount" in request.form:
        try:
            amount = float(request.form.get("expense_amount",0))
        except:
            flash("Invalid amount.", "error"); return redirect("/log_expense")
        # compute displayed allowance
        cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM allowances WHERE user_id=?", (user_id,))
        total_allow_raw = cursor.fetchone()["t"] or 0.0
        cursor.execute("SELECT COALESCE(SUM(saved_amount),0) as t FROM goals WHERE user_id=?", (user_id,))
        total_saved = cursor.fetchone()["t"] or 0.0
        displayed_allow = total_allow_raw - total_saved
        cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM expenses WHERE user_id=?", (user_id,))
        total_exp = cursor.fetchone()["t"] or 0.0
        remaining_balance = displayed_allow - total_exp
        if amount > remaining_balance:
            flash("Insufficient balance.", "error"); return redirect("/log_expense")
        # insert expense
        cursor.execute("""
            INSERT INTO expenses (user_id, category, amount, description, date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, request.form.get("category","Other"), amount, request.form.get("description",""), datetime.now().strftime("%Y-%m-%d")))
        conn.commit()
        flash("Expense added!", "success"); return redirect("/log_expense")

    # fetch data for page
    # Allowances
    cursor.execute("SELECT SUM(amount) AS t FROM allowances WHERE user_id=?", (user_id,))
    total_allowance = cursor.fetchone()["t"] or 0

# Expenses
    cursor.execute("SELECT SUM(amount) AS t FROM expenses WHERE user_id=?", (user_id,))
    total_expenses = cursor.fetchone()["t"] or 0

# Goal Savings
    cursor.execute("SELECT SUM(saved_amount) AS t FROM goals WHERE user_id=?", (user_id,))
    total_goal_savings = cursor.fetchone()["t"] or 0

# Correct Balance
    balance = total_allowance - total_expenses - total_goal_savings

    spent_percentage = (total_expenses/total_allowance*100) if total_allowance else 0
    safe_limit = balance/30 if balance>0 else 0
    cursor.execute("SELECT id, category, amount, description, date FROM expenses WHERE user_id=? ORDER BY id DESC", (user_id,))
    expenses = cursor.fetchall()
    cursor.execute("SELECT * FROM recurring_expenses WHERE user_id=?", (user_id,))
    recurring = cursor.fetchall()

    invoice_items = session.get("invoice_items")
    show_invoice = request.args.get("show_invoice")
    return render_template("log_expense.html",
                           total_allowance=round(total_allowance,2),
                           balance=round(balance,2),
                           spent_percentage=round(spent_percentage,2),
                           safe_limit=round(safe_limit,2),
                           expenses=expenses,
                           recurring=recurring,
                           invoice_items=invoice_items,
                           show_invoice=show_invoice)

# -------------------------
# Category Limits
# -------------------------
@app.route("/limits", methods=["GET","POST"])
def limits():
    if "user_id" not in session:
        return redirect("/login")
    user_id = session["user_id"]; conn = get_db(); cursor = conn.cursor()
    edit_id = request.args.get("edit"); edit_limit=None
    if edit_id:
        cursor.execute("SELECT * FROM category_limits WHERE id=? AND user_id=?", (edit_id,user_id))
        edit_limit = cursor.fetchone()
    if request.method=="POST":
        category = request.form.get("category","").strip()
        amount = float(request.form.get("amount",0))
        if request.form.get("edit_id"):
            cursor.execute("UPDATE category_limits SET limit_amount=? WHERE id=? AND user_id=?", (amount, request.form.get("edit_id"), user_id))
        else:
            cursor.execute("INSERT INTO category_limits (user_id, category, limit_amount) VALUES (?, ?, ?)", (user_id, category, amount))
        conn.commit(); return redirect("/limits")
    cursor.execute("SELECT * FROM category_limits WHERE user_id=?", (user_id,))
    limits = cursor.fetchall()
    return render_template("limits.html", limits=limits, edit_limit=edit_limit)

# -------------------------
# Goals: add / edit / delete / edit-mode
# -------------------------
@app.route("/goals", methods=["GET","POST"])
def goals_page():
    if "user_id" not in session:
        return redirect("/login")
    user_id = session["user_id"]; conn = get_db(); cursor = conn.cursor()

    # POST -> update or add
    if request.method=="POST":
        if request.form.get("goal_id"):
            # update existing (title, target, due)
            goal_id = request.form.get("goal_id")
            title = request.form.get("title","").strip()
            target = float(request.form.get("target_amount",0))
            due = request.form.get("due_date") or None
            cursor.execute("UPDATE goals SET title=?, target_amount=?, due_date=? WHERE id=? AND user_id=?",
                           (title, target, due, goal_id, user_id))
            conn.commit()
            flash("Goal updated.", "success")
            return redirect("/goals")
        else:
            # add new with required initial_save
            title = request.form.get("title","").strip()
            target = float(request.form.get("target_amount",0))
            initial_save = float(request.form.get("initial_save",0))
            due = request.form.get("due_date") or None
            if initial_save < 0 or initial_save > target:
                flash("Invalid initial save amount.", "danger"); return redirect("/goals")
            cursor.execute("""INSERT INTO goals (user_id, title, target_amount, saved_amount, due_date)
                              VALUES (?, ?, ?, ?, ?)""", (user_id, title, target, initial_save, due))
            conn.commit()
            flash("Goal added.", "success"); return redirect("/goals")

    # DELETE via query param
    delete_id = request.args.get("delete")
    if delete_id:
        # Deleting a goal refunds saved amount implicitly (since saved_amount is removed from goals sum)
        cursor.execute("DELETE FROM goals WHERE id=? AND user_id=?", (delete_id, user_id))
        conn.commit()
        flash("Goal deleted and saved amount refunded to available balance.", "success")
        return redirect("/home2")

    # EDIT mode: show only that goal and edit form
    edit_id = request.args.get("edit")
    if edit_id:
        cursor.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (edit_id, user_id))
        edit_goal = cursor.fetchone()
        return render_template("goals.html", goals=[edit_goal], edit_goal=edit_goal)

    # normal list
    cursor.execute("SELECT * FROM goals WHERE user_id=?", (user_id,))
    goals = cursor.fetchall()
    return render_template("goals.html", goals=goals, edit_goal=None)

# -------------------------
# Add more saved amount to an existing goal
# -------------------------
@app.route("/add_to_goal/<int:goal_id>", methods=["POST"])
def add_to_goal(goal_id):
    if "user_id" not in session:
        return redirect("/login")
    user_id = session["user_id"]; conn = get_db(); cursor = conn.cursor()

    try:
        amount = float(request.form.get("amount",0))
    except:
        flash("Invalid amount", "danger"); return redirect(f"/goals?edit={goal_id}")
    if amount <= 0:
        flash("Enter an amount > 0", "danger"); return redirect(f"/goals?edit={goal_id}")

    # fetch goal
    cursor.execute("SELECT * FROM goals WHERE id=? AND user_id=?", (goal_id, user_id))
    goal = cursor.fetchone()
    if not goal:
        flash("Goal not found", "danger"); return redirect("/goals")

    saved = goal["saved_amount"] or 0.0
    target = goal["target_amount"] or 0.0
    allowed_to_add = target - saved
    if amount > allowed_to_add:
        flash(f"You can only add up to ₹{allowed_to_add}", "danger"); return redirect(f"/goals?edit={goal_id}")

    # compute displayed available balance
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM allowances WHERE user_id=?", (user_id,))
    total_allow_raw = cursor.fetchone()["t"] or 0.0
    cursor.execute("SELECT COALESCE(SUM(saved_amount),0) as t FROM goals WHERE user_id=?", (user_id,))
    total_saved = cursor.fetchone()["t"] or 0.0
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM expenses WHERE user_id=?", (user_id,))
    total_exp = cursor.fetchone()["t"] or 0.0
    displayed_allow = total_allow_raw - total_saved
    remaining_balance = displayed_allow - total_exp

    if amount > remaining_balance:
        flash("Not enough available balance to add this amount!", "danger"); return redirect(f"/goals?edit={goal_id}")

    new_saved = saved + amount
    cursor.execute("UPDATE goals SET saved_amount=? WHERE id=? AND user_id=?", (new_saved, goal_id, user_id))
    conn.commit()
    flash("Amount added to goal successfully!", "success")
    return redirect(f"/goals?edit={goal_id}")

# -------------------------
# Delete goal (dedicated route)
# -------------------------
@app.route("/delete_goal/<int:id>")
def delete_goal(id):
    if "user_id" not in session:
        return redirect("/login")
    user_id = session["user_id"]; conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM goals WHERE id=? AND user_id=?", (id, user_id))
    conn.commit(); flash("Goal deleted!", "success"); return redirect("/home2")

# -------------------------
# Insights
# -------------------------
@app.route("/insights")
def insights():
    if "user_id" not in session:
        return redirect("/login")
    user_id = session["user_id"]; conn = get_db(); cursor = conn.cursor()

    # totals & displayed allowance
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM allowances WHERE user_id=?", (user_id,))
    total_allow_raw = cursor.fetchone()["t"] or 0.0
    cursor.execute("SELECT COALESCE(SUM(saved_amount),0) as t FROM goals WHERE user_id=?", (user_id,))
    total_saved = cursor.fetchone()["t"] or 0.0
    cursor.execute("SELECT COALESCE(SUM(amount),0) as t FROM expenses WHERE user_id=?", (user_id,))
    total_exp = cursor.fetchone()["t"] or 0.0
    displayed_allow = total_allow_raw - total_saved
    balance = displayed_allow - total_exp

    # category expenses
    cursor.execute("SELECT category, COALESCE(SUM(amount),0) as t FROM expenses WHERE user_id=? GROUP BY category", (user_id,))
    cat_rows = cursor.fetchall()
    categories = [r["category"] for r in cat_rows]
    totals = [r["t"] for r in cat_rows]

    # include a single 'Savings' slice if there are savings
    if total_saved > 0:
        categories.append("Savings")
        totals.append(total_saved)

    # daily totals for last 7 days
    cursor.execute("SELECT date(date) as d, COALESCE(SUM(amount),0) as t FROM expenses WHERE user_id=? AND date >= date('now','-6 days') GROUP BY d ORDER BY d", (user_id,))
    daily = cursor.fetchall()
    from datetime import datetime, timedelta
    days = []
    daily_totals_map = {r["d"]: r["t"] for r in daily}
    daily_totals = []
    for i in range(6, -1, -1):
        d = (datetime.now() - timedelta(days=i)).date().isoformat()
        days.append(d)
        daily_totals.append(daily_totals_map.get(d, 0))

    return render_template("insights.html",
                           categories=categories,
                           totals=totals,
                           days=days,
                           daily_totals=daily_totals,
                           total_allow=round(displayed_allow,2),
                           total_allow_raw=round(total_allow_raw,2),
                           total_saved_in_goals=round(total_saved,2),
                           total_exp=round(total_exp,2),
                           balance=round(balance,2))

# -------------------------
# OCR upload / invoice flow
# -------------------------
@app.route("/upload_invoice", methods=["POST"])
def upload_invoice():
    if "user_id" not in session:
        flash("Please login first.", "error"); return redirect("/login")
    if "invoice" not in request.files: flash("No file uploaded.", "error"); return redirect("/log_expense")
    file = request.files["invoice"]
    if file.filename == "" or not allowed_file(file.filename):
        flash("Invalid file.", "error"); return redirect("/log_expense")
    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    saved_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
    file.save(saved_path)
    try:
        reader = easyocr.Reader(['en'], gpu=False)
        result = reader.readtext(saved_path, detail=0)
        text = "\n".join(result)
    except:
        flash("OCR failed. Try a clearer image.", "error"); return redirect("/log_expense")
    items = parse_items_from_text(text)
    added_items = []
    for it in items:
        cat = guess_category(it['name']) or "Shopping"
        added_items.append({"name": it['name'], "amount": it['amount'], "category": cat})
    session["invoice_items"] = added_items
    flash("Bill scanned! Review and add items below.", "info")
    return redirect("/log_expense?show_invoice=1")

@app.route("/add_invoice_items", methods=["POST"])
def add_invoice_items():
    if "user_id" not in session: return redirect("/login")
    if "invoice_items" not in session: flash("No invoice data found.", "error"); return redirect("/log_expense")
    items = session["invoice_items"]; final_items=[]
    for i in range(1, len(items)+1):
        final_items.append({
            "name": request.form.get(f"name{i}"),
            "amount": float(request.form.get(f"amount{i}")),
            "category": request.form.get(f"category{i}")
        })
    conn = get_db(); cursor = conn.cursor(); today = datetime.now().strftime("%Y-%m-%d")
    for it in final_items:
        cursor.execute("INSERT INTO expenses (user_id, category, amount, description, date) VALUES (?, ?, ?, ?, ?)",
                       (session["user_id"], it["category"], it["amount"], it["name"], today))
    conn.commit(); session.pop("invoice_items", None)
    flash("Invoice items added successfully!", "success"); return redirect("/log_expense")

@app.route("/cancel_invoice", methods=["POST"])
def cancel_invoice():
    session.pop("invoice_items", None); flash("Bill cancelled.", "info"); return redirect("/log_expense")

@app.route("/review_invoice")
def review_invoice():
    if "user_id" not in session: return redirect("/login")
    if "invoice_items" not in session:
        flash("No invoice data found. Please upload a bill again.", "error"); return redirect("/log_expense")
    return render_template("review_invoice.html")

# -------------------------
# Recurring Controls (Pause / Resume / Add)
# -------------------------

@app.route("/pause_recurring/<int:id>")
def pause_recurring(id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE recurring_expenses
        SET status='paused'
        WHERE id=? AND user_id=?
    """, (id, session["user_id"]))

    conn.commit()
    flash("Recurring paused.", "info")
    return redirect("/home2")


@app.route("/resume_recurring/<int:id>")
def resume_recurring(id):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE recurring_expenses
        SET status='active'
        WHERE id=? AND user_id=?
    """, (id, session["user_id"]))

    conn.commit()
    flash("Recurring resumed.", "success")
    return redirect("/home2")


# ---------------------------------------------------------
# RECURRING PAGE (Add & View)
# ---------------------------------------------------------
@app.route("/recurring", methods=["GET", "POST"])
def recurring_page():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    # ---------------- Add New Recurring Expense ----------------
    if request.method == "POST":
        title = request.form["title"]
        amount = float(request.form["amount"])
        category = request.form["category"]
        frequency = request.form["frequency"]

        # First next_date should be TODAY so it deducts from tomorrow
        next_date = datetime.now().strftime("%Y-%m-%d")

        cursor.execute("""
            INSERT INTO recurring_expenses 
            (user_id, title, amount, category, frequency, next_date, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
        """, (user_id, title, amount, category, frequency, next_date))

        conn.commit()
        flash("Recurring expense added!", "success")
        return redirect("/home2")

    # ---------------- Show List of Recurring ----------------
    cursor.execute("SELECT * FROM recurring_expenses WHERE user_id=?", (user_id,))
    all_recurring = cursor.fetchall()

    return render_template("recurring.html", recurring=all_recurring)


# -------------------------
# Delete limit
# -------------------------
@app.route("/delete_limit/<int:id>")
def delete_limit(id):
    if "user_id" not in session: return redirect("/login")
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM category_limits WHERE id=? AND user_id=?", (id, session["user_id"]))
    conn.commit(); flash("Category limit removed!", "success"); return redirect("/home2")

# -------------------------
# Clear / delete expense
# -------------------------
@app.route("/clear_expenses", methods=["POST"])
def clear_expenses():
    if "user_id" not in session: return redirect("/login")
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE user_id=?", (session["user_id"],))
    conn.commit(); flash("All expenses cleared.", "info"); return redirect("/log_expense")

@app.route("/delete_expense/<int:id>", methods=["POST"])
def delete_expense(id):
    if "user_id" not in session: return redirect("/login")
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (id, session["user_id"]))
    conn.commit(); flash("Expense deleted.", "info"); return redirect("/log_expense")

# -------------------------
# Dashboard summary route (optional / alternate)
# -------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    conn = get_db()
    cursor = conn.cursor()

    # 🔥 Apply today's recurring if needed
    apply_recurring(user_id)

    # ----------------------------------------
    # TOTAL ALLOWANCE (ever added)
    # ----------------------------------------
    cursor.execute("SELECT SUM(amount) AS t FROM allowances WHERE user_id=?", (user_id,))
    allowance = cursor.fetchone()["t"] or 0

    # ----------------------------------------
    # TOTAL EXPENSES (manual + recurring)
    # ----------------------------------------
    cursor.execute("SELECT SUM(amount) AS t FROM expenses WHERE user_id=?", (user_id,))
    expenses = cursor.fetchone()["t"] or 0

    # ----------------------------------------
    # TOTAL SAVINGS (goals saved_amount)
    # ----------------------------------------
    cursor.execute("SELECT SUM(saved_amount) AS t FROM goals WHERE user_id=?", (user_id,))
    savings = cursor.fetchone()["t"] or 0

    # ----------------------------------------
    # RECURRING EXPENSES OF THIS MONTH ONLY
    # ----------------------------------------
    current_month = datetime.now().strftime("%Y-%m")
    cursor.execute("""
        SELECT SUM(amount) AS t 
        FROM expenses
        WHERE user_id=? 
        AND description LIKE '%(Recurring)%'
        AND date LIKE ?
    """, (user_id, f"{current_month}-%"))
    recurring_this_month = cursor.fetchone()["t"] or 0

    # ----------------------------------------
    # FINAL BALANCE CALCULATION
    # ----------------------------------------
    balance = allowance - expenses - savings

    # Daily safe spending limit
    safe_limit = balance / 30 if balance > 0 else 0

    # ----------------------------------------
    # GOALS LIST
    # ----------------------------------------
    cursor.execute("SELECT * FROM goals WHERE user_id=?", (user_id,))
    goals = cursor.fetchall()

    return render_template(
        "dashboard.html",
        allowance=round(allowance, 2),
        expenses=round(expenses, 2),
        savings=round(savings, 2),
        recurring_month=round(recurring_this_month, 2),
        balance=round(balance, 2),
        safe_limit=round(safe_limit, 2),
        goals=goals
    )



# -------------------------
# Run app
# -------------------------
if __name__ == "__main__":
    # ensure DB exists / initialized
    try:
        init_db()
    except Exception:
        pass

    print("\n🔍 Registered routes:")
    for rule in app.url_map.iter_rules():
        print("➡", rule)
    print("--------------------------------------------------\n")
    app.run(debug=True)
