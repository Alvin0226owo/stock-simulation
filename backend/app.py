from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
import yfinance as yf
from datetime import datetime, timedelta
import bcrypt
from database import db
from models import User, Portfolio, Transaction
from datetime import datetime
from sqlalchemy import text

app = Flask(__name__)
CORS(app)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stocktracker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = '401e606432da9fc76abfb83eb93705993ca282d99bf9aa422b09640ace123877' 
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=30)

# Initialize extensions
db.init_app(app)

# Initialize JWT manager
jwt = JWTManager(app)

# Add JWT error handlers
@jwt.invalid_token_loader
def invalid_token_callback(error):
    print(f"Invalid token error: {error}")
    return jsonify({
        'error': 'Invalid token',
        'message': str(error)
    }), 422

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    print(f"Expired token. Header: {jwt_header}, Payload: {jwt_payload}")
    return jsonify({
        'error': 'Token has expired',
        'message': 'Please log in again'
    }), 422

@jwt.unauthorized_loader
def unauthorized_callback(error):
    print(f"Missing token error: {error}")
    return jsonify({
        'error': 'Missing token',
        'message': str(error)
    }), 422

# Ensure database tables exist
def init_db():
    with app.app_context():
        try:
            # Verify database connection
            db.session.execute(text('SELECT 1'))
            print("Database connection verified")
            
            # Create tables
            db.create_all()
            print("Database tables created successfully")
            
            # Commit any pending transactions
            db.session.commit()
        except Exception as e:
            print(f"Error initializing database: {e}")
            db.session.rollback()
            raise

init_db()

