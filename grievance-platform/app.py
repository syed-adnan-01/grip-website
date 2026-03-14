from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
import sqlite3
from sqlite3 import Error
import os
import json
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import jwt
from functools import wraps
from flask_socketio import SocketIO, emit
from twilio.rest import Client

# --- Twilio Configuration (Replace with your credentials) ------------------
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

socketio = SocketIO(app, cors_allowed_origins="*")

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

DB_FILE_NAME = 'grievance.db'
if os.environ.get('VERCEL'):
    DB_FILE = os.path.join('/tmp', DB_FILE_NAME)
    # Copy from local dir to /tmp if not there
    if not os.path.exists(DB_FILE) and os.path.exists(DB_FILE_NAME):
        import shutil
        try:
            shutil.copy2(DB_FILE_NAME, DB_FILE)
            logging.info(f"✅ Copied {DB_FILE_NAME} to {DB_FILE}")
        except Exception as e:
            logging.error(f"❌ Failed to copy DB: {e}")
else:
    DB_FILE = DB_FILE_NAME

def get_db():
    try:
        # On Vercel, if DB still missing, we might need to create it in /tmp
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except Error as e:
        logging.error(f"DB Error: {e}")
        return None

# --- Auth helpers & Audit ---------------------------------------------------

def log_audit(username, action, details):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO audit_logs (username, action, details, timestamp) VALUES (?, ?, ?, datetime('now'))",
                       (username, action, details))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Audit log failed: {e}")

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.cookies.get('token')
        if not token:
            return redirect(url_for('login_view'))
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = data
            return fn(*args, **kwargs)
        except:
            return redirect(url_for('login_view'))
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.cookies.get('token')
        if not token:
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            if data.get('role') != 'admin':
                return jsonify({'error': 'Admin access required'}), 403
            request.user = data
            return fn(*args, **kwargs)
        except:
            return jsonify({'error': 'Invalid token'}), 401
    return wrapper

CATEGORY_KEYWORDS = {
    'Road': ['road', 'pothole', 'street', 'highway', 'pavement', 'footpath', 'traffic', 'signal', 'bridge', 'divider', 'crater', 'bump'],
    'Garbage': ['garbage', 'trash', 'waste', 'dump', 'litter', 'sanitation', 'bin', 'compost', 'smell', 'dirty', 'filth', 'sewage'],
    'Electricity': ['electricity', 'electric', 'power', 'light', 'streetlight', 'wire', 'pole', 'transformer', 'outage', 'blackout', 'voltage'],
    'Water': ['water', 'pipe', 'tap', 'supply', 'leak', 'flood', 'drainage', 'contamination', 'shortage', 'puddle', 'overflow', 'pump'],
    'Transport': ['bus', 'transport', 'auto', 'metro', 'train', 'route', 'stop', 'shelter', 'timetable', 'schedule', 'vehicle', 'commute']
}

