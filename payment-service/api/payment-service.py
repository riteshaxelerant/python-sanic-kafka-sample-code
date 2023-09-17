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
DB_PORT = config('DB_PORT', default=5434, cast=int)
DB_USER = config('DB_USER')
DB_PASSWORD = config('DB_PASSWORD')
DB_NAME = config('DB_NAME')
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = config('KAFKA_BOOTSTRAP_SERVERS')
KAFKA_PRODUCER_TOPIC = config('KAFKA_PRODUCER_TOPIC')
KAFKA_PRODUCER_TOPIC2 = config('KAFKA_PRODUCER_TOPIC2')
KAFKA_PRODUCER_TOPIC_DLQ = config('KAFKA_PRODUCER_TOPIC_DLQ')

# API Configuration
API_HOST = config('API_HOST')
API_PORT = config('API_PORT',default=1602, cast=int)

# Database connection
db_config = {
    'user': DB_USER,
    'password': DB_PASSWORD,
    'database': DB_NAME,
    'host': DB_HOST,
    'port': DB_PORT,
}

app = Sanic("PaymentService")

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
    
# Create order function that returns order ID
async def create_payment(order_id, amount, status, payment_gateway_response):
    try: 
        async with app.ctx.db.acquire() as connection: 
            # Begin a transaction to ensure that database operations are atomic. 
            async with connection.transaction():       
                payment_id = await connection.fetchval(
                    "INSERT INTO payment_service_db.payments(order_id, amount, status, payment_gateway_response) VALUES($1, $2, $3, $4) RETURNING id",
                    order_id, amount, status, payment_gateway_response
                )                  
        return payment_id
    except Exception as e:             
        return False
        
# This function is a callback function from kafka producer method used to identify the errors and report to DLQ for further investigation
def delivery_callback(err, msg):
    if err:
        data = msg.value().decode('utf-8')
        data = data.replace("'", "\"")
        data = json.loads(data) 
        data['topic'] = msg.topic()
        data['error'] = str(err)
        print(data)    
        p.produce( KAFKA_PRODUCER_TOPIC_DLQ, value=str(data) )
        print(f"Failed to deliver message: {err}. Message might be retried.")
    else:                
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]")

############## All the API related code starts from here ###########

@app.post("/payments")
async def initiate_payment(request):
    # Implement payment initiation logic
    try:        
        payment_data = request.json     
        if not payment_data.get('order_id'):                         
            return json({"message": "Object  must contains order_id"}, status=201)   
        elif not payment_data.get('amount'):  
             return json({"message": "Object must contains amount"}, status=201)  
        elif not payment_data.get('status'):  
             return json({"message": "Object must contains status"}, status=201) 
        elif not payment_data.get('payment_gateway_response'):  
             return json({"message": "Object must contains gateway response"}, status=201) 
        else:            
            order_id = payment_data.get('order_id')
            amount = float(payment_data.get('amount'))
            status = payment_data.get('status')
            payment_gateway_response = payment_data.get('payment_gateway_response')

            payment_id = await create_payment(order_id, amount, status, payment_gateway_response) 
            if payment_id and status == 'success':
                # Sending message to topic payment-success
                payment_data_for_producer = {"payment_id":str(payment_id), "order_id": str(order_id), "amount": amount, "payment_gateway_response": payment_gateway_response}
                p.produce( KAFKA_PRODUCER_TOPIC, value=str(payment_data_for_producer), callback=delivery_callback ) 
                p.flush()
                p.poll(0.5) 
                return json({"message": "Payment made successfully","id": str(payment_id)}, status=201) 
            else:
                 # Sending message to topic payment-failure
                payment_data_for_producer = {"payment_id":str(payment_id), "order_id": str(order_id), "amount": amount, "payment_gateway_response": payment_gateway_response}
                p.produce( KAFKA_PRODUCER_TOPIC2, value=str(payment_data_for_producer), callback=delivery_callback)
                p.flush()
                p.poll(0.5) 
                return json({"message": "Payment failed","id": str(payment_id)}, status=201)
            
    except Exception as e:     
        #print(str(e))  
        return json({"message": "Error"}, status=201)

@app.get("/payments/<payment_id>")
async def get_payment(request, payment_id):
    # Fetch payment by payment_id
    try:        
        if not payment_id:
            return  json({"message": "Enter payment id"}, status=201)  
        elif 32 <= len(payment_id) <= 36:        
            async with app.ctx.db.acquire() as connection:    
                query = "SELECT * FROM payment_service_db.payments WHERE id = $1"
                payment_info = await connection.fetch(query, payment_id)                                
                if not payment_info: 
                    return  json({"message": "Payment not found"}, status=201)    
                else:                                   
                    data = {
                        'id': str(payment_info[0]['id']),
                        'order_id': str(payment_info[0]['order_id']),
                        'amount': payment_info[0]['amount'], 
                        'status': payment_info[0]['status'],  
                        'payment_gateway_response': payment_info[0]['payment_gateway_response'],                   
                    }                    
                    return  json({"message": "Payment found","data": data}, status=201) 
        else:
             return  json({"message": "ID length must be between 32..36 characters"}, status=201) 
                
    except Exception as e:     
        print(e)      
        return  json({"message": "Payment not found"}, status=201)

if __name__ == "__main__":
    app.run(host=API_HOST, port=API_PORT, debug=True)

# Run this command via sanic to run the server: sanic payment-service:app --host=0.0.0.0 --port=1602 --dev
# Run this command via python to run the server: python payment-service.py