@app.route('/api/register', methods=['POST'])
def register():
    print("Received registration request")
    data = request.get_json()
    print("Request data:", data)
    
    if not data or 'email' not in data or 'password' not in data:
        print("Missing email or password in request")
        return jsonify({'error': 'Email and password are required'}), 400
    
    if User.query.filter_by(email=data['email']).first():
        print(f"Email {data['email']} already exists")
        return jsonify({'error': 'Email already exists'}), 400
    
    try:
        hashed_password = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
        
        new_user = User(
            email=data['email'],
            password=hashed_password,
            virtual_balance=1000000  # Starting balance of $1M
        )
        
        db.session.add(new_user)
        db.session.commit()
        print(f"Successfully created user with email {data['email']}")
        return jsonify({'message': 'User created successfully'}), 201
    except Exception as e:
        print(f"Error creating user: {str(e)}")
        db.session.rollback()
        return jsonify({'error': 'Failed to create user'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    
    if user and bcrypt.checkpw(data['password'].encode('utf-8'), user.password):
        # Convert user.id to string when creating the token
        access_token = create_access_token(identity=str(user.id))
        return jsonify({
            'token': access_token,
            'user_id': str(user.id)
        }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/api/stock/<symbol>')
def get_stock_data(symbol):
    period = request.args.get('period', '1d')
    interval = request.args.get('interval', '5m')
    stock = yf.Ticker(symbol)
    
    try:
        # Get historical data with interval
        hist = stock.history(period=period, interval=interval)
        
        if hist.empty:
            return jsonify({'error': 'No data available for this period'}), 404
        
        # Format data for frontend
        data = {
            'prices': hist['Close'].tolist(),
            'dates': hist.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            'info': stock.info
        }
        
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/portfolio', methods=['GET'])
@jwt_required()
def get_portfolio():
    try:
        # Get and validate user ID from token
        user_id = get_jwt_identity()
        if not user_id:
            print("No user ID in token")
            return jsonify({'error': 'Invalid token'}), 422
        
        # Convert string user_id back to integer
        try:
            user_id = int(user_id)
        except ValueError:
            print("Invalid user ID format in token")
            return jsonify({'error': 'Invalid token format'}), 422
        
        print(f"Processing portfolio request for user {user_id}")
        print("Headers:", dict(request.headers))
        
        # Verify database connection
        try:
            db.session.execute(text('SELECT 1'))
            print("Database connection verified")
        except Exception as e:
            print(f"Database connection error: {e}")
            return jsonify({'error': 'Database connection error'}), 500
        
        # Check if user exists
        user = User.query.get(user_id)
        if not user:
            print(f"User {user_id} not found in database")
            return jsonify({'error': 'User not found'}), 404
            
        # Get portfolio items
        portfolio_items = Portfolio.query.filter_by(user_id=user_id).all()
        print(f"Found {len(portfolio_items)} portfolio items")
        
        # Initialize response data
        portfolio_data = []
        total_value = user.virtual_balance
        
        # Process each portfolio item
        for item in portfolio_items:
            try:
                print(f"Processing {item.symbol}")
                stock = yf.Ticker(item.symbol)
                
                # Get current price
                current_price = None
                try:
                    hist = stock.history(period='1d')
                    if not hist.empty:
                        current_price = hist['Close'].iloc[-1]
                        print(f"Got price from history: {current_price}")
                except Exception as e:
                    print(f"Error getting price from history: {e}")
                    
                if current_price is None:
                    try:
                        current_price = stock.info.get('regularMarketPrice')
                        print(f"Got price from info: {current_price}")
                    except Exception as e:
                        print(f"Error getting price from info: {e}")
                
                if current_price is None:
                    print(f"Could not get price for {item.symbol}")
                    continue
                
                # Calculate values
                value = item.shares * current_price
                total_value += value
                gain_loss = value - (item.average_price * item.shares)
                
                # Add to portfolio data
                portfolio_data.append({
                    'symbol': item.symbol,
                    'shares': item.shares,
                    'avg_price': float(item.average_price),
                    'current_price': float(current_price),
                    'value': float(value),
                    'gain_loss': float(gain_loss)
                })
                print(f"Added {item.symbol} to portfolio data")
                
            except Exception as e:
                print(f"Error processing {item.symbol}: {str(e)}")
                continue
        
        # Prepare response
        response_data = {
            'portfolio': portfolio_data,
            'total_value': float(total_value),
            'cash_balance': float(user.virtual_balance)
        }
        
        print("Final response data:", response_data)
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Portfolio error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/trade', methods=['POST'])
@jwt_required()
def trade():
    user_id = get_jwt_identity()
    data = request.get_json()
    
    try:
        user = User.query.get(user_id)
        stock = yf.Ticker(data['symbol'])
        
        # Try different methods to get the current price
        current_price = None
        try:
            current_price = stock.info.get('regularMarketPrice')
            if current_price is None:
                current_price = stock.info.get('currentPrice')
            if current_price is None:
                hist = stock.history(period='1d')
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
        except Exception as e:
            print(f"Error fetching price for {data['symbol']}: {str(e)}")
            
        if current_price is None:
            return jsonify({'error': f'Could not fetch current price for {data["symbol"]}'}), 400
            
        shares = int(data['shares'])
        total_cost = current_price * shares
        
        if data['action'] == 'buy':
            if total_cost > user.virtual_balance:
                return jsonify({
                    'error': f'Insufficient funds. Cost: ${total_cost:.2f}, Balance: ${user.virtual_balance:.2f}'
                }), 400
            
            portfolio_item = Portfolio.query.filter_by(
                user_id=user_id, symbol=data['symbol']).first()
            
            if portfolio_item:
                new_shares = portfolio_item.shares + shares
                new_avg_price = ((portfolio_item.average_price * portfolio_item.shares) + 
                               (current_price * shares)) / new_shares
                portfolio_item.shares = new_shares
                portfolio_item.average_price = new_avg_price
            else:
                portfolio_item = Portfolio(
                    user_id=user_id,
                    symbol=data['symbol'],
                    shares=shares,
                    average_price=current_price
                )
                db.session.add(portfolio_item)
            
            user.virtual_balance -= total_cost
            
        elif data['action'] == 'sell':
            portfolio_item = Portfolio.query.filter_by(
                user_id=user_id, symbol=data['symbol']).first()
            
            if not portfolio_item:
                return jsonify({'error': 'You do not own this stock'}), 400
                
            if portfolio_item.shares < shares:
                return jsonify({
                    'error': f'Insufficient shares. You own {portfolio_item.shares} shares'
                }), 400
            
            portfolio_item.shares -= shares
            user.virtual_balance += total_cost
            
            if portfolio_item.shares == 0:
                db.session.delete(portfolio_item)
        
        transaction = Transaction(
            user_id=user_id,
            symbol=data['symbol'],
            shares=shares,
            price=current_price,
            action=data['action']
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({
            'message': 'Trade executed successfully',
            'new_balance': user.virtual_balance,
            'transaction': {
                'symbol': data['symbol'],
                'shares': shares,
                'price': current_price,
                'total': total_cost,
                'action': data['action']
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Trade error: {str(e)}")
        return jsonify({'error': 'Failed to execute trade. Please try again.'}), 500

@app.route('/api/test-auth', methods=['GET'])
@jwt_required()
def test_auth():
    user_id = get_jwt_identity()
    return jsonify({
        'message': 'Authentication successful',
        'user_id': user_id
    })

@app.route("/testingbackend")
def testingbackend():
    return("<h1>Testing Backend</h1>")

if __name__ == '__main__':
    app.run(debug=True) 