def nlp_categorize_and_prioritize(title, description):
    text = (title + ' ' + description).lower()
    
    # Priority check
    high_pri = ['urgent', 'emergency', 'danger', 'accident', 'critical', 'fatal', 'severe', 'immediate']
    low_pri = ['suggestion', 'feature', 'minor', 'cosmetic', 'request', 'feedback', 'inquiry']
    
    priority = 'Medium'
    for kw in high_pri:
        if kw in text:
            priority = 'High'
            break
    if priority == 'Medium':
        for kw in low_pri:
            if kw in text:
                priority = 'Low'
                break

    # Category check
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                scores[cat] += 1
    best_cat = max(scores, key=scores.get)
    category = best_cat if scores[best_cat] > 0 else 'Other'
    
    # Sentiment analysis (1-5 scale)
    angry_words = ['angry', 'furious', 'outraged', 'disgusted', 'pathetic', 'useless', 'incompetent',
                   'worst', 'terrible', 'horrible', 'shameful', 'unacceptable', 'ridiculous', 'fed up',
                   'sick of', 'tired of', 'hate', 'frustrated', 'corruption', 'negligence', 'scam']
    frustrated_words = ['disappointed', 'annoyed', 'unhappy', 'poor', 'bad', 'slow', 'delay',
                        'ignored', 'neglected', 'careless', 'complaint', 'problem', 'issue', 'broken',
                        'damaged', 'failed', 'not working', 'no response', 'still pending', 'weeks',
                        'months', 'repeated', 'again', 'multiple times', 'no action']
    urgent_words = ['urgent', 'emergency', 'danger', 'accident', 'critical', 'fatal', 'life threatening',
                    'health hazard', 'children at risk', 'immediately', 'asap', 'dying', 'death']
    calm_words = ['please', 'kindly', 'request', 'would appreciate', 'thank', 'grateful', 'suggestion']
    
    sentiment_score = 3  # neutral default
    angry_count = sum(1 for w in angry_words if w in text)
    frustrated_count = sum(1 for w in frustrated_words if w in text)
    urgent_count = sum(1 for w in urgent_words if w in text)
    calm_count = sum(1 for w in calm_words if w in text)
    
    if angry_count >= 2 or urgent_count >= 2:
        sentiment_score = 5
    elif angry_count >= 1 or urgent_count >= 1:
        sentiment_score = 4
    elif frustrated_count >= 3:
        sentiment_score = 4
    elif frustrated_count >= 1:
        sentiment_score = 3
    elif calm_count >= 2:
        sentiment_score = 1
    elif calm_count >= 1:
        sentiment_score = 2
    
    return category, priority, sentiment_score

# --- OTP Storage (Simulated for Dev) ---------------------------------------
pending_otps = {} # { phone_number: { otp: "123456", expires: timestamp } }

