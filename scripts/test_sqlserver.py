from os import getenv
from dotenv import load_dotenv
from mssql_python import connect

load_dotenv()

conn = connect(getenv("SQL_CONNECTION_STRING"))
cur = conn.cursor()
cur.execute("SELECT TOP 1 1 AS ok")
row = cur.fetchone()
print(row)
cur.close()
conn.close()
