import os
import threading
import csv
from datetime import datetime, date
from io import StringIO

from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify, flash
from mysql.connector import connect
from werkzeug.utils import secure_filename
import bcrypt
import face_recognition

from config import (
    DB_CONFIG,
    SECRET_KEY,
    LOCAL_FACE_DIR,
    UNKNOWN_DIR,
    STUDENT_IMAGE_DIR,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
)
from face_utils import face_cache

os.makedirs(LOCAL_FACE_DIR, exist_ok=True)
os.makedirs(UNKNOWN_DIR, exist_ok=True)
os.makedirs(STUDENT_IMAGE_DIR, exist_ok=True)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = SECRET_KEY


def get_db_conn():
    return connect(**DB_CONFIG)


def log_action(action_type, actor, details):
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO system_log (action_type, actor, details) VALUES (%s,%s,%s)",
            (action_type, actor, details),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("log_action error:", e)


def is_admin():
    return session.get("role") == "admin"


def is_faculty():
    return session.get("role") == "faculty"


def current_actor():
    return session.get("username") or session.get("faculty_code") or "guest"


def ensure_admin():
    if not is_admin():
        return redirect(url_for("login"))
    return None


def ensure_authenticated():
    if not (is_admin() or is_faculty()):
        return redirect(url_for("login"))
    return None


def save_profile_photo(file_obj, prefix):
    if not file_obj or not getattr(file_obj, "filename", ""):
        return None
    filename = secure_filename(file_obj.filename)
    ext = os.path.splitext(filename)[1] or ".jpg"
    abs_dir = os.path.join(app.root_path, STUDENT_IMAGE_DIR)
    os.makedirs(abs_dir, exist_ok=True)
    final_name = f"{prefix}_{int(datetime.now().timestamp())}{ext}"
    abs_path = os.path.join(abs_dir, final_name)
    file_obj.save(abs_path)
    rel_path = os.path.relpath(abs_path, os.path.join(app.root_path, "static"))
    return rel_path.replace("\\", "/")


def delete_profile_photo(rel_path):
    if not rel_path:
        return
    abs_path = os.path.join(app.root_path, "static", rel_path)
    if os.path.exists(abs_path):
        try:
            os.remove(abs_path)
        except OSError:
            pass