@app.route('/api/send-otp', methods=['POST'])
def send_otp():
    try:
        data = request.json
        phone = data.get('username', '').strip()
        app.logger.info(f"📩 OTP Requested for: {phone}")
        
        if not phone or len(phone) < 10:
            return jsonify({'error': 'Valid phone number required'}), 400
        
        # Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))
        expiry = datetime.now() + timedelta(minutes=5)
        pending_otps[phone] = {'otp': otp, 'expires': expiry}
        
        # Send Real SMS via Twilio
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            message = client.messages.create(
                body=f"Your GRIP verification code is: {otp}. Valid for 5 minutes.",
                from_=TWILIO_PHONE_NUMBER,
                to=f"+91{phone}" if not phone.startswith('+') else phone
            )
            app.logger.info(f"✅ SMS Sent to {phone}: {message.sid}")
        except Exception as sms_err:
            err_msg = str(sms_err)
            app.logger.error(f"❌ Twilio Error: {err_msg}")
            
            # Diagnostic tips
            if "authenticate" in err_msg.lower():
                app.logger.error("💡 TIP: Your Account SID or Auth Token is incorrect. Check your Twilio Console.")
            elif "is not a mobile number" in err_msg.lower() or "not a valid" in err_msg.lower():
                app.logger.error("💡 TIP: The sender ('from_') number must be a number purchased from Twilio.")
            elif "Permission to send" in err_msg.lower():
                app.logger.error("💡 TIP: Enable 'Geo-Permissions' for India in Twilio Settings -> Messaging -> Settings -> Geo-Permissions.")
            
            # Fallback for dev visibility 
            app.logger.info(f"⚠️ FALLBACK: OTP for {phone}: {otp}")
        
        log_audit(phone, 'OTP_SENT', "Signup OTP generated and sent to physical phone")
        
        return jsonify({'success': True, 'message': 'OTP sent to your phone!'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.json
        username = data.get('username', '')
        password = data.get('password', '')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash, role, assigned_area, assigned_category, fullname FROM users WHERE username=?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            # Create JWT token
            token_data = {
                'id': user['id'],
                'username': user['username'],
                'role': user['role'],
                'fullname': user['fullname'],
                'assigned_area': user['assigned_area'],
                'assigned_category': user['assigned_category'],
                'exp': datetime.utcnow() + timedelta(days=7)
            }
            token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm='HS256')
            
            log_audit(user['username'], 'LOGIN', f"User logged in from {request.remote_addr}")
            
            resp = jsonify({'success': True, 'user': {'username': user['username'], 'role': user['role'], 'fullname': user['fullname']}})
            resp.set_cookie('token', token, httponly=True, secure=False, samesite='Lax', max_age=7*24*3600)
            return resp
        
        return jsonify({'error': 'Invalid username or password'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        fullname = data.get('fullname', '').strip()
        
        if not username or not password:
            return jsonify({'error': 'Missing fields'}), 400

        conn = get_db()
        cursor = conn.cursor()
        
        # Check if user already exists
        cursor.execute('SELECT id FROM users WHERE username=?', (username,))
        if cursor.fetchone():
            conn.close()
            return jsonify({'error': 'Phone number already registered'}), 409
            
        password_hash = generate_password_hash(password)
        cursor.execute("INSERT INTO users (username, password_hash, role, fullname) VALUES (?,?,?,?)", (username, password_hash, 'citizen', fullname))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        token_data = {'id': user_id, 'username': username, 'role': 'citizen', 'fullname': fullname, 'exp': datetime.utcnow() + timedelta(days=7)}
        token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm='HS256')
        
        log_audit(username, 'REGISTER', f"New citizen '{fullname}' registered")
        
        resp = jsonify({'success': True, 'user': {'username': username, 'role': 'citizen', 'fullname': fullname}})
        resp.set_cookie('token', token, httponly=True, secure=False, samesite='Lax', max_age=7*24*3600)
        return resp
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/login')
@app.route('/login.html')
def login_view():
    return render_template('login.html')

@app.route('/logout')
@app.route('/logout.html')
def logout():
    session.clear()
    resp = redirect(url_for('login_view'))
    resp.set_cookie('token', '', expires=0)
    return resp

# --- SocketIO Events --------------------------------------------------------

@socketio.on('live_categorize')
def handle_live_categorize(data):
    title = data.get('title', '')
    description = data.get('description', '')
    print(f"🤖 Live Categorizing: {title[:30]}...")
    category, priority, sentiment = nlp_categorize_and_prioritize(title, description)
    print(f"   => Result: {category} ({priority})")
    emit('categorization_update', {
        'category': category,
        'priority': priority,
        'sentiment': sentiment
    })

# --- Community Chat ---------------------------------------------------------

@app.route('/community')
@app.route('/community.html')
def community_view():
    return render_template('community.html')

@app.route('/api/chat/history', methods=['GET'])
def chat_history():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.id, m.username, m.message, m.timestamp, u.fullname 
            FROM chat_messages m
            LEFT JOIN users u ON m.username = u.username 
            ORDER BY m.id DESC LIMIT 100
        """)
        msgs = [dict(r) for r in cursor.fetchall()]
        conn.close()
        msgs.reverse()
        return jsonify({'messages': msgs})
    except Exception as e:
        return jsonify({'messages': [], 'error': str(e)})

@app.route('/api/chat/send', methods=['POST'])
def chat_send():
    token = request.cookies.get('token')
    if not token:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        user_data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        username = user_data.get('username', 'Anonymous')
    except:
        return jsonify({'error': 'Invalid token'}), 401
    
    data = request.json
    message = data.get('message', '').strip()
    client_id = data.get('clientId') # Optional tracking ID from frontend
    if not message:
        return jsonify({'error': 'Empty message'}), 400
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_messages (username, message, timestamp) VALUES (?,?,?)",
                       (username, message, timestamp))
        msg_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Also broadcast via WebSocket for real-time
        socketio.emit('new_chat_message', {
            'id': msg_id,
            'clientId': client_id,
            'username': username,
            'fullname': fullname,
            'message': message,
            'timestamp': timestamp
        })
        
        return jsonify({'success': True, 'id': msg_id, 'clientId': client_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@socketio.on('chat_message')
def handle_chat_message(data):
    username = data.get('username', 'Anonymous')
    message = data.get('message', '').strip()
    if not message:
        return
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO chat_messages (username, message, timestamp) VALUES (?,?,?)",
                       (username, message, timestamp))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Chat DB Error: {e}")
    emit('new_chat_message', {
        'username': username,
        'message': message,
        'timestamp': timestamp
    }, broadcast=True)

@app.route('/api/me', methods=['GET'])
def api_me():
    token = request.cookies.get('token')
    if not token:
        return jsonify({'user': None})
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        username = data.get('username')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT username, role, fullname FROM users WHERE username=?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return jsonify({'user': dict(user)})
        return jsonify({'user': data}) # Fallback to token if user not found in DB
    except:
        return jsonify({'user': None})

@app.route('/api/ping')
def api_ping():
    return jsonify({
        'status': 'ok',
        'db_path': DB_FILE,
        'db_exists': os.path.exists(DB_FILE),
        'is_vercel': os.environ.get('VERCEL') is not None
    })

@app.route('/')
@app.route('/index.html')
def index():
    return render_template('index.html')

@app.route('/dashboard')
@app.route('/dashboard.html')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/citizen_dashboard.html')
@login_required
def citizen_dashboard():
    return render_template('citizen_dashboard.html')

@app.route('/funds')
@app.route('/funds.html')
@login_required
def funds():
    return render_template('funds.html')

@app.route('/api/complaints', methods=['POST'])
def submit_complaint():
    try:
        data = request.form
        title = data.get('title', '')
        description = data.get('description', '')
        
        auto_cat, auto_pri, sentiment = nlp_categorize_and_prioritize(title, description)
        category = data.get('category', '') or auto_cat
        priority = auto_pri

        area = data.get('area', '')
        citizen_name = data.get('citizen_name', 'Anonymous')
        citizen_contact = data.get('citizen_contact', '')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        image_path = None
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                ts = datetime.now().strftime('%Y%m%d%H%M%S')
                filename = f"{ts}_{filename}"
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_path = filename
        print(f"Submitting complaint: {title}, {category}, {priority}, {area}, lat={latitude}, lon={longitude}, sentiment={sentiment}")
        conn = get_db()
        if not conn:
            return jsonify({'error': 'DB connection failed'}), 500
        cursor = conn.cursor()
        
        # Check if priority column exists, if not, add it (for backward compatibility on first run)
        try:
            cursor.execute("SELECT priority FROM complaints LIMIT 1")
        except:
            cursor.execute("ALTER TABLE complaints ADD COLUMN priority TEXT DEFAULT 'Medium'")

        cursor.execute("""INSERT INTO complaints (title, description, category, priority, area, citizen_name, citizen_contact, image_path, status, sentiment, latitude, longitude, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, ?, datetime('now'))""",
            (title, description, category, priority, area, citizen_name, citizen_contact, image_path, sentiment, latitude, longitude))
        complaint_id = cursor.lastrowid
        conn.commit()
        conn.close()
        print(f"Complaint submitted with ID: {complaint_id}")
        
        # Log to audit table
        log_audit(citizen_name, 'SUBMIT_COMPLAINT', f"Complaint #{complaint_id} submitted")
        
        # Emit real-time event
        socketio.emit('new_complaint', {
            'id': complaint_id,
            'title': title,
            'category': category,
            'area': area,
            'priority': priority,
            'sentiment': sentiment
        })

        return jsonify({'success': True, 'complaint_id': complaint_id, 'category': category, 'priority': priority, 'message': f'Complaint #{complaint_id} submitted successfully!'})
    except Exception as e:
        print(f"Error submitting complaint: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/complaints', methods=['GET'])
def get_complaints():
    try:
        conn = get_db()
        if not conn:
            return jsonify({'error': 'DB connection failed'}), 500
        cursor = conn.cursor()
        status_filter = request.args.get('status', '')
        category_filter = request.args.get('category', '')
        area_filter = request.args.get('area', '')
        priority_filter = request.args.get('priority', '')
        contact_filter = request.args.get('contact', '')
        
        query = "SELECT * FROM complaints WHERE 1=1"
        params = []
        if status_filter:
            query += " AND status=?"; params.append(status_filter)
        if category_filter:
            query += " AND category=?"; params.append(category_filter)
        if priority_filter:
            query += " AND priority=?"; params.append(priority_filter)
        if area_filter:
            query += " AND area=?"; params.append(area_filter)
        if contact_filter:
            query += " AND citizen_contact=?"; params.append(contact_filter)
            
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        complaints = [dict(c) for c in cursor.fetchall()]
        for c in complaints:
            if c.get('created_at'):
                c['created_at'] = c['created_at']
            if c.get('resolved_at'):
                c['resolved_at'] = c['resolved_at']
        conn.close()
        return jsonify(complaints)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/complaints/<int:complaint_id>/status', methods=['PUT'])
def update_status(complaint_id):
    try:
        data = request.json
        new_status = data.get('status')
        updated_by_name = request.user['username'] if hasattr(request, 'user') else 'Anonymous'
        conn = get_db()
        cursor = conn.cursor()
        # Get old status for history
        cursor.execute("SELECT status FROM complaints WHERE id=?", (complaint_id,))
        row = cursor.fetchone()
        old_status = row['status'] if row else 'Unknown'
        if new_status == 'Resolved':
            cursor.execute("UPDATE complaints SET status=?, updated_by=?, resolved_at=datetime('now') WHERE id=?", (new_status, updated_by_name, complaint_id))
        else:
            cursor.execute("UPDATE complaints SET status=?, updated_by=? WHERE id=?", (new_status, updated_by_name, complaint_id))
        # Log to history
        cursor.execute("INSERT INTO complaint_history (complaint_id, old_status, new_status, changed_by, changed_at) VALUES (?, ?, ?, ?, datetime('now'))",
            (complaint_id, old_status, new_status, updated_by_name))
        
        # Log to audit table
        log_audit(updated_by_name, 'STATUS_UPDATE', f"Updated complaint #{complaint_id} from {old_status} to {new_status}")
        
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/officials', methods=['GET', 'POST'])
@admin_required
def manage_officials():
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'GET':
        cursor.execute("SELECT id, username, assigned_area, assigned_category FROM users WHERE role='official'")
        officials = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(officials)
    elif request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        area = data.get('assigned_area', '')
        category = data.get('assigned_category', '')
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        try:
            pwd_hash = generate_password_hash(password)
            cursor.execute("INSERT INTO users (username, password_hash, role, assigned_area, assigned_category) VALUES (?,?,'official',?,?)",
                           (username, pwd_hash, area, category))
            conn.commit()
            log_audit(request.user['username'], 'OFFICIAL_CREATED', f"Created official account: {username}")
        except Exception as e:
            conn.close()
            return jsonify({'error': str(e)}), 400
        conn.close()
        return jsonify({'success': True})

@app.route('/api/officials/<int:id>', methods=['DELETE'])
@admin_required
def delete_official(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE id=? AND role='official'", (id,))
    user = cursor.fetchone()
    if user:
        cursor.execute("DELETE FROM users WHERE id=?", (id,))
        conn.commit()
        log_audit(request.user['username'], 'OFFICIAL_DELETED', f"Deleted official account: {user['username']}")
    conn.close()
    return jsonify({'success': True})

@app.route('/api/audit_logs', methods=['GET'])
@admin_required
def get_audit_logs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 50")
    logs = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(logs)

@app.route('/api/export_complaints', methods=['GET'])
@admin_required
def export_complaints():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title, category, priority, area, status, created_at FROM complaints")
        rows = cursor.fetchall()
        conn.close()
        
        log_audit(request.user['username'], 'DATA_EXPORT', "Exported complaints dataset to CSV")
        
        # Simple CSV generation for MVP
        csv_data = "ID,Title,Category,Priority,Area,Status,Created At\n"
        for r in rows:
            title = str(r['title']).replace(',', ' ').replace('"', '')
            csv_data += f"{r['id']},{title},{r['category']},{r['priority']},{r['area']},{r['status']},{r['created_at']}\n"
            
        import io
        from flask import make_response
        output = make_response(csv_data)
        output.headers["Content-Disposition"] = "attachment; filename=complaints_export.csv"
        output.headers["Content-type"] = "text/csv"
        return output
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/complaints/<int:complaint_id>/history', methods=['GET'])
def get_complaint_history(complaint_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM complaint_history WHERE complaint_id=? ORDER BY changed_at ASC", (complaint_id,))
        history = [dict(h) for h in cursor.fetchall()]
        conn.close()
        return jsonify(history)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/complaints/<int:complaint_id>/rate', methods=['POST'])
def rate_complaint(complaint_id):
    try:
        data = request.json
        rating = data.get('rating')
        feedback_text = data.get('feedback_text', '')
        if not rating or not (1 <= int(rating) <= 5):
            return jsonify({'error': 'Rating must be 1-5'}), 400
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO complaint_ratings (complaint_id, rating, feedback_text, created_at) VALUES (?,?,?,datetime('now'))",
            (complaint_id, int(rating), feedback_text))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/complaints/<int:complaint_id>/rating', methods=['GET'])
def get_complaint_rating(complaint_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM complaint_ratings WHERE complaint_id=?", (complaint_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return jsonify(dict(row))
        return jsonify({})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/complaints/stats', methods=['GET'])
def complaint_stats():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM complaints")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) as count FROM complaints WHERE status='Pending'")
        pending = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) as count FROM complaints WHERE status='Resolved'")
        resolved = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) as count FROM complaints WHERE status='In Progress'")
        in_progress = cursor.fetchone()[0]
        cursor.execute("SELECT category, COUNT(*) as count FROM complaints GROUP BY category")
        by_category = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT area, COUNT(*) as count FROM complaints GROUP BY area ORDER BY count DESC LIMIT 10")
        by_area = [dict(r) for r in cursor.fetchall()]
        cursor.execute("""SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
            FROM complaints GROUP BY month ORDER BY month DESC LIMIT 6""")
        monthly = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify({'total': total, 'pending': pending, 'resolved': resolved, 'in_progress': in_progress,
            'by_category': by_category, 'by_area': by_area, 'monthly': monthly})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/categorize', methods=['POST'])
def categorize():
    data = request.json
    category, priority, sentiment = nlp_categorize_and_prioritize(data.get('title',''), data.get('description',''))
    return jsonify({'category': category, 'priority': priority, 'sentiment': sentiment})

@app.route('/api/funds/summary', methods=['GET'])
def fund_summary():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM budget_config ORDER BY id DESC LIMIT 1")
        budget = cursor.fetchone()
        cursor.execute("SELECT COALESCE(SUM(allocated_fund),0) as used FROM fund_allocations")
        used = cursor.fetchone()[0]
        conn.close()
        total = float(budget[1]) if budget else 50000000
        return jsonify({'total_budget': total, 'funds_used': float(used), 'remaining': total - float(used)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/funds/allocations', methods=['GET'])
def fund_allocations():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""SELECT fa.*, c.title as complaint_title, c.area, c.category, v.vendor_name
            FROM fund_allocations fa
            LEFT JOIN complaints c ON fa.complaint_id = c.id
            LEFT JOIN vendors v ON fa.vendor_id = v.id
            ORDER BY fa.id DESC""")
        rows = [dict(r) for r in cursor.fetchall()]
        for r in rows:
            if r.get('created_at'):
                r['created_at'] = r['created_at']
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/funds/allocations', methods=['POST'])
def add_allocation():
    try:
        data = request.json
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO fund_allocations (complaint_id, vendor_id, allocated_fund, work_status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (data['complaint_id'], data['vendor_id'], data['allocated_fund'], data.get('work_status','Assigned'), data.get('notes','')))
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/funds/area_spending', methods=['GET'])
def area_spending():
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""SELECT c.area, COALESCE(SUM(fa.allocated_fund),0) as total_spent
            FROM complaints c LEFT JOIN fund_allocations fa ON c.id = fa.complaint_id
            GROUP BY c.area ORDER BY total_spent DESC""")
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vendors', methods=['GET'])
def get_vendors():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM vendors ORDER BY performance_rating DESC")
        vendors = [dict(v) for v in cursor.fetchall()]
        conn.close()
        return jsonify(vendors)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/setup', methods=['POST'])
def setup_db():
    success = setup_database()
    if success:
        return jsonify({'success': True, 'message': 'Database setup complete with sample data!'})
    else:
        return jsonify({'error': 'Setup failed'}), 500

def setup_database():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
            category TEXT, priority TEXT DEFAULT 'Medium', area TEXT, citizen_name TEXT, citizen_contact TEXT,
            image_path TEXT, status TEXT DEFAULT 'Pending', updated_by TEXT DEFAULT '', sentiment INTEGER DEFAULT 3,
            latitude REAL, longitude REAL, created_at TEXT, resolved_at TEXT)""")
        
        # Backward compatibility for existing tables
        try: cursor.execute("ALTER TABLE complaints ADD COLUMN priority TEXT DEFAULT 'Medium'")
        except: pass
        try: cursor.execute("ALTER TABLE complaints ADD COLUMN updated_by TEXT DEFAULT ''")
        except: pass
        try: cursor.execute("ALTER TABLE complaints ADD COLUMN sentiment INTEGER DEFAULT 3")
        except: pass
        try: cursor.execute("ALTER TABLE complaints ADD COLUMN latitude REAL")
        except: pass
        try: cursor.execute("ALTER TABLE complaints ADD COLUMN longitude REAL")
        except: pass
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, 
            role TEXT DEFAULT 'admin', assigned_area TEXT DEFAULT '', assigned_category TEXT DEFAULT '', fullname TEXT DEFAULT '')""")
            
        # Backward compat for columns
        try: cursor.execute("ALTER TABLE users ADD COLUMN assigned_area TEXT DEFAULT ''")
        except: pass
        try: cursor.execute("ALTER TABLE users ADD COLUMN assigned_category TEXT DEFAULT ''")
        except: pass
        try: cursor.execute("ALTER TABLE users ADD COLUMN fullname TEXT DEFAULT ''")
        except: pass
        
        cursor.execute("""CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT, vendor_name TEXT NOT NULL, work_type TEXT,
            contract_value REAL, projects_completed INTEGER DEFAULT 0, performance_rating REAL DEFAULT 0.0,
            contact TEXT, registered_date TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS fund_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER, vendor_id INTEGER, allocated_fund REAL,
            work_status TEXT DEFAULT 'Assigned',
            notes TEXT, created_at TEXT,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id),
            FOREIGN KEY (vendor_id) REFERENCES vendors(id))""")
            
        cursor.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, action TEXT NOT NULL, 
            details TEXT, timestamp TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS budget_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT, total_budget REAL, fiscal_year TEXT, updated_at TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS complaint_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER NOT NULL,
            old_status TEXT, new_status TEXT, changed_by TEXT, changed_at TEXT,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS complaint_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER UNIQUE NOT NULL,
            rating INTEGER NOT NULL, feedback_text TEXT, created_at TEXT,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id))""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
            message TEXT NOT NULL, timestamp TEXT)""")
        
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
            password_hash = generate_password_hash(admin_password)
            cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?,?,?)", ('admin', password_hash, 'admin'))
            print(f"Created default admin user (username=admin password={admin_password})")

        cursor.execute("SELECT COUNT(*) FROM vendors")
        if cursor.fetchone()[0] == 0:
            vendors = [
                ('Bharat Infra Ltd','Road Repair',15000000,23,4.5,'9845012345','2020-01-15'),
                ('Green City Solutions','Garbage Management',8000000,18,4.2,'9876543210','2019-06-10'),
                ('PowerGrid Services','Electricity',12000000,31,4.7,'9900112233','2018-03-22'),
                ('AquaWorks Pvt Ltd','Water & Drainage',9500000,15,3.9,'9812345678','2021-09-05'),
                ('Metro Transit Corp','Transport',20000000,8,4.1,'9823456789','2022-01-01'),
                ('City Build Infra','Road Repair',11000000,12,3.7,'9834567890','2020-07-19'),
                ('CleanSweep India','Garbage Management',6000000,25,4.6,'9845678901','2019-02-28'),
            ]
            cursor.executemany("INSERT INTO vendors (vendor_name,work_type,contract_value,projects_completed,performance_rating,contact,registered_date) VALUES (?,?,?,?,?,?,?)", vendors)
        
        cursor.execute("SELECT COUNT(*) FROM budget_config")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO budget_config (total_budget,fiscal_year,updated_at) VALUES (50000000,'2024-25',datetime('now'))")
        
        cursor.execute("SELECT COUNT(*) FROM complaints")
        if cursor.fetchone()[0] == 0:
            samples = [
                ('Deep pothole on main road','Large pothole causing accidents near bus stand','Road','High','Whitefield','Ramesh Kumar','9801234567','Pending'),
                ('Garbage not collected for 3 days','Waste piling up near apartment complex','Garbage','Medium','Indiranagar','Priya Sharma','9812345678','Resolved'),
                ('Street light broken since a week','Dark road causing safety issues at night','Electricity','Medium','Koramangala','Arun Nair','9823456789','In Progress'),
                ('Water supply disrupted','No water supply for past 2 days in the locality','Water','High','Jayanagar','Sunita Reddy','9834567890','Pending'),
                ('Bus route changed without notice','Bus 310C no longer stops at our stop','Transport','Low','Hebbal','Mohan Das','9845678901','Pending'),
                ('Road flooded after rain','Drainage blocked causing waterlogging on main road','Water','Medium','BTM Layout','Kavya B','9856789012','Resolved'),
                ('Open manhole on footpath','Dangerous open manhole not repaired for 2 weeks','Road','High','Marathahalli','Vijay Singh','9867890123','In Progress'),
                ('Transformers making noise','Loud humming from transformer safety risk','Electricity','Medium','Electronic City','Neha Kapoor','9878901234','Pending'),
                ('Filthy public park','Public park bins overflowing unhygienic condition','Garbage','Low','Whitefield','Santosh G','9889012345','Resolved'),
                ('Water pipe leaking','Underground pipe burst causing water wastage','Water','Medium','Indiranagar','Ritu Mehta','9890123456','Pending'),
                ('Damaged road divider','Road divider broken causing traffic snarls','Road','Low','Koramangala','Arjun P','9901234567','In Progress'),
                ('No street lights in colony','Entire colony in darkness after 9PM','Electricity','Medium','Hebbal','Deepa M','9912345678','Resolved'),
            ]
            for i, s in enumerate(samples):
                days_ago = random.randint(1, 90)
                d = datetime.now() - timedelta(days=days_ago)
                status = s[7]
                if status == 'Resolved':
                    cursor.execute("INSERT INTO complaints (title,description,category,priority,area,citizen_name,citizen_contact,status,created_at,resolved_at) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))", (*s[:7], status, d.isoformat()))
                else:
                    cursor.execute("INSERT INTO complaints (title,description,category,priority,area,citizen_name,citizen_contact,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (*s[:7], status, d.isoformat()))
        
        cursor.execute("SELECT COUNT(*) FROM fund_allocations")
        if cursor.fetchone()[0] == 0:
            cursor.execute("SELECT id FROM complaints LIMIT 10")
            c_ids = [r[0] for r in cursor.fetchall()]
            cursor.execute("SELECT id FROM vendors")
            v_ids = [r[0] for r in cursor.fetchall()]
            ws_list = ['Completed','In Progress','Assigned','Delayed','Completed','Completed','In Progress','Assigned','Delayed','Completed']
            funds_list = [250000,180000,450000,320000,150000,780000,290000,410000,560000,340000]
            for i, cid in enumerate(c_ids):
                vid = v_ids[i % len(v_ids)]
                cursor.execute("INSERT INTO fund_allocations (complaint_id,vendor_id,allocated_fund,work_status,notes,created_at) VALUES (?,?,?,?,?,datetime('now'))",
                    (cid, vid, funds_list[i], ws_list[i], 'Work order issued'))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Setup error: {e}")
        return False

# Handle DB initialization for regular and serverless environments
try:
    if not os.path.exists(DB_FILE):
        setup_database()
except Exception as e:
    print(f"Serverless DB setup check skipped or failed: {e}")

if __name__ == '__main__':
    # Ensure local upload folders exist
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        
    print("✨ GRIP Backend Running in Local Mode (Port 5000)...")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
else:
    # Vercel / WSGI entry point
    app.logger.info("🚀 GRIP Backend initialized for Serverless/WSGI mode")
