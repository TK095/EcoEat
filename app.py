from flask import Flask, render_template, request, redirect, session, flash
from MySQLdb import IntegrityError
from db_config import mysql

app = Flask(__name__)
app.secret_key = "ecoeat_secret_key"
# =========================
# DATABASE CONFIGURATION
# =========================
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'Inosai123'
app.config['MYSQL_DB'] = 'ecoeat'

mysql.init_app(app)

# =========================
# HOME ROUTE
# =========================
@app.route('/')
def home():
    return render_template('index.html')

# =========================
# STUDENT REGISTRATION
# =========================
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("SELECT student_id FROM Students WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            flash('Email already registered. Please login or use a different email.', 'danger')
            return redirect('/register')

        try:
            cur.execute("""
                INSERT INTO Students (full_name, email, password)
                VALUES (%s, %s, %s)
            """, (full_name, email, password))
            mysql.connection.commit()
        except IntegrityError:
            mysql.connection.rollback()
            flash('Email already registered. Please login or use a different email.', 'danger')
            return redirect('/register')
        finally:
            cur.close()

        flash('Registration successful! Please log in.', 'success')
        return redirect('/login')

    return render_template('register.html')

# =========================
# STUDENT LOGIN
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor()

        query = """
        SELECT * FROM Students
        WHERE email = %s AND password = %s
        """

        cur.execute(query, (email, password))

        student = cur.fetchone()

        cur.close()

        if student:

            session['student_id'] = student[0]
            session['student_name'] = student[1]

            return redirect('/dashboard')

        else:
            flash('Invalid email or password.', 'danger')
            return redirect('/login')

    return render_template('login.html')

# =========================
# STUDENT DASHBOARD
# =========================
@app.route('/dashboard')
def dashboard():

    if 'student_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()
    cur.execute("SELECT eco_points FROM Students WHERE student_id = %s", (session['student_id'],))
    row = cur.fetchone()
    cur.close()
    eco_points = row[0] if row else 0

    return render_template(
        'dashboard.html',
        name=session['student_name'],
        eco_points=eco_points
    )

# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():

    session.clear()

    return redirect('/login')

# =========================
# VIEW SURPRISE BOXES
# =========================
@app.route('/boxes')
def boxes():

    if 'student_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    query = """
    SELECT * FROM Surprise_Boxes
    WHERE quantity_available > 0
    AND status = 'Available'
    """

    cur.execute(query)

    boxes = cur.fetchall()

    cur.close()

    return render_template(
        'boxes.html',
        boxes=boxes
    )

# =========================
# RESERVE SURPRISE BOX
# =========================
@app.route('/reserve/<int:box_id>')
def reserve_box(box_id):

    if 'student_id' not in session:
        return redirect('/login')

    student_id = session['student_id']

    cur = mysql.connection.cursor()

    # Get box information (must be available and in stock)
    query = """
    SELECT discounted_price, quantity_available
    FROM Surprise_Boxes
    WHERE box_id = %s AND status = 'Available'
    """

    cur.execute(query, (box_id,))

    box = cur.fetchone()

    if box is None:
        cur.close()
        flash('Box not found or not available.', 'danger')
        return redirect('/boxes')

    discounted_price = box[0]
    quantity_available = box[1]

    if quantity_available <= 0:
        cur.close()
        flash('Box is out of stock.', 'warning')
        return redirect('/boxes')

    try:
        cur.execute("""
            INSERT INTO Orders
            (student_id, box_id, total_price, order_status)
            VALUES (%s, %s, %s, 'Reserved')
        """, (student_id, box_id, discounted_price))

        cur.execute("""
            UPDATE Surprise_Boxes
            SET quantity_available = quantity_available - 1
            WHERE box_id = %s AND quantity_available > 0 AND status = 'Available'
        """, (box_id,))

        if cur.rowcount == 0:
            mysql.connection.rollback()
            flash('Could not reserve — box may be out of stock. Please try again.', 'warning')
            return redirect('/boxes')

        mysql.connection.commit()
        flash('Reservation successful! View it in My Orders.', 'success')
    except Exception:
        mysql.connection.rollback()
        flash('Reservation failed. Please try again.', 'danger')
        return redirect('/boxes')
    finally:
        cur.close()

    return redirect('/orders')

# =========================
# STUDENT ORDER HISTORY
# =========================
@app.route('/orders')
def orders():
    if 'student_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT Orders.order_id, Surprise_Boxes.title, Orders.total_price, Orders.order_date, Orders.order_status
        FROM Orders
        JOIN Surprise_Boxes ON Orders.box_id = Surprise_Boxes.box_id
        WHERE Orders.student_id = %s
        ORDER BY Orders.order_date DESC
    """, (session['student_id'],))
    orders = cur.fetchall()
    cur.close()

    return render_template('orders.html', orders=orders)

