from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'foodie-dash-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///food_ordering.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(15))
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class FoodItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50))
    image_url = db.Column(db.String(200))
    is_available = db.Column(db.Boolean, default=True)
    rating = db.Column(db.Float, default=4.5)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    user = db.relationship('User', backref='orders')
    items = db.relationship('OrderItem', backref='order', lazy=True)
    
class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    food_item_id = db.Column(db.Integer, db.ForeignKey('food_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    food_item = db.relationship('FoodItem', backref='order_items')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def home():
    featured_items = FoodItem.query.filter_by(is_available=True).limit(6).all()
    return render_template('index.html', featured_items=featured_items)

@app.route('/menu')
def menu():
    categories = ['All', 'Pizza', 'Burger', 'Pasta', 'Sushi', 'Salad', 'Dessert']
    selected_category = request.args.get('category', 'All')
    
    if selected_category == 'All':
        items = FoodItem.query.filter_by(is_available=True).all()
    else:
        items = FoodItem.query.filter_by(category=selected_category, is_available=True).all()
    
    return render_template('menu.html', items=items, categories=categories, selected_category=selected_category)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    data = request.json
    item_id = data.get('item_id')
    quantity = data.get('quantity', 1)
    
    if 'cart' not in session:
        session['cart'] = {}
    
    cart = session['cart']
    cart[str(item_id)] = cart.get(str(item_id), 0) + quantity
    session['cart'] = cart
    
    # Calculate total cart count
    cart_count = sum(cart.values())
    
    return jsonify({'success': True, 'cart_count': cart_count})

@app.route('/cart')
def cart():
    cart_items = []
    total = 0
    
    if 'cart' in session:
        for item_id, quantity in session['cart'].items():
            food_item = FoodItem.query.get(int(item_id))
            if food_item:
                item_total = food_item.price * quantity
                total += item_total
                cart_items.append({
                    'id': food_item.id,
                    'name': food_item.name,
                    'description': food_item.description,
                    'price': food_item.price,
                    'quantity': quantity,
                    'total': item_total,
                    'image_url': food_item.image_url
                })
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/update_cart', methods=['POST'])
def update_cart():
    data = request.json
    item_id = data.get('item_id')
    quantity = data.get('quantity')
    
    if 'cart' in session and str(item_id) in session['cart']:
        if quantity <= 0:
            del session['cart'][str(item_id)]
        else:
            session['cart'][str(item_id)] = quantity
        session.modified = True
        
        # Calculate new total
        new_total = 0
        for iid, qty in session['cart'].items():
            item = FoodItem.query.get(int(iid))
            if item:
                new_total += item.price * qty
        
        cart_count = sum(session['cart'].values())
        
        return jsonify({'success': True, 'cart_count': cart_count, 'total': new_total})
    
    return jsonify({'success': False})

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if request.method == 'POST':
        if 'cart' not in session or not session['cart']:
            flash('Your cart is empty!', 'error')
            return redirect(url_for('menu'))
        
        # Get delivery details
        address = request.form.get('address')
        phone = request.form.get('phone')
        
        # Update user's address and phone if provided
        if address:
            current_user.address = address
        if phone:
            current_user.phone = phone
        db.session.commit()
        
        total = 0
        order_items = []
        
        for item_id, quantity in session['cart'].items():
            food_item = FoodItem.query.get(int(item_id))
            if food_item:
                item_total = food_item.price * quantity
                total += item_total
                order_items.append({
                    'item': food_item,
                    'quantity': quantity,
                    'price': food_item.price
                })
        
        # Create order
        order = Order(
            user_id=current_user.id,
            total_amount=total,
            status='confirmed'
        )
        db.session.add(order)
        db.session.commit()
        
        # Create order items
        for item in order_items:
            order_item = OrderItem(
                order_id=order.id,
                food_item_id=item['item'].id,
                quantity=item['quantity'],
                price=item['price']
            )
            db.session.add(order_item)
        
        db.session.commit()
        
        # Clear cart
        session.pop('cart', None)
        
        flash('Order placed successfully! Thank you for shopping with us.', 'success')
        return redirect(url_for('orders'))
    
    # GET request - show checkout form
    cart_items = []
    total = 0
    
    if 'cart' in session:
        for item_id, quantity in session['cart'].items():
            food_item = FoodItem.query.get(int(item_id))
            if food_item:
                item_total = food_item.price * quantity
                total += item_total
                cart_items.append({
                    'id': food_item.id,
                    'name': food_item.name,
                    'price': food_item.price,
                    'quantity': quantity,
                    'total': item_total
                })
    
    return render_template('checkout.html', cart_items=cart_items, total=total, user=current_user)

@app.route('/orders')
@login_required
def orders():
    user_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.order_date.desc()).all()
    return render_template('orders.html', orders=user_orders)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Welcome back!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        
        flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        user = User(username=username, email=email, phone=phone)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('cart', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('home'))

# Initialize database
def init_db():
    with app.app_context():
        db.create_all()
        
        # Add sample food items if database is empty
        if FoodItem.query.count() == 0:
            sample_items = [
                FoodItem(name='Margherita Pizza', description='Fresh mozzarella, tomatoes, basil, extra virgin olive oil', price=12.99, category='Pizza', image_url='https://images.unsplash.com/photo-1604382355076-af4b0eb60143?w=400', rating=4.7),
                FoodItem(name='Pepperoni Pizza', description='Pepperoni, mozzarella, tomato sauce, oregano', price=14.99, category='Pizza', image_url='https://images.unsplash.com/photo-1628840042765-356cda07504e?w=400', rating=4.8),
                FoodItem(name='Classic Cheeseburger', description='Beef patty, cheddar cheese, lettuce, tomato, special sauce', price=10.99, category='Burger', image_url='https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=400', rating=4.6),
                FoodItem(name='Bacon Burger', description='Beef patty, crispy bacon, cheddar, BBQ sauce, onion rings', price=12.99, category='Burger', image_url='https://images.unsplash.com/photo-1553979459-d2229ba7433b?w=400', rating=4.7),
                FoodItem(name='Fettuccine Alfredo', description='Creamy parmesan sauce with fettuccine pasta', price=13.99, category='Pasta', image_url='https://images.unsplash.com/photo-1645112411341-c5a129e26a9a?w=400', rating=4.5),
                FoodItem(name='Spaghetti Carbonara', description='Eggs, pecorino cheese, pancetta, black pepper', price=14.99, category='Pasta', image_url='https://images.unsplash.com/photo-1612874742237-6526221588e3?w=400', rating=4.6),
                FoodItem(name='California Roll', description='Crab, avocado, cucumber, sesame seeds', price=15.99, category='Sushi', image_url='https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=400', rating=4.8),
                FoodItem(name='Rainbow Roll', description='Assorted fish, avocado, cucumber, crab', price=18.99, category='Sushi', image_url='https://images.unsplash.com/photo-1617196035154-1e7e6e28b0db?w=400', rating=4.9),
                FoodItem(name='Caesar Salad', description='Romaine lettuce, croutons, parmesan, caesar dressing', price=8.99, category='Salad', image_url='https://images.unsplash.com/photo-1550304943-4f24f54dd8cf?w=400', rating=4.4),
                FoodItem(name='Greek Salad', description='Feta cheese, olives, cucumber, tomatoes, red onion', price=9.99, category='Salad', image_url='https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=400', rating=4.5),
                FoodItem(name='Chocolate Lava Cake', description='Warm chocolate cake with molten center', price=6.99, category='Dessert', image_url='https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=400', rating=4.9),
                FoodItem(name='Tiramisu', description='Classic Italian dessert with coffee and mascarpone', price=7.99, category='Dessert', image_url='https://images.unsplash.com/photo-1571877227200-a0d98ea607e9?w=400', rating=4.8),
            ]
            db.session.add_all(sample_items)
            db.session.commit()
            print("Database initialized with sample food items!")

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
