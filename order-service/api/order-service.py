from sanic import Sanic
from sanic.response import json
# This library we are using to get environmental variables from .env file. Install this dependency by running this command : pip install python-decouple
from decouple import config 
# This library we are using to connect API with database postgresql. Install this dependency by running this command : pip install asyncpg
import asyncpg
# This library we are using to connect kafka. Install this dependency by running this command : pip install confluent_kafka
from confluent_kafka import Producer
# Import the authenticate and authenticate_middleware functions
from authentication import authenticate, authenticate_middleware

# Database Configuration
DB_HOST = config('DB_HOST')
DB_PORT = config('DB_PORT', default=5433, cast=int)
DB_USER = config('DB_USER')
DB_PASSWORD = config('DB_PASSWORD')
DB_NAME = config('DB_NAME')
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = config('KAFKA_BOOTSTRAP_SERVERS')
KAFKA_PRODUCER_TOPIC = config('KAFKA_PRODUCER_TOPIC')
KAFKA_PRODUCER_TOPIC_DLQ = config('KAFKA_PRODUCER_TOPIC_DLQ')

# API Configuration
API_HOST = config('API_HOST')
API_PORT = config('API_PORT',default=1603, cast=int)


# Database connection
db_config = {
    'user': DB_USER,
    'password': DB_PASSWORD,
    'database': DB_NAME,
    'host': DB_HOST,
    'port': DB_PORT,
}

app = Sanic("OrderService")

# creating a producer from Kafka 
p_conf = {
    'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
    'retries': 3,  # Number of retries
    'retry.backoff.ms': 60000,  # Wait for 60,000ms (1 minute) before retrying
    'enable.idempotence': True
}
p = Producer(p_conf)

# Register the middleware
@app.middleware('request')(authenticate_middleware)

# Register the setup_db function to be executed before starting the server
@app.listener('before_server_start')
async def before_server_start(app, loop):
    await setup_db(app)

# Register the close_db function to be executed after stopping the server
@app.listener('after_server_stop')
async def after_server_stop(app, loop):
    await close_db(app)

############## All the functions code starts from here ###########
# Define a function to create a database connection pool
async def setup_db(app):
    app.ctx.db = await asyncpg.create_pool(**db_config)
   

# Define a function to close the database connection pool
async def close_db(app):
    await app.ctx.db.close()

# This function is a callback function from kafka producer method used to identify the errors and report to DLQ for further investigation
def delivery_callback(err, msg):
    try:
        if err:
            data = msg.value().decode('utf-8')
            data = data.replace("'", "\"")
            data = json.loads(data) 
            data['topic'] = msg.topic()
            data['error'] = str(err)            
            p.produce( KAFKA_PRODUCER_TOPIC_DLQ, value=str(data) )
            print(f"Failed to deliver message: {err}. Message might be retried.")
        else:                
            print(f"Message delivered to {msg.topic()} [{msg.partition()}]")
    except Exception as e:       
        print(json({'error': str(e)})) 

# Checkif user exist or not

async def check_user(user_id):
    try:
        async with app.ctx.db.acquire() as connection:                 
            query = "SELECT EXISTS (SELECT 1 FROM order_service_db.registered_users WHERE user_id = $1)"
            rows = await connection.fetchval(query, user_id)            
        return rows
    except Exception as e:           
        return False


# Create order function that returns order ID
async def create_order(user_id, total_price):
    try: 
        async with app.ctx.db.acquire() as connection:  
            # Begin a transaction to ensure that database operations are atomic. 
            async with connection.transaction():      
                order_id = await connection.fetchval(
                    "INSERT INTO order_service_db.orders(user_id, total_price) VALUES($1, $2) RETURNING id",
                    user_id, total_price
                )                  
        return order_id
    except Exception as e:             
        return False

# Create order_item function to insert products corrosponding to order_id
async def create_order_items(order_id, products):
    try: 
        async with app.ctx.db.acquire() as connection:   
            # Perform the bulk insert
            # Begin a transaction to ensure that database operations are atomic. 
            async with connection.transaction():         
                for row in products:                    
                    product_id = row['product_id']
                    quantity = row['quantity']
                    price = row['price']
                    # Execute the INSERT statement
                    await connection.execute('''
                        INSERT INTO order_service_db.order_items (order_id, product_id, quantity, price)
                        VALUES ($1, $2, $3, $4)
                    ''', order_id, product_id, quantity, price)           
        return True
    except Exception as e:          
        return json({"message": "Error"}, status=201)
    


############## All the API related code starts from here ###########
# Service API to create orders
@app.post("/orders")
async def place_order(request):
    # Implement order placement logic
    try:        
        ordered_data = request.json     
        if not ordered_data.get('user_id'):                         
            return json({"message": "Order must contains user_id"}, status=201)   
        elif not ordered_data.get('total_price'):  
             return json({"message": "Order must contains total_price"}, status=201)  
        elif not ordered_data.get('products'):  
             return json({"message": "Order must contains some products"}, status=201)  
        else:            
            user_id = ordered_data.get('user_id')
            total_price = float(ordered_data.get('total_price'))
            products = ordered_data.get('products')
            # Here we will check the order validity by checking the user is present in the system or not
            user_exist = await check_user(user_id)            
            if user_exist:
                order_id = await create_order(user_id, total_price) 
                if order_id :                
                    status = await create_order_items(order_id, products)
                                       
                    # Sending message to topic
                    order_data_for_producer = {"order_id": str(order_id), "total_price": total_price}
                    p.produce( KAFKA_PRODUCER_TOPIC, value=str(order_data_for_producer), callback=delivery_callback )     
                    p.flush()
                    p.poll(0.5)
                return json({"message": "Order created successfully","id": str(order_id)}, status=201)
            else:
                return json({"message": "User not found. So order cannot be created"}, status=201)
    except Exception as e:     
        print(str(e))  
        return json({"message": "Error"+str(e)}, status=201)
    
@app.get("/orders/<order_id>")
async def get_order(request, order_id):
    # Fetch Order by order_id
    try:        
        if not order_id:
            return  json({"message": "Enter product id"}, status=201)  
        elif 32 <= len(order_id) <= 36:        
            async with app.ctx.db.acquire() as connection:    
                query = "SELECT * FROM order_service_db.orders WHERE id = $1"
                order_info = await connection.fetch(query, order_id)                                
                if not order_info: 
                    return  json({"message": "Order not found"}, status=201)    
                else:                                   
                    data = {
                        'id': str(order_info[0]['id']),
                        'user_id': str(order_info[0]['user_id']),
                        'total_price': order_info[0]['total_price'], 
                        'status': order_info[0]['status'],                   
                    }                    
                    return  json({"message": "Order found","data": data}, status=201) 
        else:
             return  json({"message": "ID length must be between 32..36 characters"}, status=201) 
                
    except Exception as e:     
        #print(e)      
        return  json({"message": "Order not found"}, status=201)

if __name__ == "__main__":
    app.run(host=API_HOST, port=API_PORT, debug=True)

# Run this command via sanic to run the server: sanic order-service:app --host=0.0.0.0 --port=1603 --dev
# Run this command via python to run the server: python order-service.py
