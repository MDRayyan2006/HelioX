import subprocess
import json
import os

def call_testsprite():
    env = os.environ.copy()
    env["API_KEY"] = "sk-user-83uVcuq13LxM78LmDI4ULaKEWOrGvGjnBK42_AZYZUCAddAd0gVXO3qX8opkaOK-ZXn-IwILsruVsdP5A7z3TUFV0-Z9vBhnMm3oystpxM_CeimiTqLqSEgvWwcDWqMP044"

    print("Starting testsprite MCP to execute test suite...")
    proc = subprocess.Popen(["npx", "-y", "@testsprite/testsprite-mcp@latest"], 
                            env=env, 
                            stdin=subprocess.PIPE, 
                            stdout=subprocess.PIPE,
                            text=True,
                            shell=True)

    # Initialize
    proc.stdin.write(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}
    }) + "\n")
    proc.stdin.flush()
    proc.stdout.readline()

    # Call testsprite_execute
    req = {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {
            "name": "testsprite_execute",
            "arguments": {
                "projectPath": "c:\\helioLasthope"
            }
        }
    }
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    
    # Wait for result
    resp = proc.stdout.readline()
    try:
        data = json.loads(resp)
        result = data.get("result", {})
        if result.get("isError"):
            print("ERROR from TestSprite:", result)
        else:
            print("TestSprite Output:")
            for content in result.get("content", []):
                print(content.get("text", ""))
    except Exception as e:
        print("Failed to parse response:", e)
        print("Raw:", resp)

    proc.terminate()

if __name__ == "__main__":
    call_testsprite()
