from flask import Flask, render_template, request, redirect, session, flash
import secrets
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

        cur.execute("""
            INSERT INTO Students (full_name, email, password)
            VALUES (%s, %s, %s)
        """, (full_name, email, password))
        mysql.connection.commit()
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
    eco_points = row[0] if row else 0

    cur.execute("""
        SELECT full_name, eco_points
        FROM Students
        ORDER BY eco_points DESC
        LIMIT 5
    """)
    leaderboard = cur.fetchall()
    cur.close()

    level = (eco_points // 50) + 1
    points_into_level = eco_points % 50
    progress_pct = 100 if eco_points > 0 and points_into_level == 0 else int((points_into_level / 50) * 100)
    points_to_next = 50 - points_into_level if points_into_level else 50

    return render_template(
        'dashboard.html',
        name=session['student_name'],
        eco_points=eco_points,
        level=level,
        progress_pct=progress_pct,
        points_to_next=points_to_next,
        leaderboard=leaderboard
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
    SELECT b.box_id, b.title, b.description, b.original_price, b.discounted_price,
           b.quantity_available, b.pickup_start, b.pickup_end, b.eco_points_reward,
           v.vendor_name, v.location
    FROM Surprise_Boxes b
    JOIN Vendors v ON b.vendor_id = v.vendor_id
    WHERE b.quantity_available > 0
    AND b.status = 'Available'
    ORDER BY b.pickup_start ASC
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
@app.route('/reserve/<int:box_id>', methods=['GET', 'POST'])
def reserve_box(box_id):

    if 'student_id' not in session:
        return redirect('/login')

    if request.method == 'GET':
        return redirect('/boxes')

    student_id = session['student_id']
    qty = int(request.form.get('quantity', 1))

    if qty < 1:
        flash('Quantity must be at least 1.', 'warning')
        return redirect('/boxes')

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT b.discounted_price, b.quantity_available, b.title
        FROM Surprise_Boxes b
        WHERE b.box_id = %s AND b.status = 'Available'
    """, (box_id,))
    box = cur.fetchone()

    if box is None:
        cur.close()
        flash('Box not found or not available.', 'danger')
        return redirect('/boxes')

    discounted_price = float(box[0])
    quantity_available = box[1]
    box_title = box[2]

    if quantity_available < qty:
        cur.close()
        flash(f'Only {quantity_available} available for "{box_title}".', 'warning')
        return redirect('/boxes')

    total_price = round(discounted_price * qty, 2)

    try:
        # Simple, human-friendly pickup code (digits only) for counter verification.
        # Stored per Order so the vendor can complete the correct reservation.
        pickup_code = ''.join(secrets.choice('0123456789') for _ in range(6))

        cur.execute("""
            INSERT INTO Orders
            (student_id, box_id, quantity, total_price, order_status, pickup_code)
            VALUES (%s, %s, %s, %s, 'Reserved', %s)
        """, (student_id, box_id, qty, total_price, pickup_code))

        cur.execute("""
            UPDATE Surprise_Boxes
            SET quantity_available = quantity_available - %s
            WHERE box_id = %s AND quantity_available >= %s AND status = 'Available'
        """, (qty, box_id, qty))

        if cur.rowcount == 0:
            mysql.connection.rollback()
            flash('Could not reserve — box may be out of stock. Please try again.', 'warning')
            return redirect('/boxes')

        mysql.connection.commit()
        flash(f'Reserved {qty} box(es). Pick up during the window shown in My Orders.', 'success')
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
        SELECT o.order_id, b.title, o.total_price, o.order_date, o.order_status,
               o.quantity, v.vendor_name, v.location, b.pickup_start, b.pickup_end
               , o.pickup_code
        FROM Orders o
        JOIN Surprise_Boxes b ON o.box_id = b.box_id
        JOIN Vendors v ON b.vendor_id = v.vendor_id
        WHERE o.student_id = %s
        ORDER BY o.order_date DESC
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
        SELECT Orders.order_status, Orders.box_id, Orders.quantity
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
    qty = order[2] if order[2] else 1

    cur.execute("UPDATE Orders SET order_status = 'Cancelled' WHERE order_id = %s", (order_id,))
    cur.execute("""
        UPDATE Surprise_Boxes
        SET quantity_available = quantity_available + %s
        WHERE box_id = %s
    """, (qty, box_id))

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
@app.route('/vendor/dashboard', methods=['GET', 'POST'])
def vendor_dashboard():
    if 'vendor_id' not in session:
        return redirect('/vendor/login')

    cur = mysql.connection.cursor()

    if request.method == 'POST' and request.form.get('update_location'):
        location = request.form.get('location', '').strip()
        cur.execute("UPDATE Vendors SET location = %s WHERE vendor_id = %s",
                    (location, session['vendor_id']))
        mysql.connection.commit()
        flash('Pickup location updated.', 'success')

    cur.execute("SELECT location FROM Vendors WHERE vendor_id = %s", (session['vendor_id'],))
    loc_row = cur.fetchone()
    pickup_location = loc_row[0] if loc_row and loc_row[0] else ''

    cur.execute("""
        SELECT * FROM Surprise_Boxes
        WHERE vendor_id = %s AND status != 'Deleted'
    """, (session['vendor_id'],))
    boxes = cur.fetchall()
    cur.close()

    return render_template(
        'vendor_dashboard.html',
        boxes=boxes,
        name=session['vendor_name'],
        pickup_location=pickup_location
    )

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
               Surprise_Boxes.eco_points_reward,
               COALESCE(Orders.quantity, 1),
               Orders.pickup_code
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
# VENDOR: MARK RESERVATION COMPLETED BY PICKUP CODE
# =========================
@app.route('/vendor/complete_by_code', methods=['POST'])
def complete_by_code():
    if 'vendor_id' not in session:
        return redirect('/vendor/login')

    pickup_code = (request.form.get('pickup_code') or '').strip().upper()
    if not pickup_code:
        flash('Please enter a pickup code.', 'warning')
        return redirect('/vendor/reservations')

    cur = mysql.connection.cursor()

    # Look up a reserved order by code, but only within this vendor's boxes.
    lookup_query = """
        SELECT o.order_id,
               b.eco_points_reward,
               o.student_id,
               COALESCE(o.quantity, 1)
        FROM Orders o
        JOIN Surprise_Boxes b ON o.box_id = b.box_id
        WHERE o.pickup_code = %s
          AND b.vendor_id = %s
          AND o.order_status = 'Reserved'
    """
    cur.execute(lookup_query, (pickup_code, session['vendor_id']))
    order_row = cur.fetchone()

    if not order_row:
        cur.close()
        flash('Invalid pickup code (or order is not reserved).', 'danger')
        return redirect('/vendor/reservations')

    order_id, eco_points_reward, student_id, qty = order_row

    cur.execute("""
        UPDATE Orders
        SET order_status = 'Completed'
        WHERE order_id = %s AND order_status = 'Reserved'
    """, (order_id,))

    if cur.rowcount == 0:
        cur.close()
        flash('That reservation was already completed or cancelled.', 'warning')
        return redirect('/vendor/reservations')

    eco_points = eco_points_reward * qty

    cur.execute("UPDATE Students SET eco_points = eco_points + %s WHERE student_id = %s",
                (eco_points, student_id))
    reason = f"Completed reservation #{order_id} - Surprise Box pickup confirmed (code)"
    cur.execute("""
        INSERT INTO Eco_Point_Log (student_id, points_earned, reason)
        VALUES (%s, %s, %s)
    """, (student_id, eco_points, reason))

    mysql.connection.commit()
    cur.close()

    flash(f'Pickup confirmed for order #{order_id}. {eco_points} eco points awarded.', 'success')
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
            return redirect('/admin/vendors')
        flash('Invalid admin credentials.', 'danger')
        return redirect('/admin/login')

    return render_template('admin_login.html')

# =========================
# ADMIN HELPERS
# =========================
def require_admin():
    if 'admin_id' not in session:
        return redirect('/admin/login')
    return None

# =========================
# ADMIN: MANAGE VENDORS
# =========================
@app.route('/admin/vendors')
def admin_vendors():
    guard = require_admin()
    if guard:
        return guard

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT v.vendor_id, v.vendor_name, v.location, v.email,
               (SELECT COUNT(*) FROM Surprise_Boxes b
                WHERE b.vendor_id = v.vendor_id AND b.status != 'Deleted') AS active_boxes
        FROM Vendors v
        ORDER BY v.vendor_id
    """)
    vendors = cur.fetchall()
    cur.close()

    return render_template('admin_vendors.html', vendors=vendors, name=session['admin_name'])

@app.route('/admin/vendors/add', methods=['GET', 'POST'])
def admin_vendor_add():
    guard = require_admin()
    if guard:
        return guard

    if request.method == 'POST':
        vendor_name = request.form['vendor_name']
        location = request.form.get('location', '').strip()
        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor()
        cur.execute("SELECT vendor_id FROM Vendors WHERE email = %s", (email,))
        if cur.fetchone():
            cur.close()
            flash('Email already in use.', 'danger')
            return redirect('/admin/vendors/add')

        cur.execute("""
            INSERT INTO Vendors (vendor_name, location, email, password)
            VALUES (%s, %s, %s, %s)
        """, (vendor_name, location, email, password))
        mysql.connection.commit()
        cur.close()

        flash('Vendor added successfully.', 'success')
        return redirect('/admin/vendors')

    return render_template('admin_vendor_form.html', is_edit=False, vendor=None, name=session['admin_name'])

@app.route('/admin/vendors/edit/<int:vendor_id>', methods=['GET', 'POST'])
def admin_vendor_edit(vendor_id):
    guard = require_admin()
    if guard:
        return guard

    cur = mysql.connection.cursor()

    if request.method == 'POST':
        vendor_name = request.form['vendor_name']
        location = request.form.get('location', '').strip()
        email = request.form['email']
        password = request.form.get('password', '').strip()

        cur.execute("SELECT vendor_id FROM Vendors WHERE email = %s AND vendor_id != %s",
                    (email, vendor_id))
        if cur.fetchone():
            cur.close()
            flash('Email already in use by another vendor.', 'danger')
            return redirect(f'/admin/vendors/edit/{vendor_id}')

        if password:
            cur.execute("""
                UPDATE Vendors
                SET vendor_name=%s, location=%s, email=%s, password=%s
                WHERE vendor_id=%s
            """, (vendor_name, location, email, password, vendor_id))
        else:
            cur.execute("""
                UPDATE Vendors
                SET vendor_name=%s, location=%s, email=%s
                WHERE vendor_id=%s
            """, (vendor_name, location, email, vendor_id))

        mysql.connection.commit()
        cur.close()
        flash('Vendor updated successfully.', 'success')
        return redirect('/admin/vendors')

    cur.execute("SELECT vendor_id, vendor_name, location, email FROM Vendors WHERE vendor_id = %s", (vendor_id,))
    vendor = cur.fetchone()
    cur.close()

    if not vendor:
        flash('Vendor not found.', 'danger')
        return redirect('/admin/vendors')

    return render_template('admin_vendor_form.html', is_edit=True, vendor=vendor, name=session['admin_name'])

@app.route('/admin/vendors/delete/<int:vendor_id>')
def admin_vendor_delete(vendor_id):
    guard = require_admin()
    if guard:
        return guard

    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) FROM Surprise_Boxes WHERE vendor_id = %s", (vendor_id,))
    if cur.fetchone()[0] > 0:
        cur.close()
        flash('Cannot delete: vendor has surprise boxes on record.', 'warning')
        return redirect('/admin/vendors')

    cur.execute("""
        SELECT COUNT(*) FROM Orders o
        JOIN Surprise_Boxes b ON o.box_id = b.box_id
        WHERE b.vendor_id = %s
    """, (vendor_id,))
    if cur.fetchone()[0] > 0:
        cur.close()
        flash('Cannot delete: vendor has order history.', 'warning')
        return redirect('/admin/vendors')

    cur.execute("DELETE FROM Vendors WHERE vendor_id = %s", (vendor_id,))
    if cur.rowcount == 0:
        cur.close()
        flash('Vendor not found.', 'danger')
        return redirect('/admin/vendors')

    mysql.connection.commit()
    cur.close()
    flash('Vendor deleted.', 'success')
    return redirect('/admin/vendors')

# =========================
# ADMIN LOGOUT
# =========================
@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect('/admin/login')

# =========================
# RUN APPLICATION
# =========================
if __name__ == '__main__':
    app.run(debug=True)