def get_departments():
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT department_id, name, code, chair_name, contact_email FROM department ORDER BY name"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_sections_for_user(faculty_id=None):
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    if is_admin() or not faculty_id:
        cur.execute(
            """
            SELECT s.section_id, c.course_code, c.course_name, s.section_no,
                   s.semester, s.academic_year,
                   COALESCE(f.full_name,'Unassigned') AS faculty_name
            FROM section s
            JOIN course c ON s.course_id = c.course_id
            LEFT JOIN faculty f ON s.faculty_id = f.faculty_id
            ORDER BY c.course_code, s.section_no
            """
        )
    else:
        cur.execute(
            """
            SELECT s.section_id, c.course_code, c.course_name, s.section_no,
                   s.semester, s.academic_year,
                   COALESCE(f.full_name,'Unassigned') AS faculty_name
            FROM section s
            JOIN course c ON s.course_id = c.course_id
            LEFT JOIN faculty f ON s.faculty_id = f.faculty_id
            WHERE s.faculty_id = %s OR EXISTS (
                SELECT 1 FROM faculty_assignment fa
                WHERE fa.section_id = s.section_id AND fa.faculty_id = %s
            )
            ORDER BY c.course_code, s.section_no
            """,
            (faculty_id, faculty_id),
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role", "admin")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if role == "admin":
            if (
                username.lower() == ADMIN_USERNAME.lower()
                and password == ADMIN_PASSWORD
            ):
                session.clear()
                session["role"] = "admin"
                session["username"] = ADMIN_USERNAME
                log_action("admin_login", ADMIN_USERNAME, "Admin logged in")
                return redirect(url_for("dashboard"))
            flash("Invalid admin credentials", "danger")
        else:
            conn = get_db_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM faculty WHERE faculty_code=%s AND status='active'",
                (username,),
            )
            faculty = cur.fetchone()
            cur.close()
            conn.close()
            if faculty and bcrypt.checkpw(
                password.encode(), faculty["password_hash"].encode()
            ):
                session.clear()
                session["role"] = "faculty"
                session["faculty_id"] = faculty["faculty_id"]
                session["faculty_code"] = faculty["faculty_code"]
                session["username"] = faculty["full_name"]
                log_action(
                    "faculty_login", faculty["faculty_code"], "Faculty logged in"
                )
                return redirect(url_for("faculty_dashboard"))
            flash("Invalid faculty credentials", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    actor = current_actor()
    session.clear()
    log_action("logout", actor, "Session closed")
    return redirect(url_for("login"))


@app.route("/")
def index():
    if is_admin():
        return redirect(url_for("dashboard"))
    if is_faculty():
        return redirect(url_for("faculty_dashboard"))
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    guard = ensure_admin()
    if guard:
        return guard
    stats = {
        "students": 0,
        "courses": 0,
        "sections": 0,
        "faculty": 0,
        "today_sessions": 0,
    }
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM student")
        stats["students"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM course")
        stats["courses"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM section")
        stats["sections"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM faculty")
        stats["faculty"] = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM attendance_session WHERE DATE(session_started_at)=CURDATE()"
        )
        stats["today_sessions"] = cur.fetchone()[0]
        cur.close()
        conn.close()
    except Exception as exc:
        print("dashboard stats error:", exc)
    sections = get_sections_for_user()
    return render_template("dashboard.html", stats=stats, sections=sections)


@app.route("/faculty/dashboard")
def faculty_dashboard():
    if not is_faculty():
        return redirect(url_for("login"))
    faculty_id = session.get("faculty_id")
    sections = get_sections_for_user(faculty_id)
    summary = {"sections": len(sections), "today_present": 0}
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT COUNT(*) FROM attendance_record ar
            JOIN attendance_session s ON ar.session_id = s.session_id
            WHERE DATE(ar.attendance_date)=CURDATE() AND s.faculty_id=%s AND ar.status='present'
            """,
            (faculty_id,),
        )
        summary["today_present"] = cur.fetchone()[0]
        cur.close()
        conn.close()
    except Exception as exc:
        print("faculty dashboard error:", exc)
    return render_template(
        "faculty_dashboard.html", summary=summary, sections=sections
    )


# ------------------ Departments ------------------
@app.route("/departments")
def departments():
    guard = ensure_admin()
    if guard:
        return guard
    departments = get_departments()
    return render_template("departments.html", departments=departments)


@app.route("/department/add", methods=["GET", "POST"])
def department_add():
    guard = ensure_admin()
    if guard:
        return guard
    if request.method == "POST":
        code = request.form["code"]
        name = request.form["name"]
        chair = request.form.get("chair_name")
        email = request.form.get("contact_email")
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO department (code, name, chair_name, contact_email) VALUES (%s,%s,%s,%s)",
            (code, name, chair, email),
        )
        conn.commit()
        cur.close()
        conn.close()
        log_action("department_create", current_actor(), f"dept={code}")
        return redirect(url_for("departments"))
    return render_template("department_add.html")


@app.route("/department/<int:dept_id>/edit", methods=["GET", "POST"])
def department_edit(dept_id):
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM department WHERE department_id=%s", (dept_id,))
    department = cur.fetchone()
    if not department:
        cur.close()
        conn.close()
        flash("Department not found", "danger")
        return redirect(url_for("departments"))
    if request.method == "POST":
        code = request.form["code"]
        name = request.form["name"]
        chair = request.form.get("chair_name")
        email = request.form.get("contact_email")
        cur.execute(
            "UPDATE department SET code=%s, name=%s, chair_name=%s, contact_email=%s WHERE department_id=%s",
            (code, name, chair, email, dept_id),
        )
        conn.commit()
        cur.close()
        conn.close()
        log_action("department_update", current_actor(), f"dept_id={dept_id}")
        return redirect(url_for("departments"))
    cur.close()
    conn.close()
    return render_template("department_edit.html", department=department)


# ------------------ Faculty Management ------------------
@app.route("/faculty")
def faculty_list():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT f.*, d.name AS department_name
        FROM faculty f
        LEFT JOIN department d ON f.department_id = d.department_id
        ORDER BY f.full_name
        """
    )
    faculty = cur.fetchall()
    cur.close()
    conn.close()
    departments = get_departments()
    return render_template(
        "faculty.html", faculty=faculty, departments=departments
    )


@app.route("/faculty/add", methods=["GET", "POST"])
def faculty_add():
    guard = ensure_admin()
    if guard:
        return guard
    departments = get_departments()
    if request.method == "POST":
        code = request.form["faculty_code"]
        full_name = request.form["full_name"]
        email = request.form["email"]
        phone = request.form.get("phone")
        dept_id = request.form.get("department_id") or None
        password = request.form["password"]
        avatar = save_profile_photo(request.files.get("avatar"), f"fac_{code}")
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO faculty (faculty_code, full_name, email, phone, department_id, password_hash, avatar_path)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (code, full_name, email, phone, dept_id, hashed, avatar),
        )
        conn.commit()
        cur.close()
        conn.close()
        log_action("faculty_create", current_actor(), f"faculty={code}")
        return redirect(url_for("faculty_list"))
    return render_template("faculty_add.html", departments=departments)


@app.route("/faculty/<int:faculty_id>/edit", methods=["GET", "POST"])
def faculty_edit(faculty_id):
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM faculty WHERE faculty_id=%s", (faculty_id,))
    faculty = cur.fetchone()
    if not faculty:
        cur.close()
        conn.close()
        flash("Faculty member not found", "danger")
        return redirect(url_for("faculty_list"))
    if request.method == "POST":
        code = request.form["faculty_code"]
        full_name = request.form["full_name"]
        email = request.form["email"]
        phone = request.form.get("phone")
        dept_id = request.form.get("department_id") or None
        password = request.form.get("password")
        avatar_file = request.files.get("avatar")
        avatar = faculty["avatar_path"]
        if avatar_file and avatar_file.filename:
            delete_profile_photo(avatar)
            avatar = save_profile_photo(avatar_file, f"fac_{code}")
        cur.execute(
            """
            UPDATE faculty SET faculty_code=%s, full_name=%s, email=%s,
                   phone=%s, department_id=%s, avatar_path=%s
            WHERE faculty_id=%s
            """,
            (code, full_name, email, phone, dept_id, avatar, faculty_id),
        )
        if password:
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            cur.execute(
                "UPDATE faculty SET password_hash=%s WHERE faculty_id=%s",
                (hashed, faculty_id),
            )
        conn.commit()
        cur.close()
        conn.close()
        log_action("faculty_update", current_actor(), f"faculty_id={faculty_id}")
        return redirect(url_for("faculty_list"))
    cur.close()
    conn.close()
    departments = get_departments()
    return render_template(
        "faculty_edit.html", faculty=faculty, departments=departments
    )


# ------------------ Students ------------------
@app.route("/students")
def students():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT s.*, d.name AS department_name
        FROM student s
        LEFT JOIN department d ON s.department_id = d.department_id
        ORDER BY s.created_at DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("students.html", students=rows)


@app.route("/student/add", methods=["GET", "POST"])
def student_add():
    guard = ensure_admin()
    if guard:
        return guard
    departments = get_departments()
    if request.method == "POST":
        roll = request.form["roll"]
        name = request.form["name"]
        dept_id = request.form.get("department_id") or None
        batch = request.form.get("batch")
        email = request.form.get("email")
        phone = request.form.get("phone")
        photo = save_profile_photo(request.files.get("photo"), f"stu_{roll}")
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO student (roll, name, department_id, batch, email, phone, photo_path)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (roll, name, dept_id, batch, email, phone, photo),
        )
        conn.commit()
        cur.close()
        conn.close()
        log_action("student_create", current_actor(), f"roll={roll}")
        return redirect(url_for("students"))
    return render_template("student_add.html", departments=departments)


