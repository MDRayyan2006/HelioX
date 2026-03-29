from services.query.structured_analyzer import analyze_query

queries = [
    "name all projects",
    "list all features",
    "what are the types of chunks out there",
    "show all documents",
    "how to run the server",
    "what is a vector",
    "compare fast api and flask"
]

for q in queries:
    res = analyze_query(q)
    print(f"Q: '{q}' -> Type: {res.query_type}")

print("Intent backwards compat test:", analyze_query("hello").intent)
