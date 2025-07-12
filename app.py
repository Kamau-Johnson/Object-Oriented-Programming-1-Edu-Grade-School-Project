from flask import Flask, render_template, request, redirect, flash, url_for, session, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json
import datetime

app = Flask(__name__)
app.secret_key = 'your_strong_random_secret_key_here_CHANGE_THIS!'

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "edugrade_db"
}

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'student_id' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'teacher_id' not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for('teacher_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/student_login', methods=['POST'])
def student_login():
    if request.method == 'POST':
        admission_number = request.form.get('admission_number')
        password = request.form.get('password')
        if not admission_number or not password:
            flash("Admission number and password are required.", "error")
            return redirect(url_for('home'))
        db_conn = get_db_connection()
        cursor = db_conn.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute("SELECT * FROM students WHERE admission_number = %s", (admission_number,))
            student = cursor.fetchone()
            if student and check_password_hash(student['password'], password):
                session['student_id'] = student['id']
                session['student_name'] = student['full_name']
                flash("Successful! Redirecting...", "success")
                return render_template('home.html', login_redirect_url=url_for('student_dashboard'))
            else:
                flash("Invalid admission number or password.", "error")
        finally:
            cursor.close()
            db_conn.close()
    return redirect(url_for('home'))

@app.route('/student_dashboard')
@student_required
def student_dashboard():
    num_subjects = 5 
    return render_template('student_dashboard.html', 
                           student_name=session.get('student_name', 'Student'),
                           num_subjects=num_subjects)

@app.route('/student_logout')
def student_logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    flash("Student Logged Out.", "info")
    return redirect(url_for('home'))

