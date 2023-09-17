from sanic import Sanic
# This we are using to get environmental variables from .env file. Install this dependency by running this command : pip install python-decouple
from decouple import config 
from confluent_kafka import Consumer, KafkaError, Producer
import asyncpg
import json
import asyncio

# Database Configuration from .env file
DB_HOST = config('DB_HOST')
DB_PORT = config('DB_PORT', default=5433, cast=int)
DB_USER = config('DB_USER')
DB_PASSWORD = config('DB_PASSWORD')
DB_NAME = config('DB_NAME')

# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS = config('KAFKA_BOOTSTRAP_SERVERS')
KAFKA_PRODUCER_TOPIC_DLQ = config('KAFKA_PRODUCER_TOPIC_DLQ')
KAFKA_CONSUMER_GROUP_ID = config('KAFKA_CONSUMER_GROUP_ID')
KAKFA_CONSUMER_SUBSCRIBE_TOPIC_USR_REG = config('KAKFA_CONSUMER_SUBSCRIBE_TOPIC_USR_REG')
KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_SUCC = config('KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_SUCC')
KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_FAIL = config('KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_FAIL')
KAFKA_PRODUCER_RETRIES = config('KAFKA_PRODUCER_RETRIES', default=3, cast=int)

# Database connection
db_config = {
    'user': DB_USER,
    'password': DB_PASSWORD,
    'database': DB_NAME,
    'host': DB_HOST,
    'port': DB_PORT,
}

# Database setup (similar to the Sanic app setup)
async def setup_db():
    return await asyncpg.create_pool(**db_config)

# Define a function to close the database connection pool
async def close_db(app):
    await app.ctx.db.close()

async def check_order_status(order_id):
    pool = await setup_db()
    try:
        async with pool.acquire() as connection:              
            query = "SELECT status FROM order_service_db.orders WHERE id = $1"
            rows = await connection.fetchval(query, order_id)
        return rows
    except Exception as e:         
        return False
# Order Service consumer
async def order_service_consumer():

    #Creating consumer from kafka
    c = Consumer({
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': KAFKA_CONSUMER_GROUP_ID,
        'auto.offset.reset': 'earliest'
    })
    c.subscribe( [KAKFA_CONSUMER_SUBSCRIBE_TOPIC_USR_REG, KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_SUCC, KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_FAIL] )

    # creating a producer from Kafka 
    p_conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'retries': KAFKA_PRODUCER_RETRIES,  # Number of retries
        'retry.backoff.ms': 60000,  # Wait for 60,000ms (1 minute) before retrying
        'enable.idempotence': True
    }
    p = Producer(p_conf)


    pool = await setup_db()

    try:
        while True:
            msg = c.poll(1000)
            if msg is None:
                continue

            # Check if the message has an error
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    print("Reached end of partition")
                else:
                    print("Consumer error: {}".format(msg.error()))
                continue

            topic = msg.topic()
            data = msg.value().decode('utf-8')
            data = data.replace("'", "\"")
            data = json.loads(data)            
            if topic == KAKFA_CONSUMER_SUBSCRIBE_TOPIC_USR_REG: 
                # Validating here data["user_id"] is not an empty string             
                if not data["user_id"]:
                    message_for_dlq = {"topic": KAKFA_CONSUMER_SUBSCRIBE_TOPIC_USR_REG, "error": "User is not valid"}
                    p.produce( KAFKA_PRODUCER_TOPIC_DLQ, value=str(message_for_dlq) )     
                    p.flush()
                    p.poll(0.5)
                else:
                    # Store user data for validation purposes
                    async with pool.acquire() as connection:
                        # Begin a transaction to ensure that database operations are atomic. 
                        async with connection.transaction():    
                            await connection.execute(
                                "INSERT INTO order_service_db.registered_users(user_id) VALUES($1)",
                                data["user_id"]
                            )
            elif topic == KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_SUCC:
                # Validating here data["order_id"] is not an empty string  
                if not data["order_id"]:
                    message_for_dlq = {"topic": KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_SUCC, "error": "Order ID is not valid"}
                    p.produce( KAFKA_PRODUCER_TOPIC_DLQ , value=str(message_for_dlq) )     
                    p.flush()
                    p.poll(0.5)
                else:
                    # Here we will check if order status is Pending then only we will process                             
                    order_status = await check_order_status(data["order_id"]) 
                    if order_status == 'Pending' :
                        # Update order status
                        async with pool.acquire() as connection:
                            # Begin a transaction to ensure that database operations are atomic. 
                            async with connection.transaction():    
                                await connection.execute(
                                    "UPDATE order_service_db.orders SET status='Paid' WHERE id=$1",
                                    data["order_id"]
                                )
            elif topic == KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_FAIL:
                # Validating here data["order_id"] is not an empty string  
                if not data["order_id"]:
                    message_for_dlq = {"topic": KAKFA_CONSUMER_SUBSCRIBE_TOPIC_PAY_FAIL, "error": "Order ID is not valid"}
                    p.produce( KAFKA_PRODUCER_TOPIC_DLQ, value=str(message_for_dlq) )     
                    p.flush()
                    p.poll(0.5)
                else:
                    # Here we will check if order status is Pending then only we will process                   
                    order_status = await check_order_status(data["order_id"]) 
                    if order_status == 'Pending' : 
                        # Handle payment failure, maybe notify the user, etc.
                        async with pool.acquire() as connection:
                            # Begin a transaction to ensure that database operations are atomic. 
                            async with connection.transaction():    
                                await connection.execute(
                                    "UPDATE order_service_db.orders SET status='Failed' WHERE id=$1",
                                    data["order_id"]
                                )

    except KeyboardInterrupt:
        pass
    finally:
        c.close()
asyncio.run(order_service_consumer())