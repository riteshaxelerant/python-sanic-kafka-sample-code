# Distributed Microservices System with Sanic, PostgreSQL and Kafka
Building a Distributed Microservices System with Sanic, PostgreSQL and Kafka for a fictional e-commerce platform. The platform consists of multiple services, each responsible for different aspects of the application, such as user authentication, product catalog, order management, and payment processing.

NOTE: This is just a sample project to demonstrate how micorservices work together with Kafka and postgresql.

## Goal:
1. **User Service:** Responsible for user registration, authentication, and profile management. Each user has a unique ID, username, email, and password.
2. **Product Service:** Manages the product catalog. Each product has a unique ID, name, description, and price.
3. **Order Service:** Handles customer orders. Each order is associated with a user and contains a list of products along with quantities.
4. **Payment Service:** Takes care of payment processing for orders. It interacts with external payment gateways.
5. **Communication via Kafka:** All services communicate with each other using Kafka topics. For example, when an order is placed, a message is sent to the Order Service via Kafka, which triggers the payment processing.

## Requirements:
1. **Service Implementation:** Each service should expose RESTful APIs for performing the required operations. Use Python Sanic framework for building these APIs.
2. **Database Interaction:** Each service should have its own PostgreSQL database for storing relevant data (user details, product details, orders, etc.).
3. **Event Driven:** Whenever a significant action occurs (user registration, order placement, payment success/failure), the relevant service should publish a message to the appropriate Kafka topic.
4. **Consumers:** Each service should have Kafka consumers that listen to relevant topics and react accordingly. For instance, the Order Service should listen for new orders and initiate payment processing.
5. **Fault Tolerance:** Design the system to handle failures gracefully. What happens if a service is temporarily unavailable? How do you ensure data consistency in the face of failures?
6. **Documentation:** Provide clear documentation for setting up and running the entire system, including the required steps for setting up Kafka topics and configuring services.

