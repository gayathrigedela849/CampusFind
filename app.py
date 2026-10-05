from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_from_directory
)
import sqlite3
import os
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "campusfind_secret_key_change_this")

DATABASE = os.environ.get("DATABASE_PATH", "campusfind.db")
PUBLIC_UPLOAD_FOLDER = os.path.join("static", "uploads", "public")
PRIVATE_UPLOAD_FOLDER = os.path.join("static", "uploads", "private")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

os.makedirs(PUBLIC_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PRIVATE_UPLOAD_FOLDER, exist_ok=True)


def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file, folder):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        return None

    extension = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{extension}"
    file.save(os.path.join(folder, filename))
    return filename


def current_user():
    if "user_id" not in session:
        return None
    connection = get_db_connection()
    user = connection.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    connection.close()
    return user


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


def login_required():
    if "user_id" not in session:
        flash("Please login to continue.", "warning")
        return False
    return True


def admin_required():
    user = current_user()
    if not user or user["role"] not in ("admin", "hod"):
        flash("Admin/HOD access is required.", "danger")
        return False
    return True


def add_notification(user_id, title, message):
    connection = get_db_connection()
    connection.execute(
        """
        INSERT INTO notifications (user_id, title, message, created_at, is_read)
        VALUES (?, ?, ?, ?, 0)
        """,
        (user_id, title, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    connection.commit()
    connection.close()


def create_tables():
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fullname TEXT NOT NULL,
            roll_no TEXT UNIQUE NOT NULL,
            department TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            created_at TEXT NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reporter_id INTEGER NOT NULL,
            item_type TEXT NOT NULL CHECK(item_type IN ('lost', 'found')),
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            item_date TEXT NOT NULL,
            item_time TEXT,
            public_image TEXT,
            private_image TEXT,
            verification_details TEXT,
            status TEXT NOT NULL DEFAULT 'Lost',
            created_at TEXT NOT NULL,
            FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            claimant_id INTEGER NOT NULL,
            lost_location TEXT NOT NULL,
            lost_date TEXT NOT NULL,
            lost_time TEXT,
            ownership_details TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Claim Requested',
            admin_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
            FOREIGN KEY (claimant_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    # Create default Admin account only if an Admin does not already exist.
    admin = connection.execute(
        "SELECT id FROM users WHERE role = 'admin'"
    ).fetchone()

    if not admin:
        connection.execute(
            """
            INSERT INTO users
            (fullname, roll_no, department, email, password, role, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "CampusFind Admin",
                "ADMIN001",
                "Administration",
                "admin@campusfind.local",
                generate_password_hash("Admin@123"),
                "admin",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

    
    connection.commit()
    connection.close()


@app.route("/")
def home():
    connection = get_db_connection()
    found_items = connection.execute(
        """
        SELECT items.*, users.fullname AS reporter_name
        FROM items
        JOIN users ON users.id = items.reporter_id
        WHERE items.item_type = 'found' AND items.status != 'Returned'
        ORDER BY items.created_at DESC
        LIMIT 6
        """
    ).fetchall()
    connection.close()
    return render_template("home.html", found_items=found_items)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        fullname = request.form["fullname"].strip()
        roll_no = request.form["roll_no"].strip()
        department = request.form["department"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return render_template("register.html")

        connection = get_db_connection()
        try:
            connection.execute(
                """
                INSERT INTO users
                (fullname, roll_no, department, email, password, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fullname,
                    roll_no,
                    department,
                    email,
                    generate_password_hash(password),
                    "student",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            connection.close()
            flash("Roll number or email already exists.", "danger")
            return render_template("register.html")
        connection.close()

        flash("Account created successfully. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        connection = get_db_connection()
        user = connection.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        connection.close()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["role"] = user["role"]
            session["fullname"] = user["fullname"]

            if user["role"] in ("admin", "hod"):
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))

    user_id = session["user_id"]
    connection = get_db_connection()

    stats = {
        "lost": connection.execute(
            "SELECT COUNT(*) AS c FROM items WHERE reporter_id = ? AND item_type = 'lost'",
            (user_id,),
        ).fetchone()["c"],
        "found": connection.execute(
            "SELECT COUNT(*) AS c FROM items WHERE reporter_id = ? AND item_type = 'found'",
            (user_id,),
        ).fetchone()["c"],
        "claims": connection.execute(
            "SELECT COUNT(*) AS c FROM claims WHERE claimant_id = ?",
            (user_id,),
        ).fetchone()["c"],
        "returned": connection.execute(
            "SELECT COUNT(*) AS c FROM claims WHERE claimant_id = ? AND status = 'Returned'",
            (user_id,),
        ).fetchone()["c"],
    }

    recent_reports = connection.execute(
        """
        SELECT * FROM items
        WHERE reporter_id = ?
        ORDER BY created_at DESC
        LIMIT 5
        """,
        (user_id,),
    ).fetchall()

    recent_claims = connection.execute(
        """
        SELECT claims.*, items.title, items.public_image
        FROM claims
        JOIN items ON items.id = claims.item_id
        WHERE claims.claimant_id = ?
        ORDER BY claims.created_at DESC
        LIMIT 5
        """,
        (user_id,),
    ).fetchall()

    connection.close()
    return render_template(
        "dashboard.html",
        stats=stats,
        recent_reports=recent_reports,
        recent_claims=recent_claims,
    )

@app.route("/report/<item_type>", methods=["GET", "POST"])
def report_item(item_type):
    if not login_required():
        return redirect(url_for("login"))

    if item_type not in ("lost", "found"):
        flash("Invalid report type.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        location = request.form.get("location", "").strip()
        item_date = request.form.get("item_date", "")
        item_time = request.form.get("item_time", "")
        verification_details = request.form.get(
            "verification_details", ""
        ).strip()

        public_file = request.files.get("public_image")

        # -------------------------------------------------
        # PUBLIC IMAGE
        # -------------------------------------------------
        # For FOUND items, public image is required.
        # For LOST items, public image is optional.

        if item_type == "found":

            if not public_file or not public_file.filename:
                flash(
                    "Public preview picture is required for a found item.",
                    "danger"
                )

                return render_template(
                    "report_item.html",
                    item_type=item_type,
                    form_data=request.form
                )

            if not allowed_file(public_file.filename):
                flash(
                    "Public preview picture must be JPG, JPEG, PNG or WEBP.",
                    "danger"
                )

                return render_template(
                    "report_item.html",
                    item_type=item_type,
                    form_data=request.form
                )

            public_image = save_upload(
                public_file,
                PUBLIC_UPLOAD_FOLDER
            )

        else:

            # For LOST items, picture is optional.
            if public_file and public_file.filename:

                if not allowed_file(public_file.filename):
                    flash(
                        "Public picture must be JPG, JPEG, PNG or WEBP.",
                        "danger"
                    )

                    return render_template(
                        "report_item.html",
                        item_type=item_type,
                        form_data=request.form
                    )

                public_image = save_upload(
                    public_file,
                    PUBLIC_UPLOAD_FOLDER
                )

            else:
                public_image = None

        # -------------------------------------------------
        # PRIVATE VERIFICATION IMAGE
        # -------------------------------------------------
        # Private verification information is completely
        # optional for FOUND items.

        private_image = None

        if item_type == "found":

            private_file = request.files.get("private_image")

            if private_file and private_file.filename:

                if not allowed_file(private_file.filename):
                    flash(
                        "Private verification picture must be JPG, JPEG, PNG or WEBP.",
                        "danger"
                    )

                    return render_template(
                        "report_item.html",
                        item_type=item_type,
                        form_data=request.form
                    )

                private_image = save_upload(
                    private_file,
                    PRIVATE_UPLOAD_FOLDER
                )

        # -------------------------------------------------
        # CHECK FOR DUPLICATE REPORT
        # -------------------------------------------------

        connection = get_db_connection()

        duplicate = connection.execute(
            """
            SELECT id
            FROM items
            WHERE reporter_id = ?
              AND item_type = ?
              AND LOWER(title) = LOWER(?)
              AND LOWER(category) = LOWER(?)
              AND LOWER(location) = LOWER(?)
              AND item_date = ?
            LIMIT 1
            """,
            (
                session["user_id"],
                item_type,
                title,
                category,
                location,
                item_date,
            ),
        ).fetchone()

        if duplicate:
            connection.close()

            flash(
                "You have already reported this item with the same details.",
                "warning"
            )

            return render_template(
                "report_item.html",
                item_type=item_type,
                form_data=request.form
            )

        # -------------------------------------------------
        # SAVE ITEM TO DATABASE
        # -------------------------------------------------

        connection.execute(
            """
            INSERT INTO items
            (
                reporter_id,
                item_type,
                title,
                category,
                description,
                location,
                item_date,
                item_time,
                public_image,
                private_image,
                verification_details,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session["user_id"],
                item_type,
                title,
                category,
                description,
                location,
                item_date,
                item_time,
                public_image,
                private_image,
                verification_details,
                "Found" if item_type == "found" else "Lost",
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

        connection.commit()
        connection.close()

        # -------------------------------------------------
        # SUCCESS MESSAGE
        # -------------------------------------------------

        flash(
            f"{item_type.capitalize()} item reported successfully.",
            "success"
        )

        return redirect(url_for("my_reports"))

    # -----------------------------------------------------
    # GET REQUEST
    # -----------------------------------------------------

    return render_template(
        "report_item.html",
        item_type=item_type
    )

@app.route("/found-items")
def found_items():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()

    connection = get_db_connection()

    query = """
        SELECT items.*, users.fullname AS reporter_name
        FROM items
        JOIN users ON users.id = items.reporter_id
        WHERE items.item_type = 'found'
        AND items.status != 'Returned'
    """
    params = []

    if search:
        query += """
            AND (
                items.title LIKE ?
                OR items.description LIKE ?
                OR items.location LIKE ?
                OR items.category LIKE ?
            )
        """
        term = f"%{search}%"
        params.extend([term, term, term, term])

    if category:
        query += " AND items.category = ?"
        params.append(category)

    query += " ORDER BY items.created_at DESC"

    items = connection.execute(query, params).fetchall()
    categories = connection.execute(
        """
        SELECT DISTINCT category FROM items
        WHERE item_type = 'found'
        ORDER BY category
        """
    ).fetchall()

    connection.close()
    return render_template(
        "found_items.html",
        items=items,
        categories=categories,
        search=search,
        selected_category=category,
    )


@app.route("/item/<int:item_id>")
def item_detail(item_id):
    connection = get_db_connection()

    item = connection.execute(
        """
        SELECT items.*, users.fullname AS reporter_name
        FROM items
        JOIN users ON users.id = items.reporter_id
        WHERE items.id = ?
        """,
        (item_id,),
    ).fetchone()

    if not item:
        connection.close()
        flash("Item not found.", "danger")
        return redirect(url_for("found_items"))

    # Check whether the currently logged-in user has claimed this item
    existing_claim = None

    if session.get("user_id"):
        existing_claim = connection.execute(
            """
            SELECT *
            FROM claims
            WHERE item_id = ?
              AND claimant_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (item_id, session["user_id"]),
        ).fetchone()

    # Check whether ANYONE has claimed this item
    item_has_claim = connection.execute(
        """
        SELECT id
        FROM claims
        WHERE item_id = ?
        LIMIT 1
        """,
        (item_id,),
    ).fetchone()

    connection.close()

    return render_template(
        "item_detail.html",
        item=item,
        existing_claim=existing_claim,
        item_has_claim=item_has_claim,
    )

@app.route("/claim/<int:item_id>", methods=["GET", "POST"])
def claim_item(item_id):
    if not login_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    item = connection.execute(
        """
        SELECT *
        FROM items
        WHERE id = ?
            AND item_type = 'found'
            AND status NOT IN (
                'Claim Approved',
                'Ready for Collection',
                'Returned'
        )
      """,
     (item_id,),
    ).fetchone()

    if not item:
        connection.close()
        flash("Found item not available.", "danger")
        return redirect(url_for("found_items"))

    if request.method == "POST":
        lost_location = request.form["lost_location"].strip()
        lost_date = request.form["lost_date"]
        lost_time = request.form.get("lost_time", "")
        ownership_details = request.form["ownership_details"].strip()
        
        if not lost_location or not lost_date or not ownership_details:
            connection.close()
            flash("Please fill in all required claim details.", "danger")
            return redirect(url_for("claim_item", item_id=item_id))

        if len(lost_location) > 200:
            connection.close()
            flash("Lost location is too long.", "danger")
            return redirect(url_for("claim_item", item_id=item_id))

        if len(ownership_details) < 5:
            connection.close()
            flash("Please provide more details to verify ownership.", "danger")
            return redirect(url_for("claim_item", item_id=item_id))

        if len(ownership_details) > 1000:
            connection.close()
            flash("Ownership details are too long.", "danger")
            return redirect(url_for("claim_item", item_id=item_id))

        duplicate = connection.execute(
            """
            SELECT id FROM claims
            WHERE item_id = ? AND claimant_id = ?
            AND status NOT IN ('Rejected', 'Returned')
            """,
            (item_id, session["user_id"]),
        ).fetchone()

        if duplicate:
            connection.close()
            flash("You already have an active claim for this item.", "warning")
            return redirect(url_for("item_detail", item_id=item_id))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        connection.execute(
            """
            INSERT INTO claims
            (
                item_id, claimant_id, lost_location, lost_date,
                lost_time, ownership_details, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                session["user_id"],
                lost_location,
                lost_date,
                lost_time,
                ownership_details,
                "Claim Requested",
                now,
                now,
            ),
        )
        connection.commit()
        connection.close()

        flash("Claim submitted for verification.", "success")
        return redirect(url_for("my_claims"))

    connection.close()
    return render_template("claim.html", item=item)


@app.route("/my-claims")
def my_claims():
    if not login_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    claims = connection.execute(
        """
        SELECT claims.*, items.title, items.category, items.location,
               items.public_image
        FROM claims
        JOIN items ON items.id = claims.item_id
        WHERE claims.claimant_id = ?
        ORDER BY claims.created_at DESC
        """,
        (session["user_id"],),
    ).fetchall()
    connection.close()

    return render_template("my_claims.html", claims=claims)


@app.route("/my-reports")
def my_reports():
    if not login_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    reports = connection.execute(
        """
        SELECT * FROM items
        WHERE reporter_id = ?
        ORDER BY created_at DESC
        """,
        (session["user_id"],),
    ).fetchall()
    connection.close()

    return render_template("my_reports.html", reports=reports)

@app.route("/delete-report/<int:item_id>", methods=["POST"])
def delete_report(item_id):
    if not login_required():
        return redirect(url_for("login"))

    connection = get_db_connection()

    # Find the report
    item = connection.execute(
        """
        SELECT *
        FROM items
        WHERE id = ?
        """,
        (item_id,),
    ).fetchone()

    # Report does not exist
    if not item:
        connection.close()
        flash("Report not found.", "danger")
        return redirect(url_for("my_reports"))

    user = current_user()

    # Only the person who created the report can delete it.
    # Admin/HOD are also blocked here if the report has a claim.
    if user["role"] not in ("admin", "hod"):
        if item["reporter_id"] != session["user_id"]:
            connection.close()
            flash("You can only delete your own reports.", "danger")
            return redirect(url_for("my_reports"))

    # Check whether this item already has a claim
    existing_claim = connection.execute(
        """
        SELECT id
        FROM claims
        WHERE item_id = ?
        LIMIT 1
        """,
        (item_id,),
    ).fetchone()

    # Claimed products must not be deleted
    if existing_claim:
        connection.close()
        flash(
            "This report cannot be deleted because it already has a claim.",
            "warning"
        )
        return redirect(url_for("item_detail", item_id=item_id))

    # Delete any notifications related to this item title
    connection.execute(
        """
        DELETE FROM notifications
        WHERE message LIKE ?
        """,
        (f"%{item['title']}%",),
    )

    # Delete the report
    connection.execute(
        """
        DELETE FROM items
        WHERE id = ?
        """,
        (item_id,),
    )

    connection.commit()
    connection.close()

    # Delete public image
    if item["public_image"]:
        public_path = os.path.join(
            PUBLIC_UPLOAD_FOLDER,
            item["public_image"]
        )

        if os.path.exists(public_path):
            os.remove(public_path)

    # Delete private verification image
    if item["private_image"]:
        private_path = os.path.join(
            PRIVATE_UPLOAD_FOLDER,
            item["private_image"]
        )

        if os.path.exists(private_path):
            os.remove(private_path)

    flash("Report permanently deleted.", "success")

    return redirect(url_for("my_reports"))


@app.route("/notifications")
def notifications():
    if not login_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    notes = connection.execute(
        """
        SELECT * FROM notifications
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (session["user_id"],),
    ).fetchall()

    connection.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
        (session["user_id"],),
    )
    connection.commit()
    connection.close()

    return render_template("notifications.html", notifications=notes)


# ---------------- ADMIN ----------------

@app.route("/admin")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("login"))

    connection = get_db_connection()

    stats = {
        "users": connection.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'student'"
        ).fetchone()["c"],
        
        "hods": connection.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'hod'"
        ).fetchone()["c"],

        "lost": connection.execute(
            "SELECT COUNT(*) AS c FROM items WHERE item_type = 'lost' AND status !='Returned'"
        ).fetchone()["c"],

        "found": connection.execute(
            "SELECT COUNT(*) AS c FROM items WHERE item_type = 'found' AND status !='Returned'"
        ).fetchone()["c"],

        "claims": connection.execute(
            "SELECT COUNT(*) AS c FROM claims WHERE status != 'Returned'"
        ).fetchone()["c"],

        "returned": connection.execute(
            "SELECT COUNT(*) AS c FROM claims WHERE status = 'Returned'"
        ).fetchone()["c"],

        "pending": connection.execute(
            """
            SELECT COUNT(*) AS c
            FROM claims
            WHERE status IN (
                'Claim Requested',
                'Under Verification',
                'Ready for Collection'
            )
            """
        ).fetchone()["c"],
    }

    # Recent Activity
    # Returned items are hidden from Recent Activity.
    # They are NOT deleted from the database.
    recent_items = connection.execute(
        """
        SELECT items.*, users.fullname AS reporter_name
        FROM items
        JOIN users ON users.id = items.reporter_id
        WHERE items.status != 'Returned'
        ORDER BY items.created_at DESC
        LIMIT 8
        """
    ).fetchall()

    connection.close()

    return render_template(
        "admin_dashboard.html",
        stats=stats,
        recent_items=recent_items,
    )
    
@app.route("/admin/items")
def admin_items():
    if not admin_required():
        return redirect(url_for("login"))

    item_type = request.args.get("type", "").strip().lower()

    connection = get_db_connection()

    query = """
        SELECT items.*, users.fullname AS reporter_name,
               users.email AS reporter_email
        FROM items
        JOIN users ON users.id = items.reporter_id
    """

    params = []

    if item_type in ("lost", "found"):
        query += " WHERE items.item_type = ?"
        params.append(item_type)

    query += " ORDER BY items.created_at DESC"

    items = connection.execute(query, params).fetchall()

    connection.close()

    return render_template(
        "admin_items.html",
        items=items,
        item_type=item_type,
    )

@app.route("/admin/claims")
def admin_claims():
    if not admin_required():
        return redirect(url_for("login"))

    view = request.args.get("view", "").strip().lower()
    search = request.args.get("search", "").strip()

    connection = get_db_connection()

    query = """
        SELECT claims.*,
               items.title,
               items.category,
               items.location,
               items.private_image,
               items.verification_details,
               users.fullname AS claimant_name,
               users.roll_no,
               users.department,
               users.email
        FROM claims
        JOIN items ON items.id = claims.item_id
        JOIN users ON users.id = claims.claimant_id
        WHERE 1 = 1
    """

    params = []

    # -------------------------------------------------
    # STATUS FILTER
    # -------------------------------------------------

    if view == "pending":
        query += """
            AND claims.status IN (
                'Claim Requested',
                'Under Verification'
            )
        """

    elif view == "returned":
        query += """
            AND claims.status = 'Returned'
        """

    elif not search:
        # Normal Claims page shows active/non-returned claims.
        query += """
            AND claims.status != 'Returned'
        """

    # -------------------------------------------------
    # SEARCH
    # -------------------------------------------------

    if search:
        query += """
            AND (
                LOWER(items.title) LIKE LOWER(?)
                OR LOWER(items.category) LIKE LOWER(?)
                OR LOWER(users.fullname) LIKE LOWER(?)
                OR LOWER(users.roll_no) LIKE LOWER(?)
            )
        """

        search_value = f"%{search}%"

        params.extend([
            search_value,
            search_value,
            search_value,
            search_value
        ])

    # -------------------------------------------------
    # ORDER
    # -------------------------------------------------

    query += " ORDER BY claims.created_at DESC"

    claims = connection.execute(
        query,
        params
    ).fetchall()

    connection.close()

    return render_template(
        "admin_claims.html",
        claims=claims,
        view=view,
        search=search
    )
    
@app.route("/admin/claim/<int:claim_id>/status", methods=["POST"])
def update_claim_status(claim_id):
    if not admin_required():
        return redirect(url_for("login"))

    new_status = request.form["status"]

    allowed_statuses = {
        "Under Verification",
        "Approved",
        "Rejected",
        "Ready for Collection",
        "Returned",
    }

    if new_status not in allowed_statuses:
        flash("Invalid claim status.", "danger")
        return redirect(url_for("admin_claims"))

    admin_note = request.form.get("admin_note", "").strip()

    # Remember which claims page the admin came from
    current_view = request.form.get("view", "").strip().lower()

    connection = get_db_connection()

    claim = connection.execute(
        """
        SELECT claims.*, items.title, items.reporter_id
        FROM claims
        JOIN items ON items.id = claims.item_id
        WHERE claims.id = ?
        """,
        (claim_id,),
    ).fetchone()

    if not claim:
        connection.close()
        flash("Claim not found.", "danger")
        return redirect(url_for("admin_claims"))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Update claim status
    connection.execute(
        """
        UPDATE claims
        SET status = ?, admin_note = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            new_status,
            admin_note,
            now,
            claim_id,
        ),
    )
    # If this claim is approved, reject all other active claims
    # for the same item.
    if new_status == "Approved":
        connection.execute(
            """
            UPDATE claims
            SET status = 'Rejected',
                admin_note = 'Another claim for this item was approved.',
                updated_at = ?
            WHERE item_id = ?
                AND id != ?
               AND status NOT IN ('Rejected', 'Returned')
            """,
            (
                now,
                claim["item_id"],
                claim_id,
            ),
        )
    

    # Update the item's status
    if new_status == "Returned":
        connection.execute(
            """
            UPDATE items
            SET status = 'Returned'
            WHERE id = ?
            """,
            (claim["item_id"],),
        )

    elif new_status == "Approved":
        connection.execute(
            """
            UPDATE items
            SET status = 'Claim Approved'
            WHERE id = ?
            """,
            (claim["item_id"],),
        )

    elif new_status == "Ready for Collection":
        connection.execute(
            """
            UPDATE items
            SET status = 'Ready for Collection'
            WHERE id = ?
            """,
            (claim["item_id"],),
        )

    elif new_status == "Rejected":
        connection.execute(
            """
            UPDATE items
            SET status = 'Found'
            WHERE id = ?
            """,
            (claim["item_id"],),
        )

    connection.commit()
    connection.close()

    # Notification for the claimant
    messages = {
        "Under Verification": "Your claim is now under verification.",
        "Approved": "Your claim has been approved.",
        "Rejected": "Your claim was rejected. Please check the admin note.",
        "Ready for Collection": "Your item is ready for physical collection.",
        "Returned": "Your item has been marked as returned.",
    }

    add_notification(
        claim["claimant_id"],
        f"Claim update: {new_status}",
        messages[new_status],
    )

    flash("Claim status updated successfully.", "success")

    # Return to the same admin view
    if current_view:
        return redirect(
            url_for(
                "admin_claims",
                view=current_view
            )
        )

    return redirect(url_for("admin_claims"))

@app.route("/admin/users")
def admin_users():
    if not admin_required():
        return redirect(url_for("login"))

    role = request.args.get("role", "").strip().lower()

    user = current_user()
    can_create_hod = bool(user and user["role"] == "admin")

    connection = get_db_connection()
    if role == "hod":
        users = connection.execute(
            """
            SELECT id, fullname, roll_no, department, email, role, created_at
            FROM users
            WHERE role = 'hod'
            ORDER BY created_at DESC
            """
        ).fetchall()
    else:
        users = connection.execute(
            """
            SELECT id, fullname, roll_no, department, email, role, created_at
            FROM users
            WHERE role = 'student'
            ORDER BY created_at DESC
            """
        ).fetchall()

    connection.close()

    return render_template(
    "admin_users.html",
    users=users,
    role=role,
    can_create_hod=can_create_hod
)
    
@app.route("/admin/users/create", methods=["POST"])
def create_staff_account():
    user = current_user()

    if not user or user["role"] != "admin":
        flash("Only Admin can create HOD accounts.", "danger")
        return redirect(url_for("admin_users", role="hod"))

    fullname = request.form.get("fullname", "").strip()
    roll_no = request.form.get("roll_no", "").strip()
    department = request.form.get("department", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()

    # Basic validation
    if not fullname or not roll_no or not department or not email or not password:
        flash("Please fill in all staff account fields.", "danger")
        return redirect(url_for("admin_users"))

    if len(password) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect(url_for("admin_users"))

    connection = get_db_connection()

    # Check whether email or staff ID already exists
    existing_user = connection.execute(
        """
        SELECT id
        FROM users
        WHERE email = ? OR roll_no = ?
        LIMIT 1
        """,
        (email, roll_no),
    ).fetchone()

    if existing_user:
        connection.close()
        flash(
            "An account with this email or Staff ID already exists.",
            "danger"
        )
        return redirect(url_for("admin_users"))

    connection.execute(
        """
        INSERT INTO users
        (
            fullname,
            roll_no,
            department,
            email,
            password,
            role,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fullname,
            roll_no,
            department,
            email,
            generate_password_hash(password),
            "hod",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )

    connection.commit()
    connection.close()

    flash(
        f"HOD account created successfully for {fullname}.",
        "success"
    )

    return redirect(url_for("admin_users"))


@app.route("/private-verification/<filename>")
def private_verification(filename):
    if not admin_required():
        return redirect(url_for("login"))
    return send_from_directory(PRIVATE_UPLOAD_FOLDER, filename)


@app.route("/mark-notification-read/<int:notification_id>", methods=["POST"])
def mark_notification_read(notification_id):
    if not login_required():
        return redirect(url_for("login"))

    connection = get_db_connection()
    connection.execute(
        """
        UPDATE notifications
        SET is_read = 1
        WHERE id = ? AND user_id = ?
        """,
        (notification_id, session["user_id"]),
    )
    connection.commit()
    connection.close()
    return redirect(url_for("notifications"))


@app.context_processor
def notification_count():
    if "user_id" not in session:
        return {"unread_count": 0}

    connection = get_db_connection()
    count = connection.execute(
        """
        SELECT COUNT(*) AS c FROM notifications
        WHERE user_id = ? AND is_read = 0
        """,
        (session["user_id"],),
    ).fetchone()["c"]
    connection.close()
    return {"unread_count": count}

create_tables()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
