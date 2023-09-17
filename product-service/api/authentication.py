from sanic.request import Request
from sanic.exceptions import Unauthorized
from sanic.response import json

# Define a secret token for demonstration purposes
SECRET_TOKEN = 'mySecretToKen'

def authenticate(request: Request):
    authorization = request.headers.get('Authorization')
    if not authorization:
        raise Unauthorized("Missing Bearer Token")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        raise Unauthorized("Invalid Token Format")

    token = parts[1]
    if token != SECRET_TOKEN:
        raise Unauthorized("Invalid Token")


async def authenticate_middleware(request):
    try:
        authenticate(request)
    except Unauthorized as e:
        return json({"message":str(e)}, status=401) 