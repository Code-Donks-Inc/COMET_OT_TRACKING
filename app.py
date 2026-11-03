import io
import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import IntegrityError #handle constraint violatons in site creation input boxes

# WARNING Create .env with unique password 'POSTGRES_PASSWORD" string
# Load the Existing database password from .env
load_dotenv()

password = os.getenv("POSTGRES_PASSWORD")

st.set_page_config(
    page_title="OT Vulnerability Intelligence",
    page_icon="🛡️",
    layout="wide",
)

st.title("COMET")
st.write(
    "Change Operations, Management, Engineering & Threat Intelligence"
    )

# Require Microsoft Entra ID authentication before accessing COMET.
if not st.user.is_logged_in:
    st.info("Sign in with your organizational Microsoft account.")

    if st.button("Sign in with Microsoft", type="primary"):
        st.login("microsoft")

    st.stop()

# Require stable Microsoft Entra identity claims.
entra_tenant_id = st.user.get("tid")
entra_object_id = st.user.get("oid")

if not entra_tenant_id or not entra_object_id:
    st.error(
        "Authentication succeed, but required Microsoft Entra "
        "identity claims are missing. Access Denied."
    )
    st.stop()

    st.write("Tenant ID available:", bool(entra_tenant_id))
    st.write("Object ID available:", bool(entra_object_id))

    st.stop()

# Authenticated session
st.sidebar.success("Signed in with Microsoft")

# Development-only identity verification
with st.sidebar.expander("Authentication Identity (Development)"):
    st.write("Authenticated:", st.user.is_logged_in)
    st.write("Name:", st.user.get("name", "Not Provided"))
    st.write("Email:", st.user.get("email", "Not Provided"))
    st.write("Object ID:", st.user.get("oid", "Not Provided"))
    st.write(
        "Tenant ID:",
        "Available" if st.user.get("tid") else "Not Provided"
    )

if st.sidebar.button("Sign Out"):
    st.logout()

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

#--------- Confim Asset Dialogue Box----------------------------
@st.dialog("Confirm Asset Assignment Request")
def confirm_asset_assignment(
    client_name,
    asset_tag,
    current_assignment,
    destination,
    reason,
    asset_id,
    cabinet_id,
    original_cabinet_id
):

    validation_query = text("""
        SELECT
            a.id AS asset_id,
            a.cabinet_id AS current_cabinet_id,
            cab.id AS destination_cabinet_id
        FROM public.assets AS a
        JOIN public.clients AS c
            ON c.id = a.client_id
        JOIN public.cabinets AS cab
            ON cab.client_id = a.client_id
        WHERE a.id = :asset_id
          AND cab.id = :cabinet_id
          AND c.name = :client_name
    """)

    st.warning(
        "This is a request for approval. "
        "Confirming does not change the assets assignment."
    )

    st.write(f"**Client:** {client_name}")
    st.write(f"**Asset:** {asset_tag}")
    st.write(f"**Current assignment:** {current_assignment}")
    st.write(f"**Proposed destination:** {destination}")
    st.write(f"**Justification:** {reason}")

    if st.button("Cancel", key="cancel_assignment_confirmation"):
        st.rerun()

    if st.button(
        "Confirm Request",
        key="confirm_assignment_request",
        type="primary"
    ):
        with engine.connect() as conn:
            validation_result = conn.execute(
                validation_query,
                {
                    "asset_id": asset_id,
                    "cabinet_id": cabinet_id,
                    "client_name": client_name
                }
            ).mappings().one_or_none()

        if not reason.strip():
            st.error(
                "A justification is required before confirming "
                "an asset assignment request."
            )
        elif validation_result is None:
            st.error(
                "The asset or destination cabinet is no longer valid "
                "for the selected client. Cancel and Refresh the Page."
            )
        elif (
            validation_result["current_cabinet_id"]
            !=original_cabinet_id
        ):
            st.error(
                "This asset's cabinet assignment has changed "
                "since this preview was opened. "
                "Cancel and refresh before creating a request."
            )
        elif(
            validation_result["current_cabinet_id"] is not None
            and int(validation_result["current_cabinet_id"]) == cabinet_id
        ):
            st.error(
                "This asset is already assigned to the selected cabinet. "
                "No assignment change is necessary."
            )
        else:
            st.warning(
                "Request submission is not yet enabled. "
                "No changes have been saved."
            )

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

