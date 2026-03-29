import requests
import time
import json

base_url = "http://127.0.0.1:8000/api/query"

queries = [
    {
        "name": "SIMPLE FACTUAL",
        "query": "What is Python?",
        "mode": "auto"
    },
    {
        "name": "COMPLEX REASONING",
        "query": "List all the differences between Pinecone and Qdrant and explain why one is better for dynamic scaling.",
        "mode": "auto"
    }
]

print("🚀 Starting Execution Router Test\n" + "="*50)

for q in queries:
    print(f"\n🧪 Testing {q['name']} Query:")
    print(f"  Query: \"{q['query']}\"")
    
    start_time = time.time()
    try:
        response = requests.post(base_url, json={"query": q["query"], "mode": q["mode"]})
        duration = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            llm_used = data['transparency']['llm_used'] 
            # If we see multiple stages (like critic), it used complex
            # The transparency trace has 'strategies' and 'auto_tuned_params' if complex
            is_complex = bool(data['transparency'].get('strategies', {}))
            
            print(f"  ✅ Success in {duration:.2f}s")
            print(f"  🧠 Routed to: {'MULTI-AGENT (qwen3-32b)' if is_complex else 'LIGHTWEIGHT (llama-3.1-8b)'}")
            print(f"  💬 Answer snippet: {data['answer'][:100]}...")
        else:
            print(f"  ❌ Failed with {response.status_code}: {response.text}")
    except Exception as e:
         print(f"  ❌ Error: {e}")
         
print("\n" + "="*50 + "\n🏁 Test Complete")
