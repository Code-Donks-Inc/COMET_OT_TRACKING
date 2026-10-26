import io
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text

# WARNING Create .env with unique password 'POSTGRES_PASSWORD" string 
# Load the Existing database password from .env
load_dotenv()

password = os.getenv("POSTGRES_PASSWORD")

st.set_page_config(
    page_title="OT Vulnerability Intelligence",
    page_icon="🛡️",
    layout="wide",
)

st.title("OT Vulnerability Intelligence")
st.write("Your internal OT asset inventory dashboard")

if not password:
    st.error("Database Password missing. Check your .env file")
    st.stop()

# connect to PostgreSQL database as before
connection_url = URL.create(
    drivername="postgresql+psycopg",
    username="otintel",
    password=password,
    host=os.getenv("DB_HOST", "localhost"),
    port=5432,
    database="otintel",
)

# -----------------MANUAL BACKUP SECTION ------------------
engine = create_engine(connection_url, pool_pre_ping=True)

def request_backup():
    """ Create a manual backup job for the background worker."""

    with engine.begin()as connection:
        job_id = connection.execute(
            text("""
                INSERT INTO public.backup_jobs (trigger_type, status)
                VALUES ('manual', 'pending')
                RETURNING id
            """)
        ).scalar_one()

    return job_id

def get_backup_history():
    """Retrieve the 20 most recent backup jobs"""

    query = text("""
        SELECT
            id as "Job ID",
            trigger_type AS "Trigger",
            status AS "status",
            requested_at AS "Requested",
            completed_at AS "Completed",
            filename AS "Filename",
            file_size_bytes AS "Size (bytes)"
        FROM public.backup_jobs
        ORDER BY requested_at DESC, id DESC
        LIMIT 20
    """)
    with engine.connect() as connection:
        return pd.read_sql(query,connection)

st.subheader("Database Backup")

if st.button("Request Manual Backup"):
    try:
        job_id = request_backup()

        st.success(
            f"Backup job {job_id} submitted successfully."
    )

    except Exception as exc:
        st.error(
            "Unable to submit backup request. "
            "Check the database connection and application logs."
        )

# --------------BACKUP HISTORICAL SECTION ---------------
st.subheader("Backup History")

st.button("Refresh Backup History")

try:
    history_df =get_backup_history()

    if history_df.empty:
        st.info("No backup jobs have been recorded")
    else:
        st.dataframe(
            history_df,
            width="stretch",
            hide_index=True
        )

except Exception as exc:
    st.error("Unable to load backup history.")

try:
    with engine.connect() as connection:
        query = text("""
            SELECT
                c.name AS client,
                a.asset_tag AS asset,
                a.vendor,
                a.product,
                a.model,
                a.version,
                a.criticality,
                a.last_seen
            FROM clients AS c
            JOIN assets AS a ON a.client_id = c.id
            ORDER BY c.name, a.asset_tag
        """)

        df= pd.read_sql(query, connection)

