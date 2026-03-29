import requests
import json

base_url = "http://127.0.0.1:8000/api/query"
q = "List all the differences between Pinecone and Qdrant and explain why one is better for dynamic scaling."
response = requests.post(base_url, json={"query": q, "mode": "auto"})
print(json.dumps(response.json(), indent=2))