#------------------ASSET LOCATION HIERARCHY----------------------------
    st.divider()
    st.header("Asset Location Hierarchy")
    st.caption("Browse OT assets by client, site, building and cabinet.")

    hierarchy_query = text("""
        SELECT
            c.name AS client,
            s.name AS site,
            b.name AS building,
            cab.name AS cabinet,
            a.asset_tag AS asset
        FROM public.clients AS c
        LEFT JOIN public.sites AS s
            ON s.client_id = c.id
        LEFT JOIN public.buildings AS b
            ON b.site_id = s.id
            AND b.client_id = c.id
        LEFT JOIN public.cabinets AS cab
            ON cab.building_id = b.id
            AND cab.client_id = c.id
        LEFT JOIN public.assets AS a
            ON a.cabinet_id = cab.id
            AND a.client_id = c.id
        ORDER BY
            c.name, s.name, b.name, cab.name, a.asset_tag
    """)

    with engine.connect() as conn:
        hierarchy_df = pd.read_sql_query(hierarchy_query, conn)

    hierarchy_clients = ["All clients"] + sorted(
        hierarchy_df["client"].dropna().unique().tolist()
    )

    hierarchy_selected_client = st.selectbox(
        "Filter locations by client",
        options=hierarchy_clients,
        key="hierarchy_client_filter"
    )

    if hierarchy_selected_client == "All clients":
        filtered_hierarchy_df = hierarchy_df
    else:
        filtered_hierarchy_df = hierarchy_df[
            hierarchy_df["client"] == hierarchy_selected_client
        ]

    if filtered_hierarchy_df["site"].isna().all():
        st.info(
            "No asset locations have been configured for this selection. "
            "Sites, buildings, and cabinets will appear here "
            "once they are created."
        )
    else:
        st.dataframe(
            filtered_hierarchy_df,
            width="stretch",
            hide_index=True
        )

#------------------SITE MANAGEMENT-------------------------------------
    st.subheader("Site Management")
    st.caption("Create and manage sites belonging to a client")

    site_client = st.selectbox(
        "Select client for new site",
        options=sorted(hierarchy_df["client"].dropna().unique().tolist()),
        key="site_client_selection"
        )

    site_name = st.text_input(
        "New site name",
        placeholder="Example: Minneapolis Manufacturing Plant",
        max_chars=200,
        key="new_site_name"
    )

    create_site_clicked = st.button(
        "Create Site",
        key="create_site_button"
    )

    create_site_query = text("""
        INSERT INTO public.sites (client_id, name)
        SELECT id, :site_name
        FROM public.clients
        WHERE name = :client_name
        RETURNING id
    """)

    if create_site_clicked:
        cleaned_site_name = site_name.strip()

        if not cleaned_site_name:
            st.error("Site name cannot be empty.")
        else:
            try:
                with engine.begin() as conn:
                    new_site_id = conn.execute(
                        create_site_query,
                        {
                            "site_name": cleaned_site_name,
                            "client_name": site_client
                        }
                    ).scalar_one()

                st.success(
                    f"Site '{cleaned_site_name}' created successfully. "
                    f"Site ID: {new_site_id}"
                )

            except IntegrityError:
                st.error(
                    "A site with this name already exists for "
                    "the selected client."
                )

            except Exception:
                st.error(
                    "Unable to create the site. "
                    "Please contact the administrator if the problem persists."
                )