#-----------------KPI OVERVIEW--------------------------------
    st.subheader("Inventory overview")

    total_assets = len(df)
    total_clients = df["client"].nunique() if not df.empty else 0

    col1, col2 = st.columns(2)
    col1.metric("Clients", total_clients)
    col2.metric("Assets", total_assets)

   #-----------------------------ASSET INVENTORY DISPLAY--------------------------------
    if df.empty:
        st.info("No assets found. Import Assessment results later.")
    else:
        st.subheader("Asset inventory")

        #let the user select a client
        clients = ["All clients"] + sorted(
            df["client"].unique().tolist()
            )

        selected_client = st.selectbox(
            "Filter by Client",
            options=clients,
        )

        #display only the selected clients assets
        if selected_client == "All clients":
            filtered_df = df
        else:
            filtered_df = df[df["client"] == selected_client]

        #  Show counts for current selection
        st.caption(f"Showing {len(filtered_df)} assets")

        st.dataframe(
            filtered_df,
            width='stretch',
            hide_index=True
        )

    # -----------------IMPORT CSV FUNCTION --------------------------------    
    st.divider()
    st.header("Import OT Assets")

    uploaded_file = st.file_uploader(
        "Choose an asset CSV file",
        type=["csv"],
        help="Upload an asset inventory export to preview and validate."
    )

    if uploaded_file is not None:
        if uploaded_file.size > 5 * 1024 * 1024:
            st.error("file exceeds the 5 MB limit")
        else:
            try:
                import_df = pd.read_csv(
                    io.BytesIO(uploaded_file.getvalue()),
                    dtype=str,
                    keep_default_na=False,
                )

                required = [
                    "client",
                    "asset_tag",
                    "vendor",
                    "product",
                    "version",
                ]
                optional = ["model", "criticality"]

                missing = [
                    col for col in required
                    if col not in import_df.columns
                ]

                if missing:
                    st.error(
                        "Missing Required columns: "
                        + ", ".join(missing)
                    )
                else:
                    #add optional columns if absent.
                    for col in optional:
                        if col not in import_df.columns:
                            import_df[col] = ""

                    columns = required + optional
                    import_df = import_df[columns].copy()

                    #remove accidental spaces around values
                    for col in columns:
                        import_df[col] = (
                            import_df[col].astype(str).str.strip()
                        )

                    errors = []

                    #required fields must not be blank
                    blank_rows = import_df[
                        import_df[required].eq("").any(axis=1)
                    ].index.tolist()

                    if blank_rows:
                        errors.append(
                            "Required fields are blank on CSV row(s): "
                            + ", ".join(str(i+2) for i in blank_rows)
                        )

                    #duplicate asset tags in one upload are ambiguous
                    duplicates = import_df.duplicated(
                        subset=["client", "asset_tag"],
                        keep=False,
                    )

                    if duplicates.any():
                        errors.append(
                            "Duplicate client/asset-tag pairs exist "
                            "in the upload file."
                        )

                    #clients must already exist in database
                    with engine.connect() as conn:
                        existing_clients = set(
                            pd.read_sql(
                                text("SELECT name FROM clients"),
                                conn,
                            )["name"].tolist()
                        )

                        unknown_clients = sorted(
                            set(import_df["client"]) - existing_clients
                        )

                        if unknown_clients:
                            errors.append(
                                "These clients do not exist in the "
                                "database: "
                                + ", ".join(unknown_clients)
                            )

                        # do not silently overwrite existing assets
                        existing_assets = []
                        for row in import_df.to_dict("records"):
                            found = conn.execute(
                                text("""
                                    SELECT 1
                                    FROM assets a
                                    JOIN clients c
                                      ON c.id = a.client_id
                                    WHERE c.name = :client
                                      AND a.asset_tag = :asset_tag
                                """),
                                {
                                    "client": row["client"],
                                    "asset_tag": row["asset_tag"]
                                },
                            ).first()

                            if found:
                                existing_assets.append(
                                    f'{row["client"]} / '
                                    f'{row["asset_tag"]}'
                                )
                    if existing_assets:
                        errors.append(
                            "These assets already exist: "
                            + "; ".join(existing_assets)
                            + ". Update or reconcile them seperately."
                        )

                    st.subheader("Import preview")
                    st.dataframe(
                        import_df,
                        width='stretch',
                        hide_index=True,
                    )

                    if errors:
                        for error in errors:
                            st.error(error)
                        st.warning(
                            "Nothing was imported. Correct the CSV"
                            "and upload it again"
                        )
                    else:
                        st.success(
                            f"{len(import_df)} rows passed validation"
                        )

                        if st.button(
                            "Import validated assets", type="primary"):
                            inserted = 0

                            #all inserts commit together or roll back
                            with engine.begin() as conn:
                                client_rows = conn.execute(
                                    text("SELECT id, name FROM clients")
                                ).all()
                                client_ids = {
                                    row.name: row.id
                                    for row in client_rows
                                }

                                for row in import_df.to_dict("records"):
                                    result = conn.execute(
                                        text("""
                                            INSERT INTO assets(
                                                client_id,
                                                asset_tag,
                                                vendor,
                                                product,
                                                model,
                                                version,
                                                criticality
                                                )
                                                VALUES (
                                                    :client_id,
                                                    :asset_tag,
                                                    :vendor,
                                                    :product,
                                                    :model,
                                                    :version,
                                                    :criticality
                                                )
                                                ON CONFLICT(
                                                    client_id, asset_tag
                                                ) DO NOTHING
                                            """),
                                            {
                                                "client_id": client_ids[row["client"]],
                                                "asset_tag": row["asset_tag"],
                                                "vendor": row["vendor"],
                                                "product": row["product"],
                                                "model": row["model"] or None,
                                                "version": row["version"],
                                                "criticality": row["criticality"] or "Unknown"
                                            },
                                     )
                                    inserted += result.rowcount
                                st.success(
                                    f"Import Complete: {inserted} "
                                    "new assets added."
                                )
                                st.info(
                                    "Refresh the page to update the "
                                    "Inventory Table"
                                )

            except (ValueError, UnicodeDecodeError) as exc:
                st.error(f"Could not read the CSV: {exc}")

except Exception as exc:
    st.error("unable to load asset inventory.")
    st.code(f"{type(exec).__name__}: {exc}")
    st.info(
        " Check that PostgreSQL is running and that the "
        "clients and assets tables exist."
    )

finally:
    engine.dispose()