@app.route("/student/<int:sid>/edit", methods=["GET", "POST"])
def student_edit(sid):
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM student WHERE student_id=%s", (sid,))
    student = cur.fetchone()
    if not student:
        cur.close()
        conn.close()
        flash("Student not found", "danger")
        return redirect(url_for("students"))
    departments = get_departments()
    if request.method == "POST":
        roll = request.form["roll"]
        name = request.form["name"]
        dept_id = request.form.get("department_id") or None
        batch = request.form.get("batch")
        email = request.form.get("email")
        phone = request.form.get("phone")
        photo_file = request.files.get("photo")
        photo = student["photo_path"]
        if photo_file and photo_file.filename:
            delete_profile_photo(photo)
            photo = save_profile_photo(photo_file, f"stu_{roll}")
        cur.execute(
            """
            UPDATE student SET roll=%s, name=%s, department_id=%s, batch=%s,
                   email=%s, phone=%s, photo_path=%s
            WHERE student_id=%s
            """,
            (roll, name, dept_id, batch, email, phone, photo, sid),
        )
        conn.commit()
        cur.close()
        conn.close()
        log_action("student_update", current_actor(), f"student_id={sid}")
        return redirect(url_for("students"))
    cur.close()
    conn.close()
    return render_template(
        "student_edit.html", student=student, departments=departments
    )