@app.route('/student/my_grades')
@student_required
def get_my_grades():
    student_id = session['student_id']
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        query = "SELECT term, overall_average, overall_grade, overall_remark, marks_data FROM marks WHERE student_id = %s ORDER BY term ASC"
        cursor.execute(query, (student_id,))
        grades = cursor.fetchall()
        for grade in grades:
            if grade['marks_data']:
                try: grade['marks_data'] = json.loads(grade['marks_data'])
                except (json.JSONDecodeError, TypeError): grade['marks_data'] = {}
        return jsonify(success=True, grades=grades)
    except mysql.connector.Error as err:
        return jsonify(success=False, message=f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/student/my_report_card')
@student_required
def get_my_report_card():
    student_id = session['student_id']
    term = request.args.get('term', 'Term 1')
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        sql_report_query = "SELECT m.term, m.overall_average, m.overall_grade, m.overall_remark, m.marks_data, s.full_name, s.admission_number, s.grade, c.name AS class_name, t.full_name AS teacher_name FROM marks m JOIN students s ON m.student_id = s.id LEFT JOIN teachers t ON m.teacher_id = t.id LEFT JOIN classes c ON s.class_id = c.id WHERE m.student_id = %s AND m.term = %s"
        cursor.execute(sql_report_query, (student_id, term))
        report_data = cursor.fetchone()
        if not report_data:
            return jsonify(success=False, message=f"No marks have been recorded for you in {term} yet."), 404
        report_data['report_generated_on'] = datetime.datetime.now().strftime('%B %d, %Y')
        try: report_data['marks_details'] = json.loads(report_data['marks_data'])
        except (json.JSONDecodeError, TypeError): report_data['marks_details'] = {}
        del report_data['marks_data']
        return jsonify(success=True, data=report_data)
    except mysql.connector.Error as err:
        return jsonify(success=False, message=f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    if 'teacher_id' in session:
        return redirect(url_for('teacher_dashboard'))
    if request.method == 'POST':
        access_code = request.form.get('access_code')
        password = request.form.get('password')
        db_conn = get_db_connection()
        cursor = db_conn.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute("SELECT * FROM teachers WHERE access_code = %s", (access_code,))
            teacher = cursor.fetchone()
            if teacher and check_password_hash(teacher['password'], password):
                session['teacher_id'] = teacher['id']
                session['teacher_name'] = teacher['full_name']
                flash("Successful! Redirecting...", "success")
                return render_template('teacher_login.html', login_redirect_url=url_for('teacher_dashboard'))
            else:
                flash("Invalid access code or password.", "error")
        finally:
            cursor.close()
            db_conn.close()
    return render_template('teacher_login.html')

@app.route('/teacher_dashboard')
@teacher_required
def teacher_dashboard():
    teacher_name = session.get('teacher_name', 'Teacher')
    total_students = 0
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM students")
        total_students_result = cursor.fetchone()
        if total_students_result:
            total_students = total_students_result[0]
    except mysql.connector.Error as err:
        print(f"Error fetching teacher dashboard counts: {err}")
    finally:
        cursor.close()
        db_conn.close()
    return render_template('teacher_dashboard.html', 
                           teacher_name=teacher_name, 
                           total_students=total_students)

@app.route('/teacher/dashboard_data')
@teacher_required
def teacher_dashboard_data():
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM students")
        total_students = cursor.fetchone()[0] or 0
        return jsonify(success=True, total_students=total_students)
    except mysql.connector.Error as err:
        return jsonify(success=False, message=f"Database Error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher/my_classes')
@teacher_required
def get_my_classes():
    teacher_id = session['teacher_id']
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        query = "SELECT c.id, c.name, c.grade, t.subject AS subject_taught, COUNT(s.id) AS student_count FROM classes c JOIN teachers t ON c.teacher_id = t.id LEFT JOIN students s ON c.id = s.class_id WHERE c.teacher_id = %s GROUP BY c.id, c.name, c.grade, t.subject ORDER BY c.grade, c.name"
        cursor.execute(query, (teacher_id,))
        classes = cursor.fetchall()
        return jsonify(success=True, classes=classes)
    except mysql.connector.Error as err:
        return jsonify(success=False, message=f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher/get_my_students')
@teacher_required
def get_teacher_my_students():
    teacher_id = session['teacher_id']
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        query = "SELECT s.id, s.full_name, s.admission_number, s.grade, c.name as class_name FROM students s JOIN classes c ON s.class_id = c.id WHERE c.teacher_id = %s ORDER BY s.full_name ASC"
        cursor.execute(query, (teacher_id,))
        students = cursor.fetchall()
        return jsonify(success=True, students=students)
    except mysql.connector.Error as err:
        return jsonify(success=False, message=f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher/add_student', methods=['POST'])
@teacher_required
def teacher_add_student():
    teacher_id = session['teacher_id']
    class_id = request.form.get('classId')
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("SELECT id FROM classes WHERE id = %s AND teacher_id = %s", (class_id, teacher_id))
        if cursor.fetchone() is None: return jsonify(success=False, message="You are not authorized to add students to this class."), 403
        hashed_password = generate_password_hash(request.form.get('password'))
        sql = "INSERT INTO students (full_name, admission_number, age, grade, class_id, password) VALUES (%s, %s, %s, %s, %s, %s)"
        values = (request.form.get('fullName'), request.form.get('admissionNumber'), request.form.get('age'), request.form.get('grade'), class_id, hashed_password)
        cursor.execute(sql, values)
        db_conn.commit()
        return jsonify(success=True, message="Student added successfully!")
    except mysql.connector.Error as err:
        return jsonify(success=False, message="An error occurred. The admission number may already exist." if err.errno == 1062 else f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher/delete_student/<int:student_id>', methods=['DELETE'])
@teacher_required
def teacher_delete_student(student_id):
    teacher_id = session['teacher_id']
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("SELECT s.id FROM students s JOIN classes c ON s.class_id = c.id WHERE s.id = %s AND c.teacher_id = %s", (student_id, teacher_id))
        if cursor.fetchone() is None: return jsonify(success=False, message="Authorization Error"), 403
        cursor.execute("DELETE FROM marks WHERE student_id = %s", (student_id,))
        cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
        db_conn.commit()
        return jsonify(success=True, message="Student and their marks deleted successfully.")
    except mysql.connector.Error as err:
        db_conn.rollback()
        return jsonify(success=False, message=f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher/students_for_marks')
@teacher_required
def get_students_for_marks():
    teacher_id = session['teacher_id']
    term = request.args.get('term', 'Term 1') 
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        query = "SELECT s.id, s.full_name, s.admission_number, s.grade, m.overall_average, m.overall_grade, m.overall_remark, m.updated_at FROM students s JOIN classes c ON s.class_id = c.id LEFT JOIN marks m ON s.id = m.student_id AND m.term = %s WHERE c.teacher_id = %s ORDER BY s.full_name ASC"
        cursor.execute(query, (term, teacher_id))
        students = cursor.fetchall()
        for student in students:
            if student['updated_at'] and isinstance(student['updated_at'], datetime.datetime):
                student['updated_at'] = student['updated_at'].strftime('%Y-%m-%d %H:%M:%S')
        return jsonify(success=True, students=students)
    except mysql.connector.Error as err:
        return jsonify(success=False, message=f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher/student_marks/<int:student_id>')
@teacher_required
def get_student_marks(student_id):
    teacher_id = session['teacher_id']
    term = request.args.get('term', 'Term 1')
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        sql = "SELECT s.full_name, s.admission_number, s.grade, c.name as class_name FROM students s JOIN classes c ON s.class_id = c.id WHERE s.id = %s AND c.teacher_id = %s"
        cursor.execute(sql, (student_id, teacher_id))
        student_details = cursor.fetchone()
        if not student_details: return jsonify(success=False, message="Student not found or not in your class."), 404
        cursor.execute("SELECT marks_data FROM marks WHERE student_id = %s AND term = %s", (student_id, term))
        marks_record = cursor.fetchone()
        student_details['marks_data'] = None
        if marks_record and marks_record['marks_data']:
            try: student_details['marks_data'] = json.loads(marks_record['marks_data'])
            except (json.JSONDecodeError, TypeError): pass
        return jsonify(success=True, student=student_details)
    except mysql.connector.Error as err:
        return jsonify(success=False, message=f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher/save_marks/<int:student_id>', methods=['POST'])
@teacher_required
def save_student_marks(student_id):
    teacher_id = session['teacher_id']
    data = request.get_json()
    term = data.get('term')
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("SELECT s.id FROM students s JOIN classes c ON s.class_id = c.id WHERE s.id = %s AND c.teacher_id = %s", (student_id, teacher_id))
        if cursor.fetchone() is None: return jsonify(success=False, message="Authorization Error."), 403
        marks_payload_json = json.dumps(data.get('subjects'))
        overall = data.get('overall', {})
        sql = "INSERT INTO marks (student_id, term, teacher_id, marks_data, overall_average, overall_grade, overall_remark) VALUES (%s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE teacher_id = VALUES(teacher_id), marks_data = VALUES(marks_data), overall_average = VALUES(overall_average), overall_grade = VALUES(overall_grade), overall_remark = VALUES(overall_remark)"
        values = (student_id, term, teacher_id, marks_payload_json, overall.get('average'), overall.get('grade'), overall.get('remark'))
        cursor.execute(sql, values)
        db_conn.commit()
        return jsonify(success=True, message=f"Marks for {term} saved successfully!")
    except mysql.connector.Error as err:
        db_conn.rollback()
        return jsonify(success=False, message=f"Database error: {err}")
    finally:
        cursor.close()
        db_conn.close()

@app.route('/teacher/generate_report_data/<int:student_id>')
@teacher_required
def generate_report_data(student_id):
    teacher_id = session['teacher_id']
    term = request.args.get('term', 'Term 1')
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        sql = "SELECT m.*, s.full_name, s.admission_number, s.grade, c.name AS class_name, t.full_name AS teacher_name FROM marks m JOIN students s ON m.student_id = s.id JOIN classes c ON s.class_id = c.id LEFT JOIN teachers t ON m.teacher_id = t.id WHERE s.id = %s AND c.teacher_id = %s AND m.term = %s"
        cursor.execute(sql, (student_id, teacher_id, term))
        report_data = cursor.fetchone()
        if not report_data: return jsonify(success=False, message=f"No marks found for this student in {term}."), 404
        report_data['report_generated_on'] = datetime.datetime.now().strftime('%B %d, %Y')
        try: report_data['marks_details'] = json.loads(report_data['marks_data'])
        except (json.JSONDecodeError, TypeError): report_data['marks_details'] = {}
        del report_data['marks_data']
        return jsonify(success=True, data=report_data)
    except mysql.connector.Error as err: return jsonify(success=False, message=f"Database error: {err}")
    finally: cursor.close(); db_conn.close()

@app.route('/teacher/my_reports')
@teacher_required
def teacher_get_my_reports():
    teacher_id = session['teacher_id']
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        query = "SELECT m.id AS mark_id, s.full_name AS student_name, s.admission_number, m.term, m.overall_average, m.overall_grade FROM marks m JOIN students s ON m.student_id = s.id JOIN classes c ON s.class_id = c.id WHERE c.teacher_id = %s ORDER BY s.full_name, m.term"
        cursor.execute(query, (teacher_id,))
        reports = cursor.fetchall()
        return jsonify(success=True, reports=reports)
    except mysql.connector.Error as err: return jsonify(success=False, message=f"Database error: {err}")
    finally: cursor.close(); db_conn.close()
        
@app.route('/teacher/get_report_data/<int:mark_id>')
@teacher_required
def get_report_data_by_mark_id(mark_id):
    teacher_id = session['teacher_id']
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        sql = "SELECT m.*, s.full_name, s.admission_number, s.grade, c.name AS class_name, t.full_name AS teacher_name FROM marks m JOIN students s ON m.student_id = s.id JOIN classes c ON s.class_id = c.id LEFT JOIN teachers t ON m.teacher_id = t.id WHERE m.id = %s AND c.teacher_id = %s"
        cursor.execute(sql, (mark_id, teacher_id))
        report_data = cursor.fetchone()
        if not report_data: return jsonify(success=False, message="Report not found or you are not authorized."), 404
        report_data['report_generated_on'] = datetime.datetime.now().strftime('%B %d, %Y')
        try: report_data['marks_details'] = json.loads(report_data['marks_data'])
        except (json.JSONDecodeError, TypeError): report_data['marks_details'] = {}
        del report_data['marks_data']
        return jsonify(success=True, data=report_data)
    except mysql.connector.Error as err: return jsonify(success=False, message=f"Database error: {err}")
    finally: cursor.close(); db_conn.close()

@app.route('/teacher_logout')
def teacher_logout():
    session.pop('teacher_id', None)
    session.pop('teacher_name', None)
    flash("Teacher Logged Out.", "info")
    return redirect(url_for('teacher_login'))

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if 'admin_id' in session: return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        access_code = request.form.get('access_code')
        password = request.form.get('password')
        db_conn = get_db_connection()
        cursor = db_conn.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute("SELECT * FROM admins WHERE access_code = %s", (access_code,))
            admin = cursor.fetchone()
            if admin and check_password_hash(admin['password'], password):
                session['admin_id'] = admin['id']
                flash("Successful! Redirecting...", "success")
                return render_template('admin_login.html', login_redirect_url=url_for('admin_dashboard'))
            else: flash("Invalid access code or password.", "error")
        finally: cursor.close(); db_conn.close()
    return render_template('admin_login.html')

@app.route('/admin_signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == 'POST':
        access_code = request.form.get('access_code')
        password = request.form.get('password')
        if not all([access_code, password]):
            flash("All fields are required.", "error")
            return redirect(url_for('admin_signup'))
        hashed_password = generate_password_hash(password)
        db_conn = get_db_connection()
        cursor = db_conn.cursor(buffered=True)
        try:
            cursor.execute("INSERT INTO admins (access_code, password) VALUES (%s, %s)",(access_code, hashed_password))
            db_conn.commit()
            flash("Admin registered successfully! Please log in.", "success")
            return redirect(url_for('admin_login'))
        except mysql.connector.Error as err:
            if err.errno == 1062:
                flash("An admin with this access code already exists.", "error")
            else:
                flash(f"Database error during signup: {err}", "error")
            return redirect(url_for('admin_signup'))
        finally:
            cursor.close()
            db_conn.close()
    return render_template('admin_signup.html')

@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    total_teachers, total_students = 0, 0
    try:
        cursor.execute("SELECT COUNT(*) FROM teachers"); total_teachers = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM students"); total_students = cursor.fetchone()[0]
    finally: cursor.close(); db_conn.close()
    return render_template('admin_dashboard.html', total_teachers=total_teachers, total_students=total_students)

@app.route('/admin_logout')
@admin_required
def admin_logout():
    session.pop('admin_id', None)
    flash("Admin logged out.", "info")
    return redirect(url_for('admin_login'))

@app.route('/add_student', methods=['POST'])
@admin_required
def add_student():
    class_id = request.form.get('classId') or None
    hashed_password = generate_password_hash(request.form.get('password'))
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        sql = "INSERT INTO students (full_name, admission_number, age, grade, class_id, password) VALUES (%s, %s, %s, %s, %s, %s)"
        values = (request.form.get('fullName'), request.form.get('admissionNumber'), request.form.get('age'), request.form.get('grade'), class_id, hashed_password)
        cursor.execute(sql, values)
        db_conn.commit()
        return jsonify(success=True, message="Student added successfully!")
    except mysql.connector.Error as err: return jsonify(success=False, message=f"Database error: {err}")
    finally: cursor.close(); db_conn.close()

@app.route('/get_students', methods=['GET'])
@admin_required
def get_students():
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        sql = "SELECT s.id, s.full_name, s.admission_number, s.grade, c.name as class_name FROM students s LEFT JOIN classes c ON s.class_id = c.id ORDER BY s.full_name ASC"
        cursor.execute(sql)
        students = cursor.fetchall()
        return jsonify(success=True, students=students)
    finally: cursor.close(); db_conn.close()

@app.route('/delete_student/<int:student_id>', methods=['DELETE'])
@admin_required
def delete_student(student_id):
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("DELETE FROM marks WHERE student_id = %s", (student_id,))
        cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
        db_conn.commit()
        return jsonify(success=True, message="Student and their marks deleted.")
    finally: cursor.close(); db_conn.close()

@app.route('/add_teacher', methods=['POST'])
@admin_required
def add_teacher():
    hashed_password = generate_password_hash(request.form.get('password'))
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        sql = "INSERT INTO teachers (full_name, phone_number, email, subject, access_code, password) VALUES (%s, %s, %s, %s, %s, %s)"
        values = (request.form.get('fullName'), request.form.get('phoneNumber'), request.form.get('email'), request.form.get('subject'), request.form.get('accessCode'), hashed_password)
        cursor.execute(sql, values)
        db_conn.commit()
        return jsonify(success=True, message="Teacher added.")
    except mysql.connector.Error as err: return jsonify(success=False, message=f"Database error: {err}")
    finally: cursor.close(); db_conn.close()

@app.route('/get_teachers', methods=['GET'])
@admin_required
def get_teachers():
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        cursor.execute("SELECT id, full_name, phone_number, email, subject, access_code FROM teachers")
        teachers = cursor.fetchall()
        return jsonify(success=True, teachers=teachers)
    finally: cursor.close(); db_conn.close()

@app.route('/delete_teacher/<int:teacher_id>', methods=['DELETE'])
@admin_required
def delete_teacher(teacher_id):
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("UPDATE classes SET teacher_id = NULL WHERE teacher_id = %s", (teacher_id,))
        cursor.execute("DELETE FROM teachers WHERE id = %s", (teacher_id,))
        db_conn.commit()
        return jsonify(success=True, message="Teacher deleted.")
    finally: cursor.close(); db_conn.close()

@app.route('/admin_dashboard_counts')
@admin_required
def admin_dashboard_counts():
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM teachers"); total_teachers = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM students"); total_students = cursor.fetchone()[0]
        return jsonify(success=True, total_teachers=total_teachers, total_students=total_students)
    finally: cursor.close(); db_conn.close()

@app.route('/get_classes', methods=['GET'])
@admin_required
def get_classes():
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        sql = "SELECT c.id, c.name, c.grade, c.teacher_id, t.full_name AS teacher_name FROM classes c LEFT JOIN teachers t ON c.teacher_id = t.id ORDER BY c.grade, c.name"
        cursor.execute(sql)
        classes = cursor.fetchall()
        return jsonify(success=True, classes=classes)
    finally: cursor.close(); db_conn.close()

@app.route('/get_class/<int:class_id>', methods=['GET'])
@admin_required
def get_class(class_id):
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        cursor.execute("SELECT id, name, grade, teacher_id FROM classes WHERE id = %s", (class_id,))
        cls = cursor.fetchone()
        if cls: return jsonify(success=True, class_data=cls)
        else: return jsonify(success=False, message="Class not found."), 404
    finally: cursor.close(); db_conn.close()

@app.route('/add_class', methods=['POST'])
@admin_required
def add_class():
    teacher_id = request.form.get('teacherId') or None
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        sql = "INSERT INTO classes (name, grade, teacher_id) VALUES (%s, %s, %s)"
        values = (request.form.get('className'), request.form.get('grade'), teacher_id)
        cursor.execute(sql, values)
        db_conn.commit()
        return jsonify(success=True, message="Class created.")
    except mysql.connector.Error as err: return jsonify(success=False, message=f"Database error: {err}")
    finally: cursor.close(); db_conn.close()

@app.route('/update_class/<int:class_id>', methods=['PUT'])
@admin_required
def update_class(class_id):
    teacher_id = request.form.get('teacherId') or None
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        sql = "UPDATE classes SET name = %s, grade = %s, teacher_id = %s WHERE id = %s"
        values = (request.form.get('className'), request.form.get('grade'), teacher_id, class_id)
        cursor.execute(sql, values)
        db_conn.commit()
        return jsonify(success=True, message="Class updated.")
    finally: cursor.close(); db_conn.close()

@app.route('/delete_class/<int:class_id>', methods=['DELETE'])
@admin_required
def delete_class(class_id):
    db_conn = get_db_connection()
    cursor = db_conn.cursor()
    try:
        cursor.execute("UPDATE students SET class_id = NULL WHERE class_id = %s", (class_id,))
        cursor.execute("DELETE FROM classes WHERE id = %s", (class_id,))
        db_conn.commit()
        return jsonify(success=True, message="Class deleted.")
    finally: cursor.close(); db_conn.close()

@app.route('/admin/all_reports')
@admin_required
def admin_get_all_reports():
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        query = "SELECT m.id AS mark_id, s.full_name AS student_name, s.admission_number, m.term, m.overall_average, m.overall_grade, t.full_name AS teacher_name FROM marks m JOIN students s ON m.student_id = s.id LEFT JOIN teachers t ON m.teacher_id = t.id ORDER BY s.full_name, m.term"
        cursor.execute(query)
        reports = cursor.fetchall()
        return jsonify(success=True, reports=reports)
    except mysql.connector.Error as err: return jsonify(success=False, message=f"Database error: {err}")
    finally: cursor.close(); db_conn.close()

@app.route('/admin/get_single_report_data/<int:mark_id>')
@admin_required
def admin_get_single_report_data(mark_id):
    db_conn = get_db_connection()
    cursor = db_conn.cursor(dictionary=True, buffered=True)
    try:
        query = "SELECT m.term, m.overall_average, m.overall_grade, m.overall_remark, m.marks_data, s.full_name, s.admission_number, s.grade, c.name AS class_name, t.full_name AS teacher_name FROM marks m JOIN students s ON m.student_id = s.id LEFT JOIN teachers t ON m.teacher_id = t.id LEFT JOIN classes c ON s.class_id = c.id WHERE m.id = %s"
        cursor.execute(query, (mark_id,))
        report_data = cursor.fetchone()
        if not report_data: return jsonify(success=False, message="Report data not found."), 404
        report_data['report_generated_on'] = datetime.datetime.now().strftime('%B %d, %Y')
        try: report_data['marks_details'] = json.loads(report_data['marks_data'])
        except (json.JSONDecodeError, TypeError): report_data['marks_details'] = {}
        del report_data['marks_data']
        return jsonify(success=True, data=report_data)
    except mysql.connector.Error as err: return jsonify(success=False, message=f"Database error: {err}")
    finally: cursor.close(); db_conn.close()

if __name__ == '__main__':
    app.run(debug=True)