## Prerequisites (Docker, Python, Sanic framework, Postgresql, Kafka)
Here we will use docker to setup all the services.
1. **Install Python:** Follow the [link]( https://www.python.org/downloads/macos/ ) to install python.
2. **Directory Structure:** To setup locally we will create 4 seperate directories corrosponding to our microservices(User Service, Product Service, Order Service, Payment Service) and one directory for Kafka so that we can run each service independently on a different port.
    
    Under each directory we should setup two sub-directories, one for microservice api and another for postgresql database.
3. **Postgresql setup:** Using docker compose file we can install postgresql in each microservice sub directory directory. Code for docker-compose.yml file: 
    ```
    version: '3'
    services:
    # PostgreSQL database
    user_service_db:
        image: postgres:latest
        container_name: user_service_db
        environment:
        POSTGRES_USER: root
        POSTGRES_PASSWORD: password
        ports:
        - "5436:5432"    
        volumes:
        - ./postgres_data:/var/lib/postgresql/data
        
    ```

    For a directory structure consider an example of a microservice say ``user-service``. So the directory structure should be: 
    
    ```
        user-service
        |__api
            |__user-service.py
            |__authentication.py
        |__user_service_db
            |__docker-compose.yml
    
    ```
    Then run docker command to create above postgres service: `` docker-compose up``. The same structure will be repeated for all the microservices (User Service, Product Service, Order Service, Payment Service).
    
    **NOTE:** Since postgresql will be installed for each individual microservices, we should keep the port separate. On above docker file where ports are defined as `` "5436:5432" ``. The left port ``5436`` indicates for outer connectivity (means connectivity with sanic) and the right port indicates internal connectivity which always be the same. So for another microservice say ``product-service`` we can define the left port as ``5435`` and so on.
4. **Kafka setup:** To setup Kafka at your local machine, follow the [link](https://docs.confluent.io/platform/current/platform-quickstart.html#cp-quickstart-step-1) to install Kafka under the directory ``kafka``. After verifying the kafka installation check the Kafka clusters are running on your local environment [here](http://localhost:9021/clusters).
5. **Virtual Python environment:** Since we already have a global installation of python, it is best to have a separate environment of python sanic framework for each microservice.
    - **Command to setup virtual environment:** ``` pip install virtualenv ```
    - Navigate to your microservice directory say: ``cd user-service/api/`` and run the command ``virtualenv env_user `` where env_user is our environment name. To activate the virtual environment run the command ``source env_user/bin/activate``
    - Now we have to install sanic framework with in our virtual environment using this command: ``pip install sanic``
    - For posgresql connectivity with sanic framework we have to install asyncpg library with in our virtual environment using this command: ``pip install asyncpg``
    - For Kafka connectivity we have to install a kafka library with in our virtual environment using this command: ``pip install confluent-kafka``
6. **Pgadmin setup (Optional):** This is optional if you can manage posgres with command line else if you want to see a web interface then you can create a separate directory and put a ``docker-compose.yml`` file with code:
```
version: '3'
services:  
  # pgAdmin for database management
  pgadmin:
    image: dpage/pgadmin4:latest
    container_name: postgres_webinterface
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@example.com
      PGADMIN_DEFAULT_PASSWORD: adminpassword
    ports:
      - "6420:80"
```
Run ``docker-compose up`` command to install and check the url ``http://localhost:6420/`` to see the visual interface.

## Topics and Service Communication:
### Kafka Topics:
Create following topics from Kafka panel by clicking on topics in the control center [here](http://localhost:9021/clusters/)
1. ``user-registration:`` To notify other services when a new user is registered through user service API.
2. ``product-update:`` Anytime there's a change to the product catalog.
3. ``order-placed:`` When an order is placed by the user though order service API.
4. ``payment-success:`` When a payment is successfully processed.
5. ``payment-failure:`` When a payment processing fails.
6. ``dlq:`` dlq stands for Dead Letter Queues.

### Service Communication:
Create service API in a separate directory responsible for the below services.
1. ``User Service API:`` When a user registers, the User Service publishes a message to the user-registration topic. The message might contain basic user details like user ID, username, and email.
2. ``Product Service API:`` Publishes to product-update.
3. ``Order Service API:`` The Order Service, which is subscribed to the user-registration topic, receives the message and stores essential details (like user ID) in its own database. It doesn't need to store all details; just enough to validate future orders. For instance, it might maintain a simple table with user IDs of registered users.
4. ``Payment Service API:`` Listens to order-placed, publishes to either payment-success or payment-failure. The Order Service listens to these topics and updates the order status accordingly in its own database.

### Designing Fault Tolerance
1. **Retry Mechanisms:** Implement a retry mechanism for each service when communicating with Kafka. If publishing to a topic fails, the service should retry for a configurable number of times before logging an error.
2. **Database Transactions:** Ensure that database operations are atomic. For instance, when placing an order, use transactions to ensure that inventory updates and order record creations are atomic.
3. **Dead Letter Queues (DLQ):** In Kafka, implement DLQs for failed messages. If a message fails to process after a number of attempts, it's sent to the DLQ. This ensures no message is lost and can be inspected later for issues.

## Database Setup:
As per our directory structure corrosponding to each microservices(User Service, Product Service, Order Service, Payment Service), we will setup the database for each separate microservices.
Checkout the database script along with the tables we have put in sub-directory in a following way:
```
    user-service <Direcory>
    |__api <Sub-direcory>
        |__user-service.py
        |__authentication.py
    |__user_service_db <Sub-direcory>
        |__docker-compose.yml
    |__user-service.sql 
        
```
Run the user-service.sql file to create and setup the database and tables. Repeat the same process for other microservice databases.

## API and End points:
1. **User Service End Points:** 
    - We have used ``.env`` file to configure all necessary configurations related to database, kafka service and API host.
    - We have also used a middleware authentication like ``bearer tokan`` to authenticate the API to restrict un-authorised access. A separate file named ``authentication.py`` is used and imported in main ``user-service.py`` file.
    - ``http://< configured-ip-address >/users/register :`` This service end-point is used to make registration using ``POST`` method. As a response it will gives an id of the registered user. Once a user get successfully registers we were initiating producer to send a message to the appropriate topic ``user-registration``.
    - To run the service, first we have to initialise the virtual environment of python, here in our case its ``env_user``. Navigate to the ``api`` directory and run the command ``source /env_user/bin/activate``. This will run the virtual environment. Then install the necessary sanic framework and its libraries like:

        ```
        pip install sanic
        pip install python-decouple
        pip install asyncpg
        pip install confluent_kafka        
        ```

    - ``http://< configured-ip-address >/users/login :`` This end-point is used to authenticate login using ``POST`` method. As a response it will gives user information.
    - ``http://< configured-ip-address >/users/bd5f8583-83a4-40c4-8ec7-18a685eef130 :`` This end-point is used to get user information using ``GET`` method. The alphanumeric id represents the user id.
    - There were two methods. Either run directly through the python code or via sanic.
    - Command to run via sanic: ``sanic user-service:app --host=0.0.0.0 --port=1604 --dev``
    - Command to run via python: ``python user-service.py``
    

2. **Product Service End Points:** 
    - Just like the above User Service same configurations and steps will be followed.
    - ``http://< configured-ip-address >/products :`` This service end-point is used to create product using ``POST`` method. As a response it will gives an id of the product. Once a product get successfully created we were initiating producer to send a message to the appropriate topic ``product-update``.
    - ``http://< configured-ip-address >/products/list/ :`` This end-point is used to get the listing of all the products using ``GET`` method. We can pass ``limit`` and ``offset`` parameter to get products in paginated form.
    - ``http://< configured-ip-address >/products/bd5f8583-83a4-40c4-8ec7-18a685eef130 :`` This end-point is used to get product information using ``GET`` method. The alphanumeric id represents the product id.

3. **Order Service End Points:** 
    - Just like the above User Service same configurations and steps will be followed.
    - ``http://< configured-ip-address >/orders :`` This service end-point is used to create order using ``POST`` method. As a response it will gives an id of the order. Once an order get successfully created we were initiating producer to send a message to the appropriate topic ``order-placed``. We are also checking if the user is valid from a table named ``registered_users`` in which a user id gets stored when registration happened from User Service via a consumer which is subscribed to ``user-registration`` topic.
    - ``http://< configured-ip-address >/products/list/ :`` This end-point is used to get the listing of all the products using ``GET`` method. We can pass ``limit`` and ``offset`` parameter to get products in a paginated form.
    - ``http://< configured-ip-address >/products/bd5f8583-83a4-40c4-8ec7-18a685eef130 :`` This end-point is used to get product information using ``GET`` method. The alphanumeric id represents the product id.
    - File ``consumer.py`` is an individual python code to run consumer which were subscribed to some topics like ``user-registration``, ``payment-success`` and ``payment-failure`` and continuously running to catch success and failure of topic processing. In case of failure we were sending the errors to another topic called ``dlq``.

4. **Payment Service End Points:** 
    - Just like the above User Service same configurations and steps will be followed.
    - ``http://< configured-ip-address >/payments :`` This service end-point is used to create payment using ``POST`` method. As a response it will gives an id of the payment. Once a payment get ``Paid / Failed`` we were initiating producer to send a message to the appropriate topic ``payment-success`` and ``payment-failure``.    
    - ``http://< configured-ip-address >/payments/bd5f8583-83a4-40c4-8ec7-18a685eef130 :`` This end-point is used to get payment information using ``GET`` method. The alphanumeric id represents the payment id.

## Postman collection for all the API's:
Check the ``Microservice-Orders.postman_collection.json`` collection file to import in a postman to run the services.