#------------------BUILDING MANAGEMENT--------------------------------
    st.divider()
    st.subheader("Building Management")
    st.caption("Create buildings within an existing client site.")

    building_client = st.selectbox(
        "Select client for new building",
        options=sorted(
            hierarchy_df["client"].dropna().unique().tolist()
        ),
        key="building_client_selection"
    )

    building_sites_query = text("""
        SELECT
            s.id,
            s.name
        FROM public.sites AS s
        JOIN public.clients AS c
            ON c.id = s.client_id
        WHERE c.name = :client_name
        ORDER BY s.name, s.id
    """)

    with engine.connect() as conn:
        building_sites_df = pd.read_sql_query(
            building_sites_query,
            conn,
            params={"client_name": building_client}
        )

    if building_sites_df.empty:
        st.info(
            "No sites exist for this client. "
            "Create a site before adding buildings"
        )
        building_site_id = None

    else:
        building_site_id = st.selectbox(
            "Select site for new building",
            options=building_sites_df["id"].tolist(),
            format_func=lambda site_id: building_sites_df.loc[
                building_sites_df["id"] == site_id, "name"
            ].iloc[0],
            key="building_site_selection"
        )

    building_name = st.text_input(
        "New Building Name",
        placeholder="Example: Production Building A",
        max_chars=200,
        key="new_building_name"
    )

    create_building_clicked = st.button(
        "Create Building",
        disabled=building_site_id is None,
        key="create_building_button"
    )

    create_building_query = text("""
        INSERT INTO public.buildings (
            client_id,
            site_id,
            name
        )
        SELECT
            s.client_id,
            s.id,
            :building_name
        FROM public.sites AS s
        JOIN public.clients AS c
            ON c.id = s.client_id
        WHERE s.id = :site_id
          AND c.name = :client_name
        RETURNING id
    """)

    if create_building_clicked:
        cleaned_building_name = building_name.strip()

        if not cleaned_building_name:
            st.error("Building name cannot be empty.")
        elif building_site_id is None:
            st.error("Select a valid site before creating a building.")
        else:
            try:
                with engine.begin() as conn:
                    new_building_id = conn.execute(
                        create_building_query,
                        {
                            "building_name": cleaned_building_name,
                            "site_id": int(building_site_id),
                            "client_name": building_client
                        }
                    ).scalar_one_or_none()

                if new_building_id is None:
                    st.error(
                        "The selected site could not be found "
                        "for this client."
                    )
                else:
                    st.success(
                        f"Building '{cleaned_building_name}' "
                        f"created successfully. "
                        f"Building ID: {new_building_id}"
                    )

            except IntegrityError:
                st.error(
                    "The building could not be created because "
                    "a database constraint was violated."
                )

            except Exception:
                st.error(
                    "Unable to create the building. "
                    "Please contact the administrator if the problem persists."
                )
#------------------CABINET MANAGEMENT----------------------------------
    st.divider()
    st.subheader("Cabinet Management")
    st.caption(
        "Create cabinets within existing buildings "
        "while preserving client and site relationships."
    )

    cabinet_client = st.selectbox(
        "Select client for new cabinet",
        options=sorted(
            hierarchy_df["client"].dropna().unique().tolist()
        ),
        key="cabinet_client_selection"
    )

    cabinet_buildings_query = text("""
        SELECT
            b.id AS building_id,
            b.name AS building_name,
            s.id AS site_id,
            s.name AS site_name
        FROM public.buildings AS b
        JOIN public.sites AS s
            ON s.id = b.site_id
            AND s.client_id = b.client_id
        JOIN public.clients AS c
            ON c.id = b.client_id
        WHERE c.name = :client_name
        ORDER BY s.name, b.name, b.id
     """)

    with engine.connect() as conn:
        cabinet_buildings_df = pd.read_sql_query(
            cabinet_buildings_query,
            conn,
            params={"client_name": cabinet_client}
        )

    if cabinet_buildings_df.empty:
        st.info(
            "No buildings exist for this client. "
            "Create a site and building before adding cabinets."
        )
        cabinet_building_id = None
    else:
        cabinet_building_id = st.selectbox(
            "Select a building for a new cabinet",
            options=cabinet_buildings_df["building_id"].tolist(),
            format_func=lambda building_id: (
                cabinet_buildings_df.loc[
                    cabinet_buildings_df["building_id"] == building_id,
                    "site_name"
                ].iloc[0]
                + " / "
                + cabinet_buildings_df.loc[
                    cabinet_buildings_df["building_id"] == building_id,
                    "building_name"
                ].iloc[0]
            ),
            key="cabinet_building_selection"
        )

    cabinet_name = st.text_input(
        "New Cabinet Name",
        placeholder="Example: MCC-01",
        max_chars=200,
        key="new_cabinet_name"
    )

    create_cabinet_clicked = st.button(
        "Create Cabinet",
        disabled=cabinet_building_id is None,
        key="create_cabinet_button"
    )

    create_cabinet_query = text("""
        INSERT INTO public.cabinets (
            client_id,
            building_id,
            name
        )
        SELECT
            b.client_id,
            b.id,
            :cabinet_name
        FROM public.buildings AS b
        JOIN public.sites AS s
            ON s.id = b.site_id
            AND s.client_id = b.client_id
        JOIN public.clients AS c
            ON c.id = b.client_id
        WHERE b.id = :building_id
          AND c.name = :client_name
        RETURNING id
    """)

    if create_cabinet_clicked:
        cleaned_cabinet_name = cabinet_name.strip()

        if not cleaned_cabinet_name:
            st.error("Cabinet name cannot be empty.")
        elif cabinet_building_id is None:
            st.error("Select a valid building before creating a cabinet.")
        else:
            try:
                with engine.begin() as conn:
                    new_cabinet_id = conn.execute(
                        create_cabinet_query,
                        {
                            "cabinet_name": cleaned_cabinet_name,
                            "building_id": int(cabinet_building_id),
                            "client_name": cabinet_client
                        }
                    ).scalar_one_or_none()

                if new_cabinet_id is None:
                    st.error(
                        "The selected building could not be found "
                        "for this client"
                    )
                else:
                    st.success(
                        f"Cabinet '{cleaned_cabinet_name}' "
                        f"created successfully. "
                        f"Cabinet ID: {new_cabinet_id}"
                    )

            except IntegrityError:
                st.error(
                    "The cabinet could not be created because "
                    "a database constraint was violated."
                )

            except Exception:
                st.error(
                    "Unable to create the cabinet. "
                    "Please contact the administrator if the problem persists."
                )

