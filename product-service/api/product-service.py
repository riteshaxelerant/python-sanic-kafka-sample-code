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
DB_PORT = config('DB_PORT', default=5435, cast=int)
DB_USER = config('DB_USER')
DB_PASSWORD = config('DB_PASSWORD')
DB_NAME = config('DB_NAME')
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = config('KAFKA_BOOTSTRAP_SERVERS')
KAFKA_PRODUCER_TOPIC = config('KAFKA_PRODUCER_TOPIC')
KAFKA_PRODUCER_TOPIC_DLQ = config('KAFKA_PRODUCER_TOPIC_DLQ')

# API Configuration
API_HOST = config('API_HOST')
API_PORT = config('API_PORT',default=1601, cast=int)


# Database connection
db_config = {
    'user': DB_USER,
    'password': DB_PASSWORD,
    'database': DB_NAME,
    'host': DB_HOST,
    'port': DB_PORT,
}

app = Sanic("ProductService")

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

############## All the API related code starts from here ###########
# Service API to create products
@app.post("/products")
async def create_product(request):    
    # Implement product creation logic   
    try:        
        product_data = request.json  
        if not product_data.get('name') or not product_data.get('price'):                    
            return json({"message": "Product name or price should not be empty"}, status=201)            
        else:
            async with app.ctx.db.acquire() as connection:    
                product_id = await connection.fetchval(
                    "INSERT INTO product_service_db.products(name, description, price) VALUES($1, $2, $3) RETURNING id",
                    product_data["name"], product_data["description"], product_data["price"]
                )  

                # Sending message to topic
                product_data_for_producer = {"product_id": str(product_id), "name": product_data["name"], "price": product_data["price"]}
                p.produce( KAFKA_PRODUCER_TOPIC, value=str(product_data_for_producer), callback=delivery_callback )     
                p.flush()
                p.poll(0.5)

            return json({"message": "Product created successfully","id": str(product_id)}, status=201)
    except Exception as e:     
        print(str(e))  
        return json({"message": "Error"}, status=201)


# Service API to get the single product information
@app.get("/products/<product_id>")
async def get_product(request, product_id):
    # Fetch product by product_id
    try:        
        if not product_id:
            return  json({"message": "Enter product id"}, status=201)  
        elif 32 <= len(product_id) <= 36:        
            async with app.ctx.db.acquire() as connection: 
                # Begin a transaction to ensure that database operations are atomic. 
                async with connection.transaction():      
                    query = "SELECT * FROM product_service_db.products WHERE id = $1"
                    product_info = await connection.fetch(query, product_id)                                
                    if not product_info: 
                        return  json({"message": "Product not found"}, status=201)    
                    else:                                   
                        data = {
                            'id': str(product_info[0]['id']),
                            'name': product_info[0]['name'],
                            'description': product_info[0]['description'], 
                            'price': product_info[0]['price'],                   
                        }                    
                        return  json({"message": "Product found","data": data}, status=201) 
        else:
             return  json({"message": "ID length must be between 32..36 characters"}, status=201) 
                
    except Exception as e:     
        #print(e)      
        return  json({"message": "Product not found"}, status=201)

# Service API to get the single product information
@app.get("/products/list", ignore_body=False)
async def get_product_list(request):
    # Fetch product by product_id    
    try:        
        list_params = request.json   
        limit = 5   
        offset = 0   

        if list_params and list_params.get('limit'):  
            limit = list_params.get('limit')
        
        if list_params and list_params.get('offset'):  
            offset = list_params.get('offset')      

        async with app.ctx.db.acquire() as connection:    
            query = "SELECT * FROM product_service_db.products limit $1 offset $2"            
            products = await connection.fetch(query, limit, offset)                                   
            if not products: 
                return  json({"message": "No products"}, status=201)    
            else:  
                product_list = []
                for record in products:                    
                    json_record = {
                        "id": str(record['id']),
                        "name": record['name'],
                        "description": record['description'],
                        "price": float(record['price']),
                        "created_at": record['created_at'].strftime('%Y-%m-%d %H:%M:%S'),
                        "updated_at": record['updated_at'].strftime('%Y-%m-%d %H:%M:%S'),
                    }
                    product_list.append(json_record)                                                           
                return  json({"message": "Product found","data": product_list}, status=201) 
        
                
    except Exception as e:     
        print(e)      
        return  json({"message": "No products"}, status=201)


if __name__ == "__main__":
    app.run( host=API_HOST, port=API_PORT, debug=True )

# Run this command via sanic to run the server: sanic product-service:app --host=0.0.0.0 --port=1601 --dev
# Run this command via python to run the server: python product-service.py
