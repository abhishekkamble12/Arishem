import mysql.connector

try:
    # Connect without specifying database
    connection = mysql.connector.connect(
        host='database-1-instance-1.ca9cic2mk50a.us-east-1.rds.amazonaws.com',
        port=3306,
        user='admin',
        password='abhi121205'
    )
    
    cursor = connection.cursor()
    
    # Create the database that matches your .env file
    cursor.execute("CREATE DATABASE IF NOT EXISTS `database-1`")
    print("✅ Database 'database-1' created successfully!")
    
    # Show all databases to confirm
    cursor.execute("SHOW DATABASES")
    databases = cursor.fetchall()
    print("Available databases:")
    for db in databases:
        print(f"  - {db[0]}")
    
    cursor.close()
    connection.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