# =========================
# CANCEL RESERVATION
# =========================
@app.route('/cancel/<int:order_id>')
def cancel_order(order_id):
    if 'student_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT Orders.order_status, Orders.box_id
        FROM Orders
        JOIN Surprise_Boxes ON Orders.box_id = Surprise_Boxes.box_id
        WHERE Orders.order_id = %s AND Orders.student_id = %s
    """, (order_id, session['student_id']))
    order = cur.fetchone()

    if not order:
        cur.close()
        flash('Order not found.', 'danger')
        return redirect('/orders')

    if order[0] != 'Reserved':
        cur.close()
        flash('Only reserved orders can be cancelled.', 'warning')
        return redirect('/orders')

    box_id = order[1]

    cur.execute("UPDATE Orders SET order_status = 'Cancelled' WHERE order_id = %s", (order_id,))
    cur.execute("""
        UPDATE Surprise_Boxes
        SET quantity_available = quantity_available + 1
        WHERE box_id = %s
    """, (box_id,))

    mysql.connection.commit()
    cur.close()

    flash('Reservation cancelled.', 'success')
    return redirect('/orders')

# =========================
# VENDOR LOGIN
# =========================
@app.route('/vendor/login', methods=['GET', 'POST'])
def vendor_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM Vendors WHERE email = %s AND password = %s", (email, password))
        vendor = cur.fetchone()
        cur.close()

        if vendor:
            session['vendor_id'] = vendor[0]
            session['vendor_name'] = vendor[1]
            return redirect('/vendor/dashboard')
        else:
            flash('Invalid vendor credentials.', 'danger')
            return redirect('/vendor/login')
    return render_template('vendor_login.html')

# =========================
# VENDOR DASHBOARD
# =========================
@app.route('/vendor/dashboard')
def vendor_dashboard():
    if 'vendor_id' not in session:
        return redirect('/vendor/login')

    # Fetch this vendor's surprise boxes
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT * FROM Surprise_Boxes
        WHERE vendor_id = %s AND status != 'Deleted'
    """, (session['vendor_id'],))
    boxes = cur.fetchall()
    cur.close()

    return render_template('vendor_dashboard.html', boxes=boxes, name=session['vendor_name'])

# =========================
# VENDOR LOGOUT
# =========================
@app.route('/vendor/logout')
def vendor_logout():
    session.clear()
    return redirect('/vendor/login')

