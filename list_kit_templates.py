import os
import requests
import json

api_key = os.getenv("KIT_API_KEY")

response = requests.get(
    "https://api.kit.com/v4/email_templates",
    headers={
        "X-Kit-Api-Key": api_key
    },
    timeout=30
)

print("STATUS:", response.status_code)
print(json.dumps(response.json(), indent=2))
