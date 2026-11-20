"""Parking Slot Allocation System - Flask application."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (Flask, flash, redirect, render_template, request, session,
                   url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import config
import db
from utils import (VEHICLE_TYPES, calculate_fee, next_slot_numbers,
                   normalise_vehicle_no, parse_ticket_ref, to_dt,
                   valid_vehicle_no)

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.teardown_appcontext(db.close_db)


# ---------- template helpers ----------
@app.template_filter("dt")
def fmt_dt(value):
    value = to_dt(value)
    return value.strftime("%d %b %Y, %H:%M") if value else "-"


@app.template_filter("tno")
def fmt_ticket_no(ticket_id):
    return f"T{int(ticket_id):05d}"


@app.template_filter("duration")
def fmt_duration(start, end=None):
    start, end = to_dt(start), to_dt(end) or datetime.now()
    minutes = max(int((end - start).total_seconds() // 60), 0)
    return f"{minutes // 60}h {minutes % 60:02d}m"


@app.context_processor
def inject_globals():
    return {"VEHICLE_TYPES": VEHICLE_TYPES}


# ---------- access control ----------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


# ---------- login ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = db.query("SELECT * FROM users WHERE username=%s", (username,), one=True)
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(user_id=user["user_id"], username=user["username"], role=user["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- dashboard ----------
@app.route("/")
@login_required
def dashboard():
    summary = db.query(
        "SELECT slot_type, COUNT(*) AS total, SUM(is_free) AS free_slots "
        "FROM slots GROUP BY slot_type ORDER BY slot_type")
    for row in summary:
        row["free_slots"] = int(row["free_slots"] or 0)
        row["occupied"] = row["total"] - row["free_slots"]
    open_tickets = db.query(
        "SELECT t.ticket_id, t.vehicle_no, t.entry_time, s.slot_no, s.slot_type "
        "FROM tickets t JOIN slots s ON s.slot_id = t.slot_id "
        "WHERE t.status='OPEN' ORDER BY t.entry_time")
    return render_template("dashboard.html", summary=summary, open_tickets=open_tickets)


# ---------- slots & rates (admin) ----------
@app.route("/slots")
@admin_required
def slots():
    rows = db.query("SELECT * FROM slots ORDER BY slot_id")
    return render_template("slots.html", slots=rows)


@app.route("/slots/add", methods=["POST"])
@admin_required
def slots_add():
    level = request.form.get("level", "").strip().upper()
    slot_type = request.form.get("slot_type", "")
    try:
        count = int(request.form.get("count", "0"))
    except ValueError:
        count = 0
    if not level or len(level) > 5 or not level.isalnum() or slot_type not in VEHICLE_TYPES or not 1 <= count <= 50:
        flash("Enter a level (letters/digits), a slot type and a count between 1 and 50.", "error")
        return redirect(url_for("slots"))
    existing = [r["slot_no"] for r in db.query("SELECT slot_no FROM slots")]
    for slot_no in next_slot_numbers(existing, level, slot_type, count):
        db.execute("INSERT INTO slots (slot_no, slot_type, level) VALUES (%s,%s,%s)",
                   (slot_no, slot_type, level))
    db.commit()
    flash(f"Added {count} {VEHICLE_TYPES[slot_type]} slot(s) on level {level}.", "success")
    return redirect(url_for("slots"))


@app.route("/slots/<int:slot_id>/delete", methods=["POST"])
@admin_required
def slots_delete(slot_id):
    slot = db.query("SELECT * FROM slots WHERE slot_id=%s", (slot_id,), one=True)
    used = db.query("SELECT COUNT(*) AS n FROM tickets WHERE slot_id=%s", (slot_id,), one=True)["n"]
    if not slot:
        flash("Slot not found.", "error")
    elif not slot["is_free"]:
        flash("An occupied slot cannot be deleted.", "error")
    elif used:
        flash("This slot has ticket history and cannot be deleted.", "error")
    else:
        db.execute("DELETE FROM slots WHERE slot_id=%s", (slot_id,))
        db.commit()
        flash(f"Slot {slot['slot_no']} deleted.", "success")
    return redirect(url_for("slots"))


@app.route("/rates", methods=["GET", "POST"])
@admin_required
def rates():
    if request.method == "POST":
        try:
            new_rates = {}
            for code in VEHICLE_TYPES:
                first = Decimal(request.form[f"first_{code}"])
                extra = Decimal(request.form[f"extra_{code}"])
                if first < 0 or extra < 0 or first > 99999 or extra > 99999:
                    raise InvalidOperation
                new_rates[code] = (first, extra)
        except (InvalidOperation, KeyError):
            flash("Rates must be valid, non-negative numbers.", "error")
            return redirect(url_for("rates"))
        for code, (first, extra) in new_rates.items():
            db.execute("UPDATE rates SET first_hour=%s, extra_hour=%s WHERE slot_type=%s",
                       (first, extra, code))
        db.commit()
        flash("Rates updated.", "success")
        return redirect(url_for("rates"))
    rows = {r["slot_type"]: r for r in db.query("SELECT * FROM rates")}
    return render_template("rates.html", rates=rows)


# ---------- users (admin) ----------
@app.route("/users", methods=["GET", "POST"])
@admin_required
def users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        if not (3 <= len(username) <= 50) or len(password) < 6 or role not in ("admin", "operator"):
            flash("Username needs 3+ characters, password 6+ characters and a valid role.", "error")
        elif db.query("SELECT 1 FROM users WHERE username=%s", (username,), one=True):
            flash("That username already exists.", "error")
        else:
            db.execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                       (username, generate_password_hash(password), role))
            db.commit()
            flash(f"User {username} created.", "success")
        return redirect(url_for("users"))
    return render_template("users.html", users=db.query("SELECT user_id, username, role FROM users ORDER BY user_id"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def users_delete(user_id):
    target = db.query("SELECT * FROM users WHERE user_id=%s", (user_id,), one=True)
    admins = db.query("SELECT COUNT(*) AS n FROM users WHERE role='admin'", one=True)["n"]
    used = db.query("SELECT COUNT(*) AS n FROM tickets WHERE issued_by=%s", (user_id,), one=True)["n"]
    if not target:
        flash("User not found.", "error")
    elif user_id == session["user_id"]:
        flash("You cannot delete your own account.", "error")
    elif target["role"] == "admin" and admins <= 1:
        flash("The last admin cannot be deleted.", "error")
    elif used:
        flash("This user has issued tickets and cannot be deleted.", "error")
    else:
        db.execute("DELETE FROM users WHERE user_id=%s", (user_id,))
        db.commit()
        flash(f"User {target['username']} deleted.", "success")
    return redirect(url_for("users"))


# ---------- vehicle entry ----------
@app.route("/entry", methods=["GET", "POST"])
@login_required
def entry():
    if request.method == "POST":
        vehicle_no = normalise_vehicle_no(request.form.get("vehicle_no"))
        vehicle_type = request.form.get("vehicle_type", "")
        if not valid_vehicle_no(vehicle_no) or vehicle_type not in VEHICLE_TYPES:
            flash("Enter a valid vehicle number (4-12 letters/digits) and choose a vehicle type.", "error")
            return render_template("entry.html", vehicle_no=vehicle_no, vehicle_type=vehicle_type)
        if db.query("SELECT 1 FROM tickets WHERE vehicle_no=%s AND status='OPEN'", (vehicle_no,), one=True):
            flash(f"{vehicle_no} is already parked (open ticket exists).", "error")
            return render_template("entry.html", vehicle_no=vehicle_no, vehicle_type=vehicle_type)

        # Nearest slot = lowest slot_id of the right type (slots are added starting from the gate).
        slot = None
        for _ in range(3):  # retry if another operator grabs the same slot at the same moment
            candidate = db.query(
                "SELECT slot_id, slot_no FROM slots WHERE slot_type=%s AND is_free=1 "
                "ORDER BY slot_id LIMIT 1", (vehicle_type,), one=True)
            if not candidate:
                break
            taken, _ = db.execute("UPDATE slots SET is_free=0 WHERE slot_id=%s AND is_free=1",
                                  (candidate["slot_id"],))
            if taken == 1:
                slot = candidate
                break
        if not slot:
            db.rollback()
            flash(f"Parking full: no free {VEHICLE_TYPES[vehicle_type]} slot.", "error")
            return render_template("entry.html", vehicle_no=vehicle_no, vehicle_type=vehicle_type)

        if not db.query("SELECT 1 FROM vehicles WHERE vehicle_no=%s", (vehicle_no,), one=True):
            db.execute("INSERT INTO vehicles (vehicle_no, vehicle_type) VALUES (%s,%s)",
                       (vehicle_no, vehicle_type))
        _, ticket_id = db.execute(
            "INSERT INTO tickets (vehicle_no, slot_id, issued_by, entry_time) VALUES (%s,%s,%s,%s)",
            (vehicle_no, slot["slot_id"], session["user_id"], datetime.now()))
        db.commit()
        return redirect(url_for("ticket", ticket_id=ticket_id))
    return render_template("entry.html", vehicle_no="", vehicle_type="")


@app.route("/ticket/<int:ticket_id>")
@login_required
def ticket(ticket_id):
    row = db.query(
        "SELECT t.*, s.slot_no, s.level, s.slot_type, u.username FROM tickets t "
        "JOIN slots s ON s.slot_id=t.slot_id JOIN users u ON u.user_id=t.issued_by "
        "WHERE t.ticket_id=%s", (ticket_id,), one=True)
    if not row:
        flash("Ticket not found.", "error")
        return redirect(url_for("dashboard"))
    return render_template("ticket.html", t=row)


# ---------- vehicle exit & billing ----------
def _open_ticket(ticket_id):
    return db.query(
        "SELECT t.*, s.slot_no, s.slot_type FROM tickets t JOIN slots s ON s.slot_id=t.slot_id "
        "WHERE t.ticket_id=%s AND t.status='OPEN'", (ticket_id,), one=True)


@app.route("/exit", methods=["GET", "POST"])
@login_required
def exit_vehicle():
    if request.method == "POST":
        kind, value = parse_ticket_ref(request.form.get("ref"))
        if kind == "ticket":
            row = _open_ticket(value)
        else:
            row = db.query("SELECT ticket_id FROM tickets WHERE vehicle_no=%s AND status='OPEN'",
                           (value,), one=True)
        if not row:
            flash("No open ticket found for that ticket number / vehicle number.", "error")
            return render_template("exit.html")
        return redirect(url_for("exit_bill", ticket_id=row["ticket_id"]))
    return render_template("exit.html")


@app.route("/exit/<int:ticket_id>")
@login_required
def exit_bill(ticket_id):
    t = _open_ticket(ticket_id)
    if not t:
        flash("That ticket is not open.", "error")
        return redirect(url_for("exit_vehicle"))
    rate = db.query("SELECT * FROM rates WHERE slot_type=%s", (t["slot_type"],), one=True)
    now = datetime.now()
    hours, amount = calculate_fee(to_dt(t["entry_time"]), now, rate["first_hour"], rate["extra_hour"])
    return render_template("exit_bill.html", t=t, rate=rate, now=now, hours=hours, amount=amount)


@app.route("/exit/<int:ticket_id>/pay", methods=["POST"])
@login_required
def exit_pay(ticket_id):
    t = _open_ticket(ticket_id)
    if not t:
        flash("That ticket is not open (already paid?).", "error")
        return redirect(url_for("exit_vehicle"))
    rate = db.query("SELECT * FROM rates WHERE slot_type=%s", (t["slot_type"],), one=True)
    now = datetime.now().replace(microsecond=0)
    hours, amount = calculate_fee(to_dt(t["entry_time"]), now, rate["first_hour"], rate["extra_hour"])
    closed, _ = db.execute(
        "UPDATE tickets SET status='CLOSED', exit_time=%s WHERE ticket_id=%s AND status='OPEN'",
        (now, ticket_id))
    if closed != 1:
        db.rollback()
        flash("That ticket was already closed.", "error")
        return redirect(url_for("exit_vehicle"))
    db.execute("INSERT INTO bills (ticket_id, hours, amount, paid_time) VALUES (%s,%s,%s,%s)",
               (ticket_id, hours, amount, now))
    db.execute("UPDATE slots SET is_free=1 WHERE slot_id=%s", (t["slot_id"],))
    db.commit()
    return redirect(url_for("receipt", ticket_id=ticket_id))


@app.route("/receipt/<int:ticket_id>")
@login_required
def receipt(ticket_id):
    row = db.query(
        "SELECT t.*, s.slot_no, b.bill_id, b.hours, b.amount, b.paid_time FROM tickets t "
        "JOIN slots s ON s.slot_id=t.slot_id JOIN bills b ON b.ticket_id=t.ticket_id "
        "WHERE t.ticket_id=%s", (ticket_id,), one=True)
    if not row:
        flash("Receipt not found.", "error")
        return redirect(url_for("dashboard"))
    return render_template("receipt.html", r=row)


# ---------- reports (admin) ----------
@app.route("/reports")
@admin_required
def reports():
    try:
        day = date.fromisoformat(request.args.get("date", "")).isoformat()
    except ValueError:
        day = date.today().isoformat()
    occupancy = db.query(
        "SELECT slot_type, COUNT(*) AS total, SUM(is_free) AS free_slots FROM slots "
        "GROUP BY slot_type ORDER BY slot_type")
    for row in occupancy:
        row["free_slots"] = int(row["free_slots"] or 0)
        row["occupied"] = row["total"] - row["free_slots"]
    entries = db.query("SELECT COUNT(*) AS n FROM tickets WHERE DATE(entry_time)=%s", (day,), one=True)["n"]
    totals = db.query("SELECT COUNT(*) AS vehicles, COALESCE(SUM(amount),0) AS revenue "
                      "FROM bills WHERE DATE(paid_time)=%s", (day,), one=True)
    bills = db.query(
        "SELECT b.bill_id, t.ticket_id, t.vehicle_no, s.slot_no, t.entry_time, t.exit_time, b.hours, b.amount "
        "FROM bills b JOIN tickets t ON t.ticket_id=b.ticket_id JOIN slots s ON s.slot_id=t.slot_id "
        "WHERE DATE(b.paid_time)=%s ORDER BY b.paid_time", (day,))
    last7 = db.query(
        "SELECT DATE(paid_time) AS day, COUNT(*) AS vehicles, SUM(amount) AS revenue FROM bills "
        "GROUP BY DATE(paid_time) ORDER BY day DESC LIMIT 7")
    return render_template("reports.html", day=day, occupancy=occupancy, entries=entries,
                           totals=totals, bills=bills, last7=last7)


if __name__ == "__main__":
    app.run(debug=True)
