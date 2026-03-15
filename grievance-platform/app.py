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
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PG = True
except ImportError:
    HAS_PG = False

# --- Twilio Configuration (Replace with your credentials) ------------------
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-me')

if os.environ.get('VERCEL'):
    app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
else:
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

# --- Database Configuration --------------------------------------------------
DB_URL = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')

def get_db():
    try:
        if DB_URL:
            # Postgres mode
            if not HAS_PG:
                logging.error("❌ Postgres requested but psycopg2 not installed")
                return None
            conn = psycopg2.connect(DB_URL)
            return conn
        else:
            # SQLite mode
            DB_FILE_NAME = 'grievance.db'
            if os.environ.get('VERCEL'):
                DB_FILE = os.path.join('/tmp', DB_FILE_NAME)
                if not os.path.exists(DB_FILE) and os.path.exists(DB_FILE_NAME):
                    import shutil
                    try:
                        shutil.copy2(DB_FILE_NAME, DB_FILE)
                        logging.info(f"✅ Copied {DB_FILE_NAME} to {DB_FILE}")
                    except Exception as e:
                        logging.error(f"❌ Failed to copy DB: {e}")
            else:
                APP_DIR = os.path.dirname(os.path.abspath(__file__))
                DB_FILE = os.path.join(APP_DIR, DB_FILE_NAME)
            
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            return conn
    except Exception as e:
        logging.error(f"DB Connection Error: {e}")
        return None

def db_execute(cursor, query, params=None):
    """Abstraction for SQL differences between SQLite and Postgres"""
    if params is None: params = []
    
    # Check dynamically for Postgres support
    is_pg = os.environ.get('DATABASE_URL') is not None or os.environ.get('POSTGRES_URL') is not None
    
    if is_pg:
        query = query.replace('?', '%s')
        query = query.replace("datetime('now')", "CURRENT_TIMESTAMP")
        query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        query = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        
        # Universal table check translation
        if "sqlite_master" in query and "name=" in query:
             query = "SELECT table_name as name FROM information_schema.tables WHERE table_schema='public' AND table_name=%s"
             
        # Add basic strftime support for the stats route
    
    cursor.execute(query, params)
    return cursor

def db_fetchall(cursor):
    is_pg = os.environ.get('DATABASE_URL') is not None or os.environ.get('POSTGRES_URL') is not None
    if is_pg:
        # For Postgres, we use RealDictCursor-like behavior manually if needed, 
        # but easier to just use standard cursor and dict mapping if dicts are needed.
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    else:
        return [dict(r) for r in cursor.fetchall()]

def db_fetchone(cursor):
    is_pg = os.environ.get('DATABASE_URL') is not None or os.environ.get('POSTGRES_URL') is not None
    row = cursor.fetchone()
    if not row: return None
    if is_pg:
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))
    else:
        return dict(row)

# --- Auth helpers & Audit ---------------------------------------------------