@app.route("/student/<int:sid>/delete", methods=["POST"])
def student_delete(sid):
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("SELECT photo_path FROM student WHERE student_id=%s", (sid,))
    photo = cur.fetchone()
    cur.execute("DELETE FROM student WHERE student_id=%s", (sid,))
    conn.commit()
    cur.close()
    conn.close()
    if photo and photo[0]:
        delete_profile_photo(photo[0])
    log_action("student_delete", current_actor(), f"student_id={sid}")
    return redirect(url_for("students"))


# ------------------ Courses ------------------
@app.route("/courses")
def courses():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT c.*, d.name AS department_name
        FROM course c
        LEFT JOIN department d ON c.department_id = d.department_id
        ORDER BY c.course_code
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("courses.html", courses=rows)


@app.route("/course/add", methods=["GET", "POST"])
def course_add():
    guard = ensure_admin()
    if guard:
        return guard
    departments = get_departments()
    if request.method == "POST":
        code = request.form["course_code"]
        name = request.form["course_name"]
        dept_id = request.form.get("department_id") or None
        credit = request.form.get("credit", 3.0)
        description = request.form.get("description")
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO course (course_code, course_name, department_id, credit, description)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (code, name, dept_id, credit, description),
        )
        conn.commit()
        cur.close()
        conn.close()
        log_action("course_create", current_actor(), f"course={code}")
        return redirect(url_for("courses"))
    return render_template("course_add.html", departments=departments)


# ------------------ Sections ------------------
@app.route("/sections")
def sections():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT s.section_id, s.section_no, s.semester, s.academic_year, s.schedule_info,
               c.course_code, c.course_name, f.full_name AS faculty_name
        FROM section s
        JOIN course c ON s.course_id = c.course_id
        LEFT JOIN faculty f ON s.faculty_id = f.faculty_id
        ORDER BY s.section_id DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("sections.html", sections=rows)


@app.route("/section/add", methods=["GET", "POST"])
def section_add():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT course_id, course_code, course_name FROM course ORDER BY course_code")
    courses = cur.fetchall()
    cur.execute("SELECT faculty_id, full_name FROM faculty WHERE status='active' ORDER BY full_name")
    faculties = cur.fetchall()
    cur.close()
    conn.close()
    if request.method == "POST":
        course_id = request.form["course_id"]
        section_no = request.form.get("section_no")
        semester = request.form.get("semester")
        academic_year = request.form.get("academic_year")
        faculty_id = request.form.get("faculty_id") or None
        schedule_info = request.form.get("schedule_info")
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO section (course_id, section_no, semester, academic_year, faculty_id, schedule_info)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (course_id, section_no, semester, academic_year, faculty_id, schedule_info),
        )
        conn.commit()
        cur.close()
        conn.close()
        log_action("section_create", current_actor(), f"course_id={course_id}")
        return redirect(url_for("sections"))
    return render_template("section_add.html", courses=courses, faculties=faculties)


