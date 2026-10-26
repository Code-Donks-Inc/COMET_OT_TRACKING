import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text, URL

# Load settinging from the .env file in the project folder
load_dotenv()

password = os.getenv("POSTGRES_PASSWORD")

if not password:
        raise RuntimeError(
                "POSTGRES_PASSWORD is missing from you .env file."
        )

# build the connection URL safely without exposing the password.
connection_url = URL.create(
    drivername="postgresql+psycopg",
    username="otintel",
    password=password,
    host="localhost",
    port=5432,
    database="otintel",    
)

engine = create_engine(
    connection_url,
    pool_pre_ping=True,
)

try:
    with engine.connect() as connection:
        result = connection.execute(
            text("""
                SELECT
                    c.name AS client,
                    a.asset_tag,
                    a.vendor,
                    a.product,
                    a.version
                    FROM clients AS c
                JOIN assets AS a ON a.client_id = c.id
                ORDER BY a,asset_tag
            """)
        )

        print("Connected to PostgreSQL successfully!")
        print()

        for row in result:
            print(
                 f"Client:  {row.client} | "
                 f"Asset: {row.asset_tag} | "
                 f"Vendor: {row.vendor} | "
                 f"Product: {row.product} | "
                 f"Version: {row.version}"
            )

finally:
     engine.dispose()