#------------------ASSET CABINET ASSIGNMENT----------------------------
    st.divider()
    st.subheader("Asset Cabinet Assignment")
    st.caption(
        "Assign existing assets to cabinets within the same client. "
        "Asset assignment must preserve client isolation"
    )

    assignment_client = st.selectbox(
        "Select client for asset assignment",
        options=sorted(
            hierarchy_df["client"].dropna().unique().tolist()
        ),
        key="assignment_client_selection"
    )

    assignment_assets_query = text("""
        SELECT
            a.id AS asset_id,
            a.asset_tag,
            a.vendor,
            a.product,
            a.cabinet_id
        FROM public.assets AS a
        JOIN public.clients AS c
            ON c.id = a.client_id
        WHERE c.name = :client_name
        ORDER BY a.asset_tag, a.id
    """)

    with engine.connect() as conn:
        assignment_assets_df = pd.read_sql_query(
            assignment_assets_query,
            conn,
            params={"client_name": assignment_client}
        )

    if assignment_assets_df.empty:
        st.info(
            "No assets exist for this client. "
            "Add assets before assigning them to cabinets."
        )
        assignment_asset_id = None
    else:
        assignment_asset_id = st.selectbox(
            "Select asset to assign",
            options=assignment_assets_df["asset_id"].tolist(),
            format_func=lambda asset_id: (
                assignment_assets_df.loc[
                    assignment_assets_df["asset_id"] == asset_id,
                    "asset_tag"
                ].iloc[0]
            ),
            key="assignment_asset_selection"
        )

    assignment_cabinets_query = text("""
        SELECT
            cab.id AS cabinet_id,
            cab.name AS cabinet_name,
            b.name AS building_name,
            s.name AS site_name
        FROM public.cabinets AS cab
        JOIN public.buildings AS b
            ON b.id = cab.building_id
           AND b.client_id = cab.client_id
        JOIN public.sites AS s
            ON s.id = b.site_id
           AND s.client_id = b.client_id
        JOIN public.clients AS c
            ON c.id = cab.client_id
        WHERE c.name = :client_name
        ORDER BY s.name, b.name, cab.name, cab.id
    """)

    with engine.connect() as conn:
        assignment_cabinets_df =pd.read_sql_query(
            assignment_cabinets_query,
            conn,
            params={"client_name": assignment_client}
        )

    if assignment_cabinets_df.empty:
        st.info(
            "No cabinets exist for this client. "
            "Create a cabinet before assigning assets."
        )
        assignment_cabinet_id = None
    else:
        assignment_cabinet_id = st.selectbox(
            "Select destination cabinet",
            options=assignment_cabinets_df["cabinet_id"].tolist(),
            format_func=lambda cabinet_id: (
                " / ".join(
                    str(value)
                    for value in assignment_cabinets_df.loc[
                        assignment_cabinets_df["cabinet_id"] == cabinet_id,
                        ["site_name", "building_name", "cabinet_name"]
                    ].iloc[0]
                )
            ),
            key="assignment_cabinet_selection"
        )

    if assignment_asset_id is not None:
        selected_asset = assignment_assets_df.loc[
            assignment_assets_df["asset_id"] == assignment_asset_id
        ].iloc[0]

        current_cabinet_id = selected_asset["cabinet_id"]

        if pd.isna(current_cabinet_id):
            st.info(
                f"Asset '{selected_asset['asset_tag']}' "
                f"is currently unassigned."
            )
        else:
            st.info(
                f"Asset '{selected_asset['asset_tag']}' "
                f"is currently assigned to cabinet ID "
                f"{int(current_cabinet_id)}."
            )

        if(
            assignment_asset_id is not None
            and assignment_cabinet_id is not None
        ):
            selected_cabinet = assignment_cabinets_df.loc[
                assignment_cabinets_df["cabinet_id"] == assignment_cabinet_id
            ].iloc[0]

            st.markdown("#### Proposed Asset Assignment")

            current_assignment_label = (
                "Unassigned"
                if pd.isna(current_cabinet_id)
                else f"Cabinet ID {int(current_cabinet_id)} "
            )

            st.write(
                f"**Current Assignment:** {current_assignment_label}"
            )

            st.info(
                "Request status: Draft - not submitted. "
                "Assignment changes require approval."
            )

            st.write(
                f"**Asset:** {selected_asset['asset_tag']}"
            )

            st.write(
                "**Destination:** "
                f"{selected_cabinet['site_name']} / "
                f"{selected_cabinet['building_name']} / "
                f"{selected_cabinet['cabinet_name']}"
            )

            assignment_reason = st.text_area(
                "Reason for assignment",
                placeholder=(
                    "Explain why this asset should be assigned "
                    "to the selected cabinet. "
                    "Example: 'Blueprint, Ctec Work Order, or Other documentation.' "
                ),
                max_chars=1000,
                key="assignment_request_reason"
            )

            if assignment_reason.strip():
                st.write(
                    f"**Proposed change justification:** "
                    f"{assignment_reason.strip()}"
                )

            st.caption(
                "Preview only. No asset assignment has been saved."
            )

            if st.button(
                "Preview Assignment Request",
                key="request_asset_assignment",
                type="primary"
            ):
                if not assignment_reason.strip():
                    st.error(
                        "A reason for assignment is required. Example: 'Blueprint, Ctec Work Order or Other Documetation."
                    )
                elif (
                    pd.notna(current_cabinet_id)
                    and int(current_cabinet_id) == int(assignment_cabinet_id)
                ):
                    st.error(
                        "This asset is already assigned to the selected cabinet. "
                        "Choose a different destination."
                    )
                else:
                    destination_label = (
                        f"{selected_cabinet['site_name']} / "
                        f"{selected_cabinet['building_name']} / "
                        f"{selected_cabinet['cabinet_name']}"
                    )

                    confirm_asset_assignment(
                        client_name=assignment_client,
                        asset_tag=selected_asset["asset_tag"],
                        current_assignment=current_assignment_label,
                        destination=destination_label,
                        reason=assignment_reason.strip(),
                        asset_id=int(assignment_asset_id),
                        cabinet_id=int(assignment_cabinet_id),
                        original_cabinet_id=(
                            None
                            if pd.isna(current_cabinet_id)
                            else int(current_cabinet_id)
                        )
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
    st.code(f"{type(exc).__name__}: {exc}")
    st.info(
        " Check that PostgreSQL is running and that the "
        "clients and assets tables exist."
    )

finally:
    engine.dispose()