# =========================
# VENDOR: ADD SURPRISE BOX
# =========================
@app.route('/vendor/add_box', methods=['GET', 'POST'])
def add_box():
    if 'vendor_id' not in session:
        return redirect('/vendor/login')

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        original_price = float(request.form['original_price'])
        discounted_price = float(request.form['discounted_price'])
        quantity = int(request.form['quantity'])
        pickup_start = request.form['pickup_start']
        pickup_end = request.form['pickup_end']
        eco_points = int(request.form['eco_points'])

        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO Surprise_Boxes 
            (vendor_id, title, description, original_price, discounted_price, 
             quantity_available, pickup_start, pickup_end, eco_points_reward, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Available')
        """, (session['vendor_id'], title, description, original_price, discounted_price,
              quantity, pickup_start, pickup_end, eco_points))
        mysql.connection.commit()
        cur.close()
        return redirect('/vendor/dashboard')

    return render_template('add_box.html')

# =========================
# VENDOR: EDIT SURPRISE BOX
# =========================
@app.route('/vendor/edit_box/<int:box_id>', methods=['GET', 'POST'])
def edit_box(box_id):
    if 'vendor_id' not in session:
        return redirect('/vendor/login')

    cur = mysql.connection.cursor()
    if request.method == 'POST':
        cur.execute("SELECT status FROM Surprise_Boxes WHERE box_id=%s AND vendor_id=%s",
                    (box_id, session['vendor_id']))
        existing = cur.fetchone()
        if not existing or existing[0] == 'Deleted':
            cur.close()
            flash('This box has been deactivated and cannot be edited.', 'warning')
            return redirect('/vendor/dashboard')

        title = request.form['title']
        description = request.form['description']
        original_price = float(request.form['original_price'])
        discounted_price = float(request.form['discounted_price'])
        quantity = int(request.form['quantity'])
        pickup_start = request.form['pickup_start']
        pickup_end = request.form['pickup_end']
        eco_points = int(request.form['eco_points'])

        cur.execute("""
            UPDATE Surprise_Boxes 
            SET title=%s, description=%s, original_price=%s, discounted_price=%s,
                quantity_available=%s, pickup_start=%s, pickup_end=%s, eco_points_reward=%s
            WHERE box_id=%s AND vendor_id=%s
        """, (title, description, original_price, discounted_price, quantity,
              pickup_start, pickup_end, eco_points, box_id, session['vendor_id']))
        mysql.connection.commit()
        cur.close()
        return redirect('/vendor/dashboard')

    # GET request – show current data
    cur.execute("SELECT * FROM Surprise_Boxes WHERE box_id=%s AND vendor_id=%s", (box_id, session['vendor_id']))
    box = cur.fetchone()
    cur.close()
    if not box:
        flash('Box not found or you do not own it.', 'danger')
        return redirect('/vendor/dashboard')
    if box[10] == 'Deleted':
        flash('This box has been deactivated and cannot be edited.', 'warning')
        return redirect('/vendor/dashboard')
    return render_template('edit_box.html', box=box)

# =========================
# VENDOR: DELETE SURPRISE BOX
# =========================
@app.route('/vendor/delete_box/<int:box_id>')
def delete_box(box_id):
    if 'vendor_id' not in session:
        return redirect('/vendor/login')

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM Orders
        JOIN Surprise_Boxes ON Orders.box_id = Surprise_Boxes.box_id
        WHERE Surprise_Boxes.box_id = %s
          AND Surprise_Boxes.vendor_id = %s
          AND Orders.order_status = 'Reserved'
    """, (box_id, session['vendor_id']))
    reserved_count = cur.fetchone()[0]

    if reserved_count > 0:
        cur.close()
        flash('Cannot deactivate: this box has active reserved orders. Complete or wait for cancellations first.', 'warning')
        return redirect('/vendor/dashboard')

    cur.execute("""
        UPDATE Surprise_Boxes SET status = 'Deleted'
        WHERE box_id=%s AND vendor_id=%s
    """, (box_id, session['vendor_id']))
    mysql.connection.commit()
    cur.close()
    flash('Surprise box deactivated.', 'success')
    return redirect('/vendor/dashboard')

# =========================
# VENDOR: VIEW RESERVATIONS
# =========================
@app.route('/vendor/reservations')
def vendor_reservations():
    # Check if vendor is logged in
    if 'vendor_id' not in session:
        return redirect('/vendor/login')
    
    cur = mysql.connection.cursor()
    
    # Get all orders for this vendor's boxes, with student info
    query = """
        SELECT Orders.order_id, 
               Orders.order_date, 
               Orders.order_status,
               Students.full_name,
               Students.student_id,
               Surprise_Boxes.title,
               Surprise_Boxes.eco_points_reward
        FROM Orders
        JOIN Surprise_Boxes ON Orders.box_id = Surprise_Boxes.box_id
        JOIN Students ON Orders.student_id = Students.student_id
        WHERE Surprise_Boxes.vendor_id = %s
        ORDER BY Orders.order_date DESC
    """
    
    cur.execute(query, (session['vendor_id'],))
    reservations = cur.fetchall()
    cur.close()
    
    return render_template('vendor_reservations.html', 
                         reservations=reservations, 
                         name=session['vendor_name'])