# ------------------ Enrollments ------------------
@app.route("/enrollments")
def enrollments():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT e.enrollment_id, s.student_id, s.name, s.roll,
               sec.section_id, sec.section_no, c.course_code, f.full_name AS faculty_name
                   FROM enrollment e
                   JOIN student s ON e.student_id = s.student_id
                   JOIN section sec ON e.section_id = sec.section_id
                   JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN faculty f ON sec.faculty_id = f.faculty_id
        ORDER BY e.enrolled_on DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("enrollments.html", enrollments=rows)


@app.route("/enrollment/add", methods=["GET", "POST"])
def enrollment_add():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT student_id, name, roll FROM student ORDER BY name")
    students = cur.fetchall()
    cur.execute(
        """
        SELECT sec.section_id, sec.section_no, c.course_code, c.course_name
        FROM section sec
        JOIN course c ON sec.course_id = c.course_id
        ORDER BY c.course_code
        """
    )
    sections = cur.fetchall()
    cur.close()
    conn.close()
    if request.method == "POST":
        student_id = request.form["student_id"]
        section_id = request.form["section_id"]
        conn = get_db_conn()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO enrollment (student_id, section_id) VALUES (%s,%s)",
                (student_id, section_id),
            )
            conn.commit()
            log_action(
                "enrollment_create",
                current_actor(),
                f"student_id={student_id}, section_id={section_id}",
            )
        except Exception as exc:
            flash(f"Enrollment failed: {exc}", "danger")
        cur.close()
        conn.close()
        return redirect(url_for("enrollments"))
    return render_template(
        "enrollment_add.html", students=students, sections=sections
    )


# ------------------ Face Capture ------------------
@app.route("/student/<int:sid>/capture", methods=["GET", "POST"])
def capture(sid):
    guard = ensure_admin()
    if guard:
        return guard
    if request.method == "POST":
        file_obj = request.files.get("file")
        if not file_obj or not file_obj.filename:
            flash("No file sent", "danger")
            return redirect(request.url)
        filename = secure_filename(
            f"{sid}_{int(datetime.now().timestamp())}.jpg"
        )
        local_path = os.path.join(LOCAL_FACE_DIR, filename)
        file_obj.save(local_path)
        conn = get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO face_data (student_id, storage_path, capture_source) VALUES (%s,%s,%s)",
            (sid, local_path, "webcam"),
        )
        conn.commit()
        cur.close()
        conn.close()
        threading.Thread(target=face_cache.load_from_db).start()
        flash("Face captured and saved locally.", "success")
        return redirect(url_for("students"))
    return render_template("capture.html", sid=sid)


# ------------------ Live Attendance ------------------
@app.route("/attendance/live")
def live_attendance():
    guard = ensure_authenticated()
    if guard:
        return guard
    faculty_id = session.get("faculty_id") if is_faculty() else None
    sections = get_sections_for_user(faculty_id)
    return render_template("attendance_live.html", sections=sections)


