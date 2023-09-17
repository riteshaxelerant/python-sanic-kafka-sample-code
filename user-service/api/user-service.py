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

app = Sanic("UserService")

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

# Function to check email if already exist
async def checkEmail(email):
    try:
        async with app.ctx.db.acquire() as connection:    
            query = "SELECT EXISTS (SELECT 1 FROM user_service_db.users WHERE email = $1)"
            rows = await connection.fetchval(query, email)
        return rows
    except Exception as e:           
        return False

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

# Service API to register Users
@app.post("/users/register")
async def register(request):    
    # Implement user registration logic
    try:
        user_data = request.json  
        if not user_data.get('email') or not user_data.get('username') or not user_data.get('password'):
            return json({"message": "Please input username, email, password"}, status=201)
        else:
            email_exist = await checkEmail(user_data.get('email'))         
            if email_exist:      
                return json({"message": "Email already exist"}, status=201)            
            else:
                async with app.ctx.db.acquire() as connection: 
                    # Begin a transaction to ensure that database operations are atomic. 
                    async with connection.transaction():   
                        new_user_id = await connection.fetchval(
                            "INSERT INTO user_service_db.users(username, email, password) VALUES($1, $2, $3) RETURNING id",
                            user_data["username"], user_data["email"], user_data["password"]
                        ) 

                    # Sending message to topic
                    user_data_for_producer = {"user_id": str(new_user_id), "username": user_data["username"], "email": user_data["email"]}
                    p.produce( KAFKA_PRODUCER_TOPIC , value=str(user_data_for_producer), callback=delivery_callback )
                    p.flush()
                    p.poll(0.5)

                return json({"message": "User registered successfully","id": str(new_user_id)}, status=201)
    except Exception as e:       
        return json({'error': str(e)})
    
# Service API to login user. It will return the user's information like email, id and user name
@app.post("/users/login")
async def login(request):
    # Implement login logic
    try:
        user_data = request.json 
        if not user_data.get('email') or not user_data.get('password'): 
            return json({"message": "Email or Password should not be empty and keys must be email and password"}, status=201) 
        else:    
            async with app.ctx.db.acquire() as connection:    
                query = "SELECT id, email, password, username FROM user_service_db.users WHERE email = $1"
                user_info = await connection.fetch(query, user_data['email'])                
                if not user_info: 
                    return  json({"message": "Incorrect Email"}, status=201)    
                else: 
                    stored_password = user_info[0]['password']
                    if stored_password == user_data['password'] :                    
                        data = {
                            'id': str(user_info[0]['id']),
                            'username': user_info[0]['username'],
                            'email': user_info[0]['email'],
                        }                    
                        return  json({"message": "Logged in successfully","data": data}, status=201)  
                    else:
                        return  json({"message": "Incorrect password"}, status=201)   
    except Exception as e:           
        return json({'error': str(e)})
    


#Service API to get user information
@app.get("/users/<user_id>")
async def get_user(request, user_id):    
    try:        
        if not user_id:
            return  json({"message": "Enter user id"}, status=201)  
        elif 32 <= len(user_id) <= 36:        
            async with app.ctx.db.acquire() as connection:    
                query = "SELECT * FROM user_service_db.users WHERE id = $1"
                user_info = await connection.fetch(query, user_id)                                
                if not user_info: 
                    return  json({"message": "User not found"}, status=201)    
                else:                                   
                    data = {
                        'id': str(user_info[0]['id']),
                        'username': user_info[0]['username'],
                        'email': user_info[0]['email'],                    
                    }                    
                    return  json({"message": "User found","data": data}, status=201) 
        else:
             return  json({"message": "length must be between 32..36 characters"}, status=201) 
                
    except Exception as e:     
        #print(e)      
        return  json({"message": "User not found"}, status=201)    

# Comment the code below if you want to run the service API using sanic command
if __name__ == "__main__":
    app.run( host=API_HOST, port=API_PORT, debug=True )


    
# Run this command via sanic to run the server: sanic user-service:app --host=0.0.0.0 --port=1604 --dev
# Run this command via python to run the server: python user-service.py