# =========================
# VENDOR: MARK RESERVATION AS COMPLETED
# =========================
@app.route('/vendor/complete_reservation/<int:order_id>')
def complete_reservation(order_id):
    # Check if vendor is logged in
    if 'vendor_id' not in session:
        return redirect('/vendor/login')
    
    cur = mysql.connection.cursor()
    
    # First, verify this order belongs to this vendor's box
    # (Security check - prevent vendors from completing orders for other vendors)
    verify_query = """
        SELECT Orders.order_id, Orders.order_status,
               Surprise_Boxes.eco_points_reward, 
               Orders.student_id
        FROM Orders
        JOIN Surprise_Boxes ON Orders.box_id = Surprise_Boxes.box_id
        WHERE Orders.order_id = %s AND Surprise_Boxes.vendor_id = %s
    """
    
    cur.execute(verify_query, (order_id, session['vendor_id']))
    order = cur.fetchone()
    
    if not order:
        cur.close()
        flash('Order not found or you do not have permission to modify it.', 'danger')
        return redirect('/vendor/reservations')

    if order[1] == 'Completed':
        cur.close()
        flash('This reservation has already been completed.', 'info')
        return redirect('/vendor/reservations')

    if order[1] != 'Reserved':
        cur.close()
        flash('Only reserved orders can be marked as completed.', 'warning')
        return redirect('/vendor/reservations')

    cur.execute("""
        UPDATE Orders SET order_status = 'Completed'
        WHERE order_id = %s AND order_status = 'Reserved'
    """, (order_id,))

    if cur.rowcount == 0:
        cur.close()
        flash('Order was already completed or cancelled.', 'warning')
        return redirect('/vendor/reservations')

    eco_points = order[2]
    student_id = order[3]

    cur.execute("UPDATE Students SET eco_points = eco_points + %s WHERE student_id = %s",
                (eco_points, student_id))
    reason = f"Completed reservation #{order_id} - Surprise Box pickup confirmed"
    cur.execute("""
        INSERT INTO Eco_Point_Log (student_id, points_earned, reason)
        VALUES (%s, %s, %s)
    """, (student_id, eco_points, reason))

    mysql.connection.commit()
    cur.close()

    flash(f'Pickup confirmed. {eco_points} eco points awarded to the student.', 'success')
    return redirect('/vendor/reservations')

# =========================
# ADMIN LOGIN
# =========================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM Admins WHERE username = %s AND password = %s", (username, password))
        admin = cur.fetchone()
        cur.close()

        if admin:
            session.clear()
            session['admin_id'] = admin[0]
            session['admin_name'] = admin[1]  # username
            return redirect('/admin/dashboard')
        flash('Invalid admin credentials.', 'danger')
        return redirect('/admin/login')

    return render_template('admin_login.html')

# =========================
# ADMIN DASHBOARD
# =========================
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect('/admin/login')

    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) FROM Orders WHERE order_status = 'Completed'")
    meals_rescued = cur.fetchone()[0]

    cur.execute("SELECT COALESCE(SUM(points_earned), 0) FROM Eco_Point_Log")
    eco_points_distributed = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM Students")
    total_students = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM Vendors")
    total_vendors = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM Surprise_Boxes WHERE status != 'Deleted'")
    active_boxes = cur.fetchone()[0]

    cur.execute("""
        SELECT order_status, COUNT(*) AS cnt
        FROM Orders
        GROUP BY order_status
    """)
    order_stats = cur.fetchall()

    cur.execute("""
        SELECT full_name, eco_points
        FROM Students
        ORDER BY eco_points DESC
        LIMIT 5
    """)
    top_students = cur.fetchall()

    cur.execute("""
        SELECT Vendors.vendor_name, COUNT(*) AS completed_orders
        FROM Orders
        JOIN Surprise_Boxes ON Orders.box_id = Surprise_Boxes.box_id
        JOIN Vendors ON Surprise_Boxes.vendor_id = Vendors.vendor_id
        WHERE Orders.order_status = 'Completed'
        GROUP BY Vendors.vendor_id, Vendors.vendor_name
        ORDER BY completed_orders DESC
        LIMIT 5
    """)
    top_vendors = cur.fetchall()

    cur.close()

    return render_template(
        'admin_dashboard.html',
        name=session['admin_name'],
        meals_rescued=meals_rescued,
        eco_points_distributed=eco_points_distributed,
        total_students=total_students,
        total_vendors=total_vendors,
        active_boxes=active_boxes,
        order_stats=order_stats,
        top_students=top_students,
        top_vendors=top_vendors
    )

# =========================
# ADMIN LOGOUT
# =========================
@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

# =========================
# TEST DATABASE CONNECTION
# =========================
@app.route('/test_db')
def test_db():
    cur = mysql.connection.cursor()
    cur.execute("SELECT DATABASE();")
    db = cur.fetchone()
    cur.close()

    return f"Connected to database: {db}"

# =========================
# RUN APPLICATION
# =========================
if __name__ == '__main__':
    app.run(debug=True)