@app.route("/api/attendance_sessions", methods=["POST"])
def api_create_session():
    if not (is_admin() or is_faculty()):
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(force=True)
    section_id = payload.get("section_id")
    mode = payload.get("mode", "smart")
    device_name = payload.get("device_name")
    if not section_id:
        return jsonify({"error": "section_id required"}), 400
    faculty_id = (
        session.get("faculty_id") if is_faculty() else payload.get("faculty_id")
    )
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO attendance_session (section_id, faculty_id, mode, device_name)
        VALUES (%s,%s,%s,%s)
        """,
        (section_id, faculty_id, mode, device_name),
    )
    session_id = cur.lastrowid
    conn.commit()
    cur.close()
    conn.close()
    log_action(
        "attendance_session_start",
        current_actor(),
        f"section_id={section_id}, session_id={session_id}",
    )
    return jsonify({"session_id": session_id, "status": "open"})


@app.route("/api/attendance_sessions/<int:session_id>/close", methods=["POST"])
def api_close_session(session_id):
    if not (is_admin() or is_faculty()):
        return jsonify({"error": "unauthorized"}), 401
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE attendance_session SET status='closed', session_closed_at=NOW() WHERE session_id=%s",
        (session_id,),
    )
    conn.commit()
    cur.close()
    conn.close()
    log_action(
        "attendance_session_close", current_actor(), f"session_id={session_id}"
    )
    return jsonify({"status": "closed"})


@app.route("/recognize_frame", methods=["POST"])
def recognize_frame():
    if not (is_admin() or is_faculty()):
        return jsonify({"error": "unauthorized"}), 401
    file_obj = request.files.get("frame")
    section_id = request.form.get("section_id", type=int)
    session_id = request.form.get("session_id", type=int)
    if not file_obj or not section_id:
        return jsonify({"error": "Missing frame or section"}), 400
    tmp_name = f"tmp_{int(datetime.now().timestamp())}.jpg"
    tmp_path = os.path.join(UNKNOWN_DIR, tmp_name)
    file_obj.save(tmp_path)
    faces_payload = []
    recognized_count = 0
    unknown_boxes = []
    try:
        img = face_recognition.load_image_file(tmp_path)
        locations = face_recognition.face_locations(img)
        encodings = face_recognition.face_encodings(img, locations)
        if not encodings:
            os.remove(tmp_path)
            return jsonify({"status": "no_face"})
        conn = get_db_conn()
        cur = conn.cursor(dictionary=True)
        for loc, encoding in zip(locations, encodings):
            match = face_cache.find_match(encoding)
            top, right, bottom, left = loc
            box = {
                "top": int(top),
                "left": int(left),
                "width": int(right - left),
                "height": int(bottom - top),
            }
            if match:
                student_id, distance = match
                cur.execute(
                    """
                    SELECT s.name, e.enrollment_id
                    FROM student s
                    LEFT JOIN enrollment e ON s.student_id = e.student_id AND e.section_id=%s
                    WHERE s.student_id=%s
                    """,
                    (section_id, student_id),
                )
                info = cur.fetchone()
                if info and info["enrollment_id"]:
                    cur.execute(
                        """
                        INSERT INTO attendance_record (
                            enrollment_id, session_id, attendance_date, status, time_in,
                            marked_by_faculty, mode
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                            status=VALUES(status),
                            time_in=VALUES(time_in),
                            session_id=VALUES(session_id),
                            mode=VALUES(mode)
                        """,
                        (
                            info["enrollment_id"],
                            session_id,
                            date.today(),
                            "present",
                            datetime.now().time(),
                            session.get("faculty_id"),
                            "smart",
                        ),
                    )
                    conn.commit()
                    faces_payload.append(
                        {
                            "type": "recognized",
                            "student_id": student_id,
                            "name": info["name"],
                            "distance": float(distance),
                            "box": box,
                        }
                    )
                    recognized_count += 1
                else:
                    faces_payload.append(
                        {
                            "type": "unassigned",
                            "box": box,
                            "name": "Not enrolled",
                        }
                    )
            else:
                unknown_boxes.append(box)
        if unknown_boxes:
            fname = f"unknown_{int(datetime.now().timestamp())}.jpg"
            storage_path = os.path.join(UNKNOWN_DIR, fname)
            os.rename(tmp_path, storage_path)
            cur.execute(
                "INSERT INTO unknown_faces (storage_path, session_id, tag) VALUES (%s,%s,%s)",
                (storage_path, session_id, "frame"),
            )
            conn.commit()
        else:
            os.remove(tmp_path)
        cur.close()
        conn.close()
        for box in unknown_boxes:
            faces_payload.append(
                {"type": "unknown", "box": box, "name": "Unknown face"}
            )
        frame_meta = {
            "width": img.shape[1],
            "height": img.shape[0],
        }
        log_action(
            "recognition",
            current_actor(),
            f"section={section_id}, recognized={recognized_count}, unknown={len(unknown_boxes)}",
        )
        return jsonify(
            {
                "status": "processed",
                "faces": faces_payload,
                "recognized": recognized_count,
                "unknown": len(unknown_boxes),
                "frame": frame_meta,
            }
        )
    except Exception as exc:
        print("recognition error:", exc)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return jsonify({"error": "server_error"}), 500


@app.route("/attendance/manual", methods=["POST"])
def manual_attendance():
    guard = ensure_authenticated()
    if guard:
        return guard
    section_id = request.form.get("section_id", type=int)
    student_id = request.form.get("student_id", type=int)
    status = request.form.get("status", "present")
    note = request.form.get("note")
    session_id = request.form.get("session_id", type=int)
    if not (section_id and student_id):
        flash("Section and student are required", "danger")
        return redirect(url_for("live_attendance"))
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT enrollment_id FROM enrollment WHERE section_id=%s AND student_id=%s",
        (section_id, student_id),
    )
    enrollment = cur.fetchone()
    if not enrollment:
        cur.close()
        conn.close()
        flash("Student is not enrolled in this section", "warning")
        return redirect(url_for("live_attendance"))
    cur.execute(
        """
        INSERT INTO attendance_record (
            enrollment_id, session_id, attendance_date, status, time_in, marked_by_faculty, mode, note
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            status=VALUES(status),
            time_in=VALUES(time_in),
            marked_by_faculty=VALUES(marked_by_faculty),
            mode=VALUES(mode),
            note=VALUES(note)
        """,
        (
            enrollment["enrollment_id"],
            session_id,
            date.today(),
            status,
            datetime.now().time(),
            session.get("faculty_id"),
            "manual",
            note,
        ),
    )
    conn.commit()
    cur.close()
    conn.close()
    log_action(
        "attendance_manual",
        current_actor(),
        f"student_id={student_id}, section_id={section_id}, status={status}",
    )
    flash("Attendance updated manually", "success")
    return redirect(url_for("live_attendance"))


@app.route("/api/sections/<int:section_id>/students")
def api_section_students(section_id):
    if not (is_admin() or is_faculty()):
        return jsonify({"error": "unauthorized"}), 401
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT s.student_id, s.name, s.roll
        FROM enrollment e
        JOIN student s ON e.student_id = s.student_id
        WHERE e.section_id=%s
        ORDER BY s.name
        """,
        (section_id,),
    )
    students = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(students)


# ------------------ Attendance Views ------------------
@app.route("/attendance")
def attendance():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT ar.attendance_id, ar.attendance_date, ar.status, ar.time_in, ar.mode,
               s.name, s.roll, c.course_code, sec.section_no,
               f.full_name AS faculty_name
                   FROM attendance_record ar
                   JOIN enrollment e ON ar.enrollment_id = e.enrollment_id
                   JOIN student s ON e.student_id = s.student_id
                   JOIN section sec ON e.section_id = sec.section_id
                   JOIN course c ON sec.course_id = c.course_id
        LEFT JOIN faculty f ON ar.marked_by_faculty = f.faculty_id
        ORDER BY ar.attendance_date DESC, ar.time_in DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("attendance.html", records=rows)


@app.route("/attendance/export")
def attendance_export():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ar.attendance_id, ar.attendance_date, ar.status, ar.time_in, ar.mode,
                          s.student_id, s.name, s.roll, c.course_code, sec.section_no
                   FROM attendance_record ar
                   JOIN enrollment e ON ar.enrollment_id = e.enrollment_id
                   JOIN student s ON e.student_id = s.student_id
                   JOIN section sec ON e.section_id = sec.section_id
                   JOIN course c ON sec.course_id = c.course_id
        ORDER BY ar.attendance_date DESC
        """
    )
    rows = cur.fetchall()
    headers = [col[0] for col in cur.description]
    cur.close()
    conn.close()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=attendance.csv"},
    )


# ------------------ Unknown Faces ------------------
@app.route("/unknowns")
def unknowns():
    guard = ensure_admin()
    if guard:
        return guard
    conn = get_db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT u.*, sec.section_no, c.course_code
        FROM unknown_faces u
        LEFT JOIN attendance_session s ON u.session_id = s.session_id
        LEFT JOIN section sec ON s.section_id = sec.section_id
        LEFT JOIN course c ON sec.course_id = c.course_id
        ORDER BY u.capture_time DESC
        """
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("unknowns.html", unknowns=rows)


@app.route("/refresh_faces")
def refresh_faces():
    guard = ensure_admin()
    if guard:
        return guard
    threading.Thread(target=face_cache.load_from_db).start()
    flash("Face cache refresh started", "info")
    return redirect(url_for("students"))


if __name__ == "__main__":
    try:
        face_cache.load_from_db()
    except Exception as exc:
        print("initial face load failed:", exc)
    app.run(host="127.0.0.1", port=5000, debug=True)