def log_audit(username, action, details):
    try:
        conn = get_db()
        cursor = conn.cursor()
        db_execute(cursor, "INSERT INTO audit_logs (username, action, details, timestamp) VALUES (?, ?, ?, datetime('now'))",
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
        db_execute(cursor, 'SELECT id, username, password_hash, role, assigned_area, assigned_category, fullname FROM users WHERE username=?', (username,))
        user = db_fetchone(cursor)
        conn.close()
        
        if user:
            if check_password_hash(user['password_hash'], password):
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
            else:
                app.logger.warning(f"❌ Login failed for {username}: Incorrect password")
        else:
            app.logger.warning(f"❌ Login failed for {username}: User not found")
        
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
        db_execute(cursor, 'SELECT id FROM users WHERE username=?', (username,))
        if db_fetchone(cursor):
            conn.close()
            return jsonify({'error': 'Phone number already registered'}), 409
            
        password_hash = generate_password_hash(password)
        db_execute(cursor, "INSERT INTO users (username, password_hash, role, fullname) VALUES (?,?,?,?)", (username, password_hash, 'citizen', fullname))
        
        # In Postgres, we need to handle lastrowid differently if we need it, 
        # but for simple registration we just need success.
        # Actually, let's use a safe way to get the ID if needed.
        if DB_URL:
            # For PG, we should have used RETURNING id, but let's just fetch it if needed
            db_execute(cursor, "SELECT id FROM users WHERE username=?", (username,))
            user_id = db_fetchone(cursor)['id']
        else:
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
        db_execute(cursor, """
            SELECT m.id, m.username, m.message, m.timestamp, u.fullname 
            FROM chat_messages m
            LEFT JOIN users u ON m.username = u.username 
            ORDER BY m.id DESC LIMIT 100
        """)
        msgs = db_fetchall(cursor)
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
        db_execute(cursor, "INSERT INTO chat_messages (username, message, timestamp) VALUES (?,?,?)",
                       (username, message, timestamp))
        if DB_URL:
             # Get the latest ID for this user/message
             db_execute(cursor, "SELECT MAX(id) as id FROM chat_messages WHERE username=?", (username,))
             msg_id = db_fetchone(cursor)['id']
        else:
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
        db_execute(cursor, "INSERT INTO chat_messages (username, message, timestamp) VALUES (?,?,?)",
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
        db_execute(cursor, 'SELECT username, role, fullname FROM users WHERE username=?', (username,))
        user = db_fetchone(cursor)
        conn.close()
        
        if user:
            return jsonify({'user': dict(user)})
        return jsonify({'user': data}) # Fallback to token if user not found in DB
    except:
        return jsonify({'user': None})

@app.route('/api/ping')
def api_ping():
    is_pg = os.environ.get('DATABASE_URL') is not None or os.environ.get('POSTGRES_URL') is not None
    db_conn_status = "untested"
    tables = []
    try:
        conn = get_db()
        if conn:
            db_conn_status = "connected"
            cursor = conn.cursor()
            # Introspect tables
            db_execute(cursor, "SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r['name'] for r in db_fetchall(cursor)]
            conn.close()
        else:
            db_conn_status = "failed"
    except Exception as e:
        db_conn_status = f"error: {str(e)}"
        
    return jsonify({
        'status': 'ok',
        'db_type': 'postgres' if is_pg else 'sqlite',
        'db_connection': db_conn_status,
        'tables_found': tables,
        'is_vercel': os.environ.get('VERCEL') is not None,
        'has_pg_driver': HAS_PG,
        'timestamp': datetime.now().isoformat()
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
        
        # Convert and validate numeric fields
        try:
            latitude = float(latitude) if latitude else None
        except:
            latitude = None
        try:
            longitude = float(longitude) if longitude else None
        except:
            longitude = None
        
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
        
        # Check if priority column exists - wrap in db_execute for PG support
        try:
            db_execute(cursor, "SELECT priority FROM complaints LIMIT 1")
        except:
            db_execute(cursor, "ALTER TABLE complaints ADD COLUMN priority TEXT DEFAULT 'Medium'")

        db_execute(cursor, """INSERT INTO complaints (title, description, category, priority, area, citizen_name, citizen_contact, image_path, status, sentiment, latitude, longitude, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', ?, ?, ?, datetime('now'))""",
            (title, description, category, priority, area, citizen_name, citizen_contact, image_path, sentiment, latitude, longitude))
        
        if DB_URL:
            # For PG, we can't easily get lastrowid without RETURNING, so we fetch the last id for this contact
            db_execute(cursor, "SELECT MAX(id) as id FROM complaints WHERE citizen_contact=?", (citizen_contact,))
            complaint_id = db_fetchone(cursor)['id']
        else:
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
        logging.info(f"🔍 Executing complaint query: {query} with params {params}")
        db_execute(cursor, query, params)
        complaints = db_fetchall(cursor)
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
        db_execute(cursor, "SELECT status FROM complaints WHERE id=?", (complaint_id,))
        row = db_fetchone(cursor)
        old_status = row['status'] if row else 'Unknown'
        if new_status == 'Resolved':
            db_execute(cursor, "UPDATE complaints SET status=?, updated_by=?, resolved_at=datetime('now') WHERE id=?", (new_status, updated_by_name, complaint_id))
        else:
            db_execute(cursor, "UPDATE complaints SET status=?, updated_by=? WHERE id=?", (new_status, updated_by_name, complaint_id))
        # Log to history
        db_execute(cursor, "INSERT INTO complaint_history (complaint_id, old_status, new_status, changed_by, changed_at) VALUES (?, ?, ?, ?, datetime('now'))",
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
        db_execute(cursor, "SELECT id, username, assigned_area, assigned_category FROM users WHERE role='official'")
        officials = db_fetchall(cursor)
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
            db_execute(cursor, "INSERT INTO users (username, password_hash, role, assigned_area, assigned_category) VALUES (?,?,'official',?,?)",
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
    db_execute(cursor, "SELECT username FROM users WHERE id=? AND role='official'", (id,))
    user = db_fetchone(cursor)
    if user:
        db_execute(cursor, "DELETE FROM users WHERE id=?", (id,))
        conn.commit()
        log_audit(request.user['username'], 'OFFICIAL_DELETED', f"Deleted official account: {user['username']}")
    conn.close()
    return jsonify({'success': True})

@app.route('/api/audit_logs', methods=['GET'])
@admin_required
def get_audit_logs():
    conn = get_db()
    cursor = conn.cursor()
    db_execute(cursor, "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 50")
    logs = db_fetchall(cursor)
    conn.close()
    return jsonify(logs)

@app.route('/api/export_complaints', methods=['GET'])
@admin_required
def export_complaints():
    try:
        conn = get_db()
        cursor = conn.cursor()
        db_execute(cursor, "SELECT id, title, category, priority, area, status, created_at FROM complaints")
        rows = db_fetchall(cursor)
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
        db_execute(cursor, "SELECT * FROM complaint_history WHERE complaint_id=? ORDER BY changed_at ASC", (complaint_id,))
        history = db_fetchall(cursor)
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
        # INSERT OR REPLACE handled by abstraction
        db_execute(cursor, "INSERT OR REPLACE INTO complaint_ratings (complaint_id, rating, feedback_text, created_at) VALUES (?,?,?,datetime('now'))",
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
        db_execute(cursor, "SELECT * FROM complaint_ratings WHERE complaint_id=?", (complaint_id,))
        row = db_fetchone(cursor)
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
        
        db_execute(cursor, "SELECT COUNT(*) as total FROM complaints")
        total = db_fetchone(cursor)['total']
        db_execute(cursor, "SELECT COUNT(*) as count FROM complaints WHERE status='Pending'")
        pending = db_fetchone(cursor)['count']
        db_execute(cursor, "SELECT COUNT(*) as count FROM complaints WHERE status='Resolved'")
        resolved = db_fetchone(cursor)['count']
        db_execute(cursor, "SELECT COUNT(*) as count FROM complaints WHERE status='In Progress'")
        in_progress = db_fetchone(cursor)['count']
        
        db_execute(cursor, "SELECT category, COUNT(*) as count FROM complaints GROUP BY category")
        by_category = db_fetchall(cursor)
        
        db_execute(cursor, "SELECT area, COUNT(*) as count FROM complaints GROUP BY area ORDER BY count DESC LIMIT 10")
        by_area = db_fetchall(cursor)
        
        db_execute(cursor, "SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count FROM complaints GROUP BY month ORDER BY month DESC LIMIT 6")
        monthly = db_fetchall(cursor)
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
        db_execute(cursor, "SELECT SUM(allocated_fund) as total_spent FROM fund_allocations")
        total_spent_row = db_fetchone(cursor)
        total_spent = total_spent_row['total_spent'] if total_spent_row and total_spent_row['total_spent'] is not None else 0

        db_execute(cursor, "SELECT total_budget FROM budget_config ORDER BY id DESC LIMIT 1")
        budget_row = db_fetchone(cursor)
        total_budget = budget_row['total_budget'] if budget_row else 50000000 # Default if no budget config

        conn.close()
        return jsonify({'total_budget': float(total_budget), 'funds_used': float(total_spent), 'remaining': float(total_budget) - float(total_spent)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/funds/allocations', methods=['GET'])
def fund_allocations():
    try:
        conn = get_db()
        cursor = conn.cursor()
        db_execute(cursor, """SELECT fa.*, c.title as complaint_title, c.area, c.category, v.vendor_name
            FROM fund_allocations fa
            LEFT JOIN complaints c ON fa.complaint_id = c.id
            LEFT JOIN vendors v ON fa.vendor_id = v.id
            ORDER BY fa.id DESC""")
        rows = db_fetchall(cursor)
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
        db_execute(cursor, """INSERT INTO fund_allocations (complaint_id, vendor_id, allocated_fund, work_status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))""",
            (data['complaint_id'], data['vendor_id'], data['allocated_fund'], data.get('work_status','Assigned'), data.get('notes','')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/funds/area_spending', methods=['GET'])
def area_spending():
    try:
        conn = get_db()
        cursor = conn.cursor()
        db_execute(cursor, """SELECT c.area, COALESCE(SUM(fa.allocated_fund),0) as total_spent
            FROM complaints c LEFT JOIN fund_allocations fa ON c.id = fa.complaint_id
            GROUP BY c.area ORDER BY total_spent DESC""")
        rows = db_fetchall(cursor)
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vendors', methods=['GET'])
def get_vendors():
    try:
        conn = get_db()
        cursor = conn.cursor()
        db_execute(cursor, "SELECT * FROM vendors ORDER BY vendor_name")
        rows = db_fetchall(cursor)
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/init-db')
def force_init_db():
    try:
        logging.info("Force-initializing database...")
        success, message = setup_database()
        if success:
            return jsonify({'status': 'success', 'message': message})
        else:
            return jsonify({'status': 'error', 'message': message}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def setup_database():
    try:
        conn = get_db()
        cursor = conn.cursor()
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
            category TEXT, priority TEXT DEFAULT 'Medium', area TEXT, citizen_name TEXT, citizen_contact TEXT,
            image_path TEXT, status TEXT DEFAULT 'Pending', updated_by TEXT DEFAULT '', sentiment INTEGER DEFAULT 3,
            latitude REAL, longitude REAL, created_at TEXT, resolved_at TEXT)""")
        
        # Backward compatibility for existing tables (only relevant for SQLite)
        if not DB_URL:
            columns = [
                ("priority", "TEXT DEFAULT 'Medium'"),
                ("updated_by", "TEXT DEFAULT ''"),
                ("sentiment", "INTEGER DEFAULT 3"),
                ("latitude", "REAL"),
                ("longitude", "REAL")
            ]
            for col_name, col_def in columns:
                try:
                    cursor.execute(f"ALTER TABLE complaints ADD COLUMN {col_name} {col_def}")
                except:
                    pass
        
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, 
            role TEXT DEFAULT 'admin', assigned_area TEXT DEFAULT '', assigned_category TEXT DEFAULT '', fullname TEXT DEFAULT '')""")
            
        # Backward compat for columns
        if not DB_URL:
            try: cursor.execute("ALTER TABLE users ADD COLUMN assigned_area TEXT DEFAULT ''")
            except: pass
            try: cursor.execute("ALTER TABLE users ADD COLUMN assigned_category TEXT DEFAULT ''")
            except: pass
            try: cursor.execute("ALTER TABLE users ADD COLUMN fullname TEXT DEFAULT ''")
            except: pass
        
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT, vendor_name TEXT NOT NULL, work_type TEXT,
            contract_value REAL, projects_completed INTEGER DEFAULT 0, performance_rating REAL DEFAULT 0.0,
            contact TEXT, registered_date TEXT)""")
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS fund_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER, vendor_id INTEGER, allocated_fund REAL,
            work_status TEXT DEFAULT 'Assigned',
            notes TEXT, created_at TEXT)""")
            
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, action TEXT NOT NULL, 
            details TEXT, timestamp TEXT)""")
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS budget_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT, total_budget REAL, fiscal_year TEXT, updated_at TEXT)""")
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS complaint_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER NOT NULL,
            old_status TEXT, new_status TEXT, changed_by TEXT, changed_at TEXT)""")
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS complaint_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, complaint_id INTEGER UNIQUE NOT NULL,
            rating INTEGER NOT NULL, feedback_text TEXT, created_at TEXT)""")
        db_execute(cursor, """CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
            message TEXT NOT NULL, timestamp TEXT)""")
        
        db_execute(cursor, "SELECT id, username, password_hash FROM users WHERE username='admin'")
        admin = db_fetchone(cursor)
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
        if not admin:
            password_hash = generate_password_hash(admin_password)
            db_execute(cursor, "INSERT INTO users (username, password_hash, role) VALUES (?,?,?)", ('admin', password_hash, 'admin'))
            logging.info(f"✅ Created default admin user (username=admin)")
        else:
            # Force hash if it looks like plain text
            if not admin['password_hash'].startswith(('pbkdf2:sha256:', 'scrypt:')):
                logging.info("Updating admin password to hashed format...")
                new_hash = generate_password_hash(admin_password)
                db_execute(cursor, "UPDATE users SET password_hash=? WHERE id=?", (new_hash, admin['id']))

        db_execute(cursor, "SELECT COUNT(*) as count FROM vendors")
        if db_fetchone(cursor)['count'] == 0:
            vendors = [
                ('Bharat Infra Ltd','Road Repair',15000000,23,4.5,'9845012345','2020-01-15'),
                ('Green City Solutions','Garbage Management',8000000,18,4.2,'9876543210','2019-06-10'),
                ('PowerGrid Services','Electricity',12000000,31,4.7,'9900112233','2018-03-22'),
                ('AquaWorks Pvt Ltd','Water & Drainage',9500000,15,3.9,'9812345678','2021-09-05'),
                ('Metro Transit Corp','Transport',20000000,8,4.1,'9823456789','2022-01-01'),
                ('City Build Infra','Road Repair',11000000,12,3.7,'9834567890','2020-07-19'),
                ('CleanSweep India','Garbage Management',6000000,25,4.6,'9845678901','2019-02-28'),
            ]
            for v in vendors:
                db_execute(cursor, "INSERT INTO vendors (vendor_name,work_type,contract_value,projects_completed,performance_rating,contact,registered_date) VALUES (?,?,?,?,?,?,?)", v)
        
        db_execute(cursor, "SELECT COUNT(*) as count FROM budget_config")
        if db_fetchone(cursor)['count'] == 0:
            db_execute(cursor, "INSERT INTO budget_config (total_budget,fiscal_year,updated_at) VALUES (50000000,'2024-25',datetime('now'))")
        
        db_execute(cursor, "SELECT COUNT(*) as count FROM complaints")
        if db_fetchone(cursor)['count'] == 0:
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
            for s in samples:
                days_ago = random.randint(1, 90)
                d = datetime.now() - timedelta(days=days_ago)
                status = s[7]
                if status == 'Resolved':
                    db_execute(cursor, "INSERT INTO complaints (title,description,category,priority,area,citizen_name,citizen_contact,status,created_at,resolved_at) VALUES (?,?,?,?,?,?,?,?,?,datetime('now'))", (*s[:7], status, d.isoformat()))
                else:
                    db_execute(cursor, "INSERT INTO complaints (title,description,category,priority,area,citizen_name,citizen_contact,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (*s[:7], status, d.isoformat()))
        
        db_execute(cursor, "SELECT COUNT(*) as count FROM fund_allocations")
        if db_fetchone(cursor)['count'] == 0:
            db_execute(cursor, "SELECT id FROM complaints LIMIT 10")
            c_ids = [r['id'] for r in db_fetchall(cursor)]
            db_execute(cursor, "SELECT id FROM vendors")
            v_ids = [r['id'] for r in db_fetchall(cursor)]
            ws_list = ['Completed','In Progress','Assigned','Delayed','Completed','Completed','In Progress','Assigned','Delayed','Completed']
            funds_list = [250000,180000,450000,320000,150000,780000,290000,410000,560000,340000]
            for i, cid in enumerate(c_ids):
                vid = v_ids[i % len(v_ids)]
                db_execute(cursor, "INSERT INTO fund_allocations (complaint_id,vendor_id,allocated_fund,work_status,notes,created_at) VALUES (?,?,?,?,?,datetime('now'))",
                    (cid, vid, funds_list[i], ws_list[i], 'Work order issued'))
        
        conn.commit()
        conn.close()
        return True, "Database setup complete with sample data!"
    except Exception as e:
        error_msg = f"Setup error: {str(e)}"
        logging.error(error_msg)
        return False, error_msg

# Handle DB initialization
def init_db():
    try:
        conn = get_db()
        if not conn: 
            logging.error("❌ init_db: Could not get DB connection")
            return
        cursor = conn.cursor()
        
        # Aggressive check: try to SELECT from users. If it fails, we definitely need setup.
        try:
            db_execute(cursor, "SELECT 1 FROM users LIMIT 1")
            logging.info("✅ Database already initialized (users table accessible).")
        except Exception as query_error:
            logging.info(f"💾 Users table missing or inaccessible ({query_error}), triggering setup...")
            setup_database()
            
        conn.close()
    except Exception as e:
        logging.error(f"❌ DB init error: {e}")

@app.before_request
def first_request_init():
    if not hasattr(app, '_db_initialized'):
        logging.info("🚀 First request - initializing database check...")
        init_db()
        app._db_initialized = True

if __name__ == '__main__':
    # Ensure local upload folders exist
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        
    print("✨ GRIP Backend Running in Local Mode (Port 5000)...")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
else:
    # Vercel / WSGI entry point
    app.logger.info("🚀 GRIP Backend initialized for Serverless/WSGI mode")
    # Call init_db once at startup for Vercel too
    with app.app_context():
        init_db()
