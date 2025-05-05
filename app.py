from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import func

app = Flask(__name__)

# Config for SQLite db
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db?check_same_thread=False'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False 

db = SQLAlchemy(app)

# DB models
class Product(db.Model):
    custom_id = db.Column(db.String(10), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, nullable=False)
    i_location = db.Column(db.String(100), nullable=False)

class Location(db.Model):
    location_id = db.Column(db.String(10), primary_key=True) 
    name = db.Column(db.String(100), nullable=False)

class ProductMovement(db.Model):
    product_id = db.Column(db.String(10), db.ForeignKey('product.custom_id'), primary_key=True)
    timestamp = db.Column(db.DateTime, primary_key=True)
    from_location = db.Column(db.String(100))
    to_location = db.Column(db.String(100))
    qty = db.Column(db.Integer, nullable=False)

# Routes
@app.route('/')
def default():
    return redirect(url_for('login'))

#login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        adminid = request.form['adminid']
        password = request.form['password']
        if adminid == 'aereletech' and password == 'at@123':
            return redirect(url_for('home'))
        else:
            error = 'Invalid Id or password'
    return render_template('login.html', error=error, hide_nav=True)

#home route
@app.route('/home')
def home():
    product = Product.query.all()
    locations = Location.query.all()
    product_data = []

    for pro in product:
        total_stock = sum(get_stock(pro.custom_id, location.location_id) for location in locations)

        product_data.append({
            'custom_id': pro.custom_id,
            'name': pro.name,
            'price': pro.price,
            'stock': pro.stock
        })

    return render_template('home.html', last_products=product_data, locations=locations)

#Add Product details
@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    locations = Location.query.all()

    if request.method == 'POST':
        try:
            
            name = request.form['name']
            price = float(request.form['price'])
            stock = int(request.form['stock'])
            i_location = request.form['i_location']

            # Generate a new custom_id (e.g., AE001, AE002)
            last_product = Product.query.order_by(Product.custom_id.desc()).first()
            next_number = int(last_product.custom_id[2:]) + 1 if last_product else 1
            custom_id = f"AE{next_number:03d}"

            # Create a new product
            new_product = Product(
                custom_id=custom_id,
                name=name,
                price=price,
                stock=stock,
                i_location=i_location
            )
            db.session.add(new_product)
            db.session.commit()

        
            move = ProductMovement(
                product_id=custom_id,
                from_location=None,
                to_location=i_location,
                qty=stock,
                timestamp=datetime.now()
            )
            db.session.add(move)
            db.session.commit()

            return redirect(url_for('add_product'))

        except Exception as e:
            db.session.rollback()
            return f"Error while adding product: {str(e)}", 500

    # Fetch latest 3 products for display
    last_products = Product.query.order_by(Product.custom_id.desc()).limit(3).all()
    return render_template('add_product.html', locations=locations, last_products=last_products)



#Add location
@app.route('/add_location', methods=['GET', 'POST'])
def add_location():
    if request.method == 'POST':
        name = request.form['name']
        prefix = name[:3].upper()
        last_location = Location.query.order_by(Location.location_id.desc()).first()
        next_number = 1
        if last_location:
            last_num = int(last_location.location_id[3:])
            next_number = last_num + 1
        location_id = f"{prefix}{next_number:03d}"

        new_location = Location(name=name, location_id=location_id)
        db.session.add(new_location)
        db.session.commit()
        return redirect(url_for('add_location'))

    locations = Location.query.all()
    return render_template('add_location.html', locations=locations)

# Get stock for a product at a specific location
def get_stock(product_id, location):
    in_qty = db.session.query(func.sum(ProductMovement.qty)).filter_by(
        product_id=product_id,
        to_location=location
    ).scalar() or 0

    out_qty = db.session.query(func.sum(ProductMovement.qty)).filter_by(
        product_id=product_id,
        from_location=location
    ).scalar() or 0

    return in_qty - out_qty

# Add movement route
@app.route('/add_movement', methods=['GET', 'POST'])
def add_movement():
    products = Product.query.all()
    locations = Location.query.all()

    if request.method == 'POST':
        try:
            product_id = request.form['product_id']
            from_location = request.form['from_location']
            to_location = request.form['to_location']
            qty = int(request.form['qty'])
            timestamp = datetime.now()

            # Basic validations
            if qty <= 0:
                return "Quantity must be positive", 400
            if not from_location or not to_location:
                return "Both locations are required", 400
            if from_location == to_location:
                return "From and To locations cannot be the same", 400

            
            incoming = db.session.query(func.sum(ProductMovement.qty)).filter_by(product_id=product_id, to_location=from_location).scalar() or 0
            outgoing = db.session.query(func.sum(ProductMovement.qty)).filter_by(product_id=product_id, from_location=from_location).scalar() or 0
            available_stock = incoming - outgoing

            if available_stock < qty:
                return f"Insufficient stock at {from_location}. Available: {available_stock}, Requested: {qty}", 400

            new_move = ProductMovement(
                product_id=product_id,
                from_location=from_location,
                to_location=to_location,
                qty=qty,
                timestamp=timestamp
            )
            db.session.add(new_move)

            product = Product.query.get(product_id)
            if product:
                total_in = db.session.query(func.sum(ProductMovement.qty)).filter_by(product_id=product_id).filter(ProductMovement.to_location.isnot(None)).scalar() or 0
                total_out = db.session.query(func.sum(ProductMovement.qty)).filter_by(product_id=product_id).filter(ProductMovement.from_location.isnot(None)).scalar() or 0
                product.stock = total_in - total_out

            db.session.commit()
            return redirect(url_for('add_movement'))

        except Exception as e:
            db.session.rollback()
            return f"Error: {str(e)}", 500

    return render_template('add_movement.html', products=products, locations=locations)



# Report route
@app.route('/report')
def report():
    movements = ProductMovement.query.all()
    products = Product.query.all()
    locations = Location.query.all()

    stock_map = {}
    timestamp_map = {}

    for move in movements:
        if move.from_location:
            key_from = (move.product_id, move.from_location)
            stock_map[key_from] = stock_map.get(key_from, 0) - move.qty
            timestamp_map[key_from] = move.timestamp

        if move.to_location:
            key_to = (move.product_id, move.to_location)
            stock_map[key_to] = stock_map.get(key_to, 0) + move.qty
            timestamp_map[key_to] = move.timestamp

    report_data = []

    for (product_id, location), qty in stock_map.items():
        product = Product.query.get(product_id)
        if product:
            timestamp = timestamp_map.get((product_id, location))
            if timestamp:
                timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')  # Format the timestamp
            report_data.append({
                'product_id': product.custom_id,
                'product_name': product.name,
                'price': product.price,
                'location': location,
                'qty': qty,
                'timestamp': timestamp
            })

    return render_template('report.html', report_data=report_data, locations=locations, products=products)




if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
