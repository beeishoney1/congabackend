# app.py - Diamond Shop Backend API Only
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import requests
import os
from werkzeug.security import generate_password_hash, check_password_hash
import time  # Add this import
from flask_cors import CORS


app = Flask(__name__)
# Configure CORS to allow requests from your Netlify frontend
CORS(app, resources={
    r"/*": {
        "origins": [
            "https://congashop.netlify.app",
            "http://localhost:3000",  # For local development
            "http://localhost:5173"   # For Vite development
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# Configuration
DATABASE_URL = "postgresql://postgres.mroyctjvmcuyuyuyumvj:congashop123laoidnfo2ndo@aws-1-eu-north-1.pooler.supabase.com:6543/postgres"
TELEGRAM_BOT_TOKEN = "8042603273:AAFZpfKNICr57kYBkexm1MmcJLU_2mTSRmA"

# Database connection function
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# Initialize database tables
def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                telegram_id VARCHAR(50) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create diamond_prices table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS diamond_prices (
                id SERIAL PRIMARY KEY,
                game_name VARCHAR(100) NOT NULL,
                server_name VARCHAR(100) NOT NULL,
                amount INTEGER NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create purchases table - ADD payment_number and payment_name columns
        cur.execute("""
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                game_id VARCHAR(100) NOT NULL,
                server_id VARCHAR(100) NOT NULL,
                amount INTEGER NOT NULL,
                payment_slip_url TEXT,
                payment_number VARCHAR(50),  -- NEW COLUMN
                payment_name VARCHAR(100),   -- NEW COLUMN
                status VARCHAR(20) DEFAULT 'Pending',
                admin_notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create admin users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Add some sample diamond prices
        cur.execute("SELECT COUNT(*) FROM diamond_prices")
        if cur.fetchone()[0] == 0:
            sample_prices = [
                ('Mobile Legends', 'Server 1', 100, 10.00),
                ('Mobile Legends', 'Server 1', 500, 45.00),
                ('Mobile Legends', 'Server 1', 1000, 85.00),
                ('PUBG Mobile', 'Asia', 100, 12.00),
                ('PUBG Mobile', 'Asia', 500, 55.00),
                ('PUBG Mobile', 'Asia', 1000, 100.00),
            ]
            for price in sample_prices:
                cur.execute(
                    "INSERT INTO diamond_prices (game_name, server_name, amount, price) VALUES (%s, %s, %s, %s)",
                    price
                )
        
        conn.commit()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Error initializing database: {e}")
    finally:
        cur.close()
        conn.close()

# Send Telegram notification (called by API endpoints, not a bot)
def send_telegram_notification(telegram_id, message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": telegram_id,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")
        return False

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

# User Registration
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    telegram_id = data.get('telegram_id')
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if username already exists
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            return jsonify({'error': 'Username already exists'}), 400
        
        # Hash password and create user
        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, password_hash, telegram_id) VALUES (%s, %s, %s) RETURNING id",
            (username, password_hash, telegram_id)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        
        return jsonify({'message': 'User created successfully', 'user_id': user_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# User Login
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get user by username
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check if user is admin
        cur.execute("SELECT * FROM admin_users WHERE user_id = %s AND is_active = TRUE", (user['id'],))
        is_admin = cur.fetchone() is not None
        
        user_data = {
            'id': user['id'],
            'username': user['username'],
            'telegram_id': user['telegram_id'],
            'is_admin': is_admin
        }
        
        return jsonify({'message': 'Login successful', 'user': user_data}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/buy-diamond', methods=['POST'])
def buy_diamond():
    try:
        # Get data from JSON instead of form data
        data = request.get_json()
        user_id = data.get('userId')
        package_id = data.get('packageId')
        game_id = data.get('gameId')
        server_id = data.get('serverId')
        payment_number = data.get('paymentNumber')  # NEW FIELD
        payment_name = data.get('paymentName')      # NEW FIELD

        print(f"Received purchase request: user_id={user_id}, package_id={package_id}, game_id={game_id}, server_id={server_id}")

        if not all([user_id, package_id, game_id, server_id, payment_number, payment_name]):
            return jsonify({'error': 'Missing required fields'}), 400

        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # Get the amount from diamond_prices table using package_id
            cur.execute("SELECT amount FROM diamond_prices WHERE id = %s", (package_id,))
            result = cur.fetchone()
            if not result:
                return jsonify({'error': 'Invalid package ID'}), 400
            amount = result[0]
            
            # Create purchase record with payment number and name
            cur.execute(
                """INSERT INTO purchases (user_id, game_id, server_id, amount, payment_number, payment_name) 
                   VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                (user_id, game_id, server_id, amount, payment_number, payment_name)
            )
            purchase_id = cur.fetchone()[0]
            conn.commit()

            # Get user telegram_id for notification
            cur.execute("SELECT telegram_id FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            telegram_id = user[0] if user else None

            if telegram_id:
                message = (
                    f"🎮 Diamond Purchase Submitted!\n\n"
                    f"Game ID: {game_id}\nServer: {server_id}\nAmount: {amount}\n"
                    f"Payment: {payment_number} ({payment_name})\nStatus: Pending\n\n"
                    f"We'll process your order soon!"
                )
                send_telegram_notification(telegram_id, message)

            return jsonify({'message': 'Purchase submitted successfully', 'purchase_id': purchase_id}), 201
            
        except Exception as e:
            conn.rollback()
            print(f"Database error in buy-diamond: {str(e)}")
            return jsonify({'error': f'Database error: {str(e)}'}), 500
        finally:
            cur.close()
            conn.close()
            
    except Exception as e:
        print(f"General error in buy-diamond: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# Get Purchase History
@app.route('/purchase-history', methods=['GET'])
def purchase_history():
    user_id = request.args.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'User ID is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute(
            """SELECT p.*, u.username 
               FROM purchases p 
               JOIN users u ON p.user_id = u.id 
               WHERE p.user_id = %s 
               ORDER BY p.created_at DESC""",
            (user_id,)
        )
        purchases = cur.fetchall()
        
        return jsonify({'purchases': purchases}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# Admin - Get All Purchases
@app.route('/admin/purchases', methods=['GET'])
def admin_purchases():
    status = request.args.get('status', 'Pending')
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if status == 'All':
            cur.execute(
                """SELECT p.*, u.username 
                   FROM purchases p 
                   JOIN users u ON p.user_id = u.id 
                   ORDER BY p.created_at DESC"""
            )
        else:
            cur.execute(
                """SELECT p.*, u.username 
                   FROM purchases p 
                   JOIN users u ON p.user_id = u.id 
                   WHERE p.status = %s 
                   ORDER BY p.created_at DESC""",
                (status,)
            )
        
        purchases = cur.fetchall()
        return jsonify({'purchases': purchases}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

        # Add this to your Flask app.py
# Admin - Get All Users
@app.route('/admin/users', methods=['GET'])
def admin_users():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute(
            """SELECT u.*, COUNT(p.id) as order_count 
               FROM users u 
               LEFT JOIN purchases p ON u.id = p.user_id 
               GROUP BY u.id 
               ORDER BY u.created_at DESC"""
        )
        users = cur.fetchall()
        return jsonify({'users': users}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# Admin - Update Purchase Status
@app.route('/admin/update-purchase', methods=['POST'])
def admin_update_purchase():
    data = request.get_json()
    purchase_id = data.get('purchase_id')
    status = data.get('status')
    admin_notes = data.get('admin_notes', '')
    
    if not purchase_id or not status:
        return jsonify({'error': 'Purchase ID and status are required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Update purchase status
        cur.execute(
            """UPDATE purchases 
               SET status = %s, admin_notes = %s, updated_at = CURRENT_TIMESTAMP 
               WHERE id = %s 
               RETURNING user_id, game_id, server_id, amount, payment_number, payment_name""",
            (status, admin_notes, purchase_id)
        )
        purchase = cur.fetchone()
        
        if not purchase:
            return jsonify({'error': 'Purchase not found'}), 404
        
        user_id, game_id, server_id, amount, payment_number, payment_name = purchase
        
        # Get user telegram_id for notification
        cur.execute("SELECT telegram_id FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        telegram_id = user[0] if user else None
        
        if telegram_id:
            message = f"🎮 Diamond Purchase Update!\n\nGame ID: {game_id}\nServer: {server_id}\nAmount: {amount}\nPayment: {payment_number} ({payment_name})\nStatus: {status}\n\nNotes: {admin_notes}"
            send_telegram_notification(telegram_id, message)
        
        conn.commit()
        return jsonify({'message': 'Purchase updated successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# Admin - CRUD Diamond Prices
@app.route('/admin/diamond-prices', methods=['GET', 'POST', 'PUT', 'DELETE'])
def admin_diamond_prices():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # GET - Get all diamond prices
        if request.method == 'GET':
            cur.execute("SELECT * FROM diamond_prices ORDER BY game_name, server_name, amount")
            prices = cur.fetchall()
            return jsonify({'prices': prices}), 200
        
        data = request.get_json()
        
        # POST - Create new diamond price
        if request.method == 'POST':
            game_name = data.get('game_name')
            server_name = data.get('server_name')
            amount = data.get('amount')
            price = data.get('price')
            
            if not all([game_name, server_name, amount, price]):
                return jsonify({'error': 'All fields are required'}), 400
            
            cur.execute(
                """INSERT INTO diamond_prices (game_name, server_name, amount, price) 
                   VALUES (%s, %s, %s, %s) 
                   RETURNING id""",
                (game_name, server_name, amount, price)
            )
            price_id = cur.fetchone()['id']
            conn.commit()
            return jsonify({'message': 'Price created successfully', 'price_id': price_id}), 201
        
        # PUT - Update diamond price
        if request.method == 'PUT':
            price_id = data.get('id')
            game_name = data.get('game_name')
            server_name = data.get('server_name')
            amount = data.get('amount')
            price = data.get('price')
            
            if not all([price_id, game_name, server_name, amount, price]):
                return jsonify({'error': 'All fields are required'}), 400
            
            cur.execute(
                """UPDATE diamond_prices 
                   SET game_name = %s, server_name = %s, amount = %s, price = %s, updated_at = CURRENT_TIMESTAMP 
                   WHERE id = %s""",
                (game_name, server_name, amount, price, price_id)
            )
            conn.commit()
            return jsonify({'message': 'Price updated successfully'}), 200
        
        # DELETE - Delete diamond price
        if request.method == 'DELETE':
            price_id = data.get('id')
            
            if not price_id:
                return jsonify({'error': 'Price ID is required'}), 400
            
            cur.execute("DELETE FROM diamond_prices WHERE id = %s", (price_id,))
            conn.commit()
            return jsonify({'message': 'Price deleted successfully'}), 200
            
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# Admin - Filter Purchases by User
@app.route('/admin/filter-purchases', methods=['GET'])
def admin_filter_purchases():
    username = request.args.get('username')
    
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute(
            """SELECT p.*, u.username 
               FROM purchases p 
               JOIN users u ON p.user_id = u.id 
               WHERE u.username ILIKE %s 
               ORDER BY p.created_at DESC""",
            (f'%{username}%',)
        )
        purchases = cur.fetchall()
        
        return jsonify({'purchases': purchases}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# Get Diamond Prices (Public endpoint)
@app.route('/diamond-prices', methods=['GET'])
def get_diamond_prices():
    game_name = request.args.get('game_name')
    server_name = request.args.get('server_name')
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if game_name and server_name:
            cur.execute(
                "SELECT * FROM diamond_prices WHERE game_name = %s AND server_name = %s ORDER BY amount",
                (game_name, server_name)
            )
        elif game_name:
            cur.execute(
                "SELECT * FROM diamond_prices WHERE game_name = %s ORDER BY server_name, amount",
                (game_name,)
            )
        else:
            cur.execute("SELECT * FROM diamond_prices ORDER BY game_name, server_name, amount")
        
        prices = cur.fetchall()
        return jsonify({'prices': prices}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)