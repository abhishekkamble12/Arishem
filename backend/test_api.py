import json
import urllib.request
import urllib.error
import time

BASE_URL = "http://127.0.0.1:8000"

def make_request(path, method="GET", headers=None, data=None):
    url = f"{BASE_URL}{path}"
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
        
    req_data = None
    if data:
        req_data = json.dumps(data).encode("utf-8")
        
    req = urllib.request.Request(url, data=req_data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            resp_body = response.read().decode("utf-8")
            return response.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode("utf-8")
        return e.code, json.loads(resp_body) if resp_body else {"error": e.reason}
    except Exception as e:
        return 500, {"error": str(e)}

def run_tests():
    print("=== Start End-to-End API Integration Verification ===")
    
    # Generate a unique email to avoid "already registered" errors
    timestamp = int(time.time())
    email = f"tester_{timestamp}@example.com"
    password = "SecurePassword123!"
    
    # 1. Test Registration
    print(f"\n1. Registering user: {email}...")
    reg_payload = {
        "email": email,
        "password": password,
        "password2": password,
        "role": "editor"
    }
    status, res = make_request("/app/auth/register", method="POST", data=reg_payload)
    print(f"   Status: {status}")
    print(f"   Response: {json.dumps(res, indent=2)}")
    if status != 201:
        print("[-] Registration failed. Exiting.")
        return

    # 2. Test Login
    print(f"\n2. Logging in as {email}...")
    login_payload = {
        "email": email,
        "password": password
    }
    status, res = make_request("/app/auth/login", method="POST", data=login_payload)
    print(f"   Status: {status}")
    if status != 200:
        print("[-] Login failed. Exiting.")
        return
        
    access_token = res["tokens"]["access"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    print("   [+] Successfully logged in and retrieved JWT access token.")

    # 3. Test Auth Me
    print("\n3. Testing authenticated /auth/me endpoint...")
    status, res = make_request("/app/auth/me", method="GET", headers=auth_headers)
    print(f"   Status: {status}")
    print(f"   Response: {json.dumps(res, indent=2)}")
    if status != 200:
        print("[-] Auth Me verification failed.")
        return

    # 4. Test Ingested Files List
    print("\n4. Retrieving list of ingested files from vector database...")
    status, res = make_request("/app/ai/files", method="GET", headers=auth_headers)
    print(f"   Status: {status}")
    print(f"   Response: {json.dumps(res, indent=2)}")

    # 5. Test RAG Query
    print("\n5. Testing RAG AI Query (triggers Qdrant search & Bedrock LLM converse)...")
    query_payload = {
        "question": "What is skills?",
        "top_k": 3
    }
    status, res = make_request("/app/ai/query", method="POST", headers=auth_headers, data=query_payload)
    print(f"   Status: {status}")
    print(f"   Response: {json.dumps(res, indent=2)}")
    if status == 200:
        print("\n[+] Success! The entire RAG pipeline (MySQL, Qdrant, Bedrock Claude 3.7) is working perfectly!")
    else:
        print("\n[-] RAG Query execution failed.")

if __name__ == "__main__":
    run_tests()
