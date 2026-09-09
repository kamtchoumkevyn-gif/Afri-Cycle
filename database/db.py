# sqlite3 is Python's built-in library for interacting with SQLite databases. It provides a lightweight disk-based database that doesn't require a separate server process and allows access to the database using a nonstandard variant of the SQL query language. This makes it a great choice for small to medium-sized applications, prototyping, and testing.
import sqlite3
import os

#This  build the exact path to the database file, ensuring that it is located in the same directory as this script. This is important for maintaining a consistent and predictable location for the database, especially when the application is deployed or run in different environments.

DB_PATH = os.path.join(os.path.dirname(__file__), 'africycle.db')

#The function get_connection() establishes a connection to the SQLite database specified by DB_PATH. It also sets the row_factory attribute of the connection to sqlite3.Row, which allows us to access columns in the result set by their names instead of by index. This can make the code more readable and easier to maintain.

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row # This allows us to access columns by name.
    return conn

#The function init_db() initializes the database by creating the necessary tables if they do not already exist. It uses the get_connection() function to establish a connection to the database, and then executes SQL commands to create the tables. The cursor object is used to execute these commands, and the changes are committed to the database before closing the connection.
def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    #creates a table named 'users' with the specified columns and constraints if it does not already exist. The table includes an auto-incrementing primary key (id), a unique phone number, a password, a role, an optional guardian phone number, a verified status (defaulting to false), and a timestamp for when the record was created.
    cursor.execute('''                      
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phoneNumber TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            guardianPhoneNumber TEXT,
            verified BOOLEAN DEFAULT 0,
            createdAt TEXT NOT NULL
        )
    ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS material_category (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       name TEXT NOT NULL,
                       description TEXT,
                       referencePhotoUrl TEXT
                       
                   )
     ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS buyer_profile (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       userId INTEGER NOT NULL,
                       workingHours TEXT,
                       latitude REAL,
                       longitude REAL,
                       FOREIGN KEY (userId) REFERENCES users(id)
                   )
     ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS buyer_prices (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       buyerId INTEGER NOT NULL,
                       materialCategoryId INTEGER NOT NULL,
                       pricePerKillo REAL NOT NULL,
                       updatedAt TEXT NOT NULL,
                       FOREIGN KEY (buyerId) REFERENCES users(id),
                       FOREIGN KEY (materialCategoryId) REFERENCES material_category(id)
                       
                   )
    ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS transactions (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       buyerId INTEGER NOT NULL,
                       sellerPhoneNumber TEXT NOT NULL,
                       sellerName TEXT,
                       materialCategoryId INTEGER NOT NULL,
                       weightKg REAL NOT NULL,
                       pricePerKillo REAL NOT NULL,
                       photoUrl TEXT,
                       latitude REAL,
                       longitude REAL,
                       confirmedBySeller BOOLEAN DEFAULT 0,
                       timestamp TEXT NOT NULL,
                       FOREIGN KEY (buyerId) REFERENCES users(id),
                       FOREIGN KEY (materialCategoryId) REFERENCES material_category(id)
                   )
    ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS notifications (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       sellerId INTEGER NOT NULL,
                       buyerId INTEGER NOT NULL,
                       materialCategoryId INTEGER NOT NULL,
                       sellerLatitude REAL,
                       sellerLongitude REAL,
                       estimatedDistanceKm REAL,
                       estimatedTimeMinutes REAL,
                       status TEXT DEFAULT 'pending',
                       createdAt TEXT NOT NULL,
                       FOREIGN KEY (sellerId) REFERENCES users(id),
                       FOREIGN KEY (buyerId) REFERENCES users(id),
                       FOREIGN KEY (materialCategoryId) REFERENCES material_category(id)
                       
                   )
    ''')
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS chat_messages (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       notificationId INTEGER NOT NULL,
                       senderId INTEGER NOT NULL,
                       messageText TEXT NOT NULL,
                       timestamp TEXT NOT NULL,
                       FOREIGN KEY (notificationId) REFERENCES notification(id),
                       FOREIGN KEY (senderId) REFERENCES user(id)
                       
                   )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")
    
if __name__ == '__main__':
    init_db()
    
                   