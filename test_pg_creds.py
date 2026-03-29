import psycopg2

def test_credentials():
    common_passwords = ["", "postgres", "password", "root", "admin", "1234", "123456"]
    
    print("Testing common local PostgreSQL passwords:")
    for pwd in common_passwords:
        try:
            conn = psycopg2.connect(
                host="localhost",
                database="postgres", # Using 'postgres' default database to test connection
                user="postgres",
                password=pwd,
                connect_timeout=2
            )
            print(f"✅ SUCCESS! Password is: '{pwd}'")
            conn.close()
            return pwd
        except Exception as e:
            if "password authentication failed" in str(e):
                print(f"❌ Failed for password: '{pwd}'")
            elif 'database "postgres" does not exist' in str(e):
                # If we get here, authentication succeeded but DB doesn't exist
                print(f"✅ SUCCESS! Password is: '{pwd}' (but default DB 'postgres' is missing)")
                return pwd
            else:
                print(f"⚠️ Other error for '{pwd}': {e}")
                
    print("\nCould not automatically determine the password.")
    return None

if __name__ == "__main__":
    test_credentials()
