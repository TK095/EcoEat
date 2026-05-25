from flask import Flask, render_template, request, redirect, session
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

        query = """
        INSERT INTO Students (full_name, email, password)
        VALUES (%s, %s, %s)
        """

        values = (full_name, email, password)

        cur.execute(query, values)

        mysql.connection.commit()

        cur.close()

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
            return "Invalid email or password"

    return render_template('login.html')

# =========================
# STUDENT DASHBOARD
# =========================
@app.route('/dashboard')
def dashboard():

    if 'student_id' not in session:
        return redirect('/login')

    return render_template(
        'dashboard.html',
        name=session['student_name']
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
        return "Box not found or not available"

    discounted_price = box[0]
    quantity_available = box[1]

    if quantity_available <= 0:
        return "Box is out of stock"

    # Create reservation with Reserved status
    insert_query = """
    INSERT INTO Orders
    (student_id, box_id, total_price, order_status)
    VALUES (%s, %s, %s, 'Reserved')
    """

    cur.execute(
        insert_query,
        (student_id, box_id, discounted_price)
    )

    # Reduce quantity
    update_query = """
    UPDATE Surprise_Boxes
    SET quantity_available = quantity_available - 1
    WHERE box_id = %s
    """

    cur.execute(update_query, (box_id,))

    mysql.connection.commit()

    cur.close()

    return redirect('/boxes')

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
        return "Order not found"

    if order[0] != 'Reserved':
        cur.close()
        return "Only reserved orders can be cancelled"

    box_id = order[1]

    cur.execute("UPDATE Orders SET order_status = 'Cancelled' WHERE order_id = %s", (order_id,))
    cur.execute("""
        UPDATE Surprise_Boxes
        SET quantity_available = quantity_available + 1
        WHERE box_id = %s
    """, (box_id,))

    mysql.connection.commit()
    cur.close()

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
            return "Invalid vendor credentials"
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
    session.pop('vendor_id', None)
    session.pop('vendor_name', None)
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
            return "This box has been deactivated and cannot be edited"

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
        return "Box not found or you don't own it"
    if box[10] == 'Deleted':
        return "This box has been deactivated and cannot be edited"
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
        UPDATE Surprise_Boxes SET status = 'Deleted'
        WHERE box_id=%s AND vendor_id=%s
    """, (box_id, session['vendor_id']))
    mysql.connection.commit()
    cur.close()
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
        return "Order not found or you don't have permission to modify it"
    
    if order[1] == 'Completed':
        cur.close()
        return "This reservation has already been completed"

    if order[1] != 'Reserved':
        cur.close()
        return "Only reserved orders can be marked as completed"

    # Update order status to 'Completed'
    update_query = "UPDATE Orders SET order_status = 'Completed' WHERE order_id = %s"
    cur.execute(update_query, (order_id,))
    
    # Award eco points to student
    eco_points = order[2]  # eco_points_reward from Surprise_Boxes
    student_id = order[3]
    
    # Update student's total eco points
    update_points = "UPDATE Students SET eco_points = eco_points + %s WHERE student_id = %s"
    cur.execute(update_points, (eco_points, student_id))
    
    # Log the points transaction
    log_query = """
        INSERT INTO Eco_Point_Log (student_id, points_earned, reason)
        VALUES (%s, %s, %s)
    """
    reason = f"Completed reservation #{order_id} - Surprise Box pickup confirmed"
    cur.execute(log_query, (student_id, eco_points, reason))
    
    mysql.connection.commit()
    cur.close()
    
    return redirect('/vendor/reservations')
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