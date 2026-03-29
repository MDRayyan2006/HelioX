import subprocess
import json
import os

def main():
    env = os.environ.copy()
    env["API_KEY"] = "sk-user-83uVcuq13LxM78LmDI4ULaKEWOrGvGjnBK42_AZYZUCAddAd0gVXO3qX8opkaOK-ZXn-IwILsruVsdP5A7z3TUFV0-Z9vBhnMm3oystpxM_CeimiTqLqSEgvWwcDWqMP044"

    proc = subprocess.Popen(["npx", "-y", "@testsprite/testsprite-mcp@latest"], 
                            env=env, 
                            stdin=subprocess.PIPE, 
                            stdout=subprocess.PIPE,
                            text=True,
                            shell=True)

    proc.stdin.write(json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}
    }) + "\n")
    proc.stdin.flush()
    proc.stdout.readline() # init response

    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}) + "\n")
    proc.stdin.flush()
    
    tools_resp = proc.stdout.readline()
    try:
        data = json.loads(tools_resp)
        for tool in data.get("result", {}).get("tools", []):
            print(f"--- TOOL: {tool['name']} ---")
            print(f"Desc: {tool['description']}")
            print(f"Schema: {json.dumps(tool.get('inputSchema', {}), indent=2)}\n")
    except Exception as e:
        print("Error parsing:", e, tools_resp)
        
    proc.terminate()

if __name__ == "__main__":
    main()
