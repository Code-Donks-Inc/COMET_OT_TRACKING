import os
import uuid
import subprocess
import time
import stat
import tarfile
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
import psycopg

#-------BACKUP VARIABLES ----------
BACKUP_INTERVAL_HOURS = int(
    os.getenv("BACKUP_INTERVAL_HOURS", "24")
)

BACKUP_INTERVAL_SECONDS = BACKUP_INTERVAL_HOURS * 60 * 60

BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

if BACKUP_RETENTION_DAYS < 1:
    raise ValueError("BACKUP_RETENTION_DAYS must be at least 1")

BACKUP_ARCHIVE_RETENTION_YEARS = int(
    os.getenv("BACKUP_ARCHIVE_RENTENTION_YEARS", "3")
)

BACKUP_ARCHIVE_ENABLED = (
    os.getenv("BACKUP_ARCHIVE_ENABLED", "false").lower() == "true"
)

if BACKUP_ARCHIVE_RETENTION_YEARS < 1:
    raise ValueError(
        "BACKUP_ARCHIVE_RETENTION_YEARS must be at least 1"
    )

# Location of the backup script inside the Docker container.
BACKUP_SCRIPT = "/worker/backup.sh"

# Directory where completed backups are stored.
BACKUP_DIR = Path("/backups")

#--------SQL Connection Configuration---------------
def get_connection():
    """Connect to PostgreSQL using Docker environment variables."""
    return psycopg.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
    )

# ---------------- ARCHIVE METADATA FUNCTIONS -----------
def get_registered_monthly_archives():
    """return registered monthly archives without modifying the database."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    archive_filename,
                    archive_year,
                    archive_month,
                    verification_status,
                    retention_expires_at
                FROM public.backup_archives
                ORDER BY archive_year, archive_month
                """
            )
            return cursor.fetchall()
        
def get_monthly_archive_record(archive_filename):
    """return metadata for one registered monthly archive."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    archive_filename,
                    archive_year,
                    archive_month,
                    created_at,
                    verification_status,
                    retention_expires_at
                FROM public.backup_archives
                WHERE archive_filename = %s
                """,
                (archive_filename,)
            )
            return cursor.fetchone()

def get_monthly_archive_by_period(year, month):
    """Return archive metadata for a specific year and month."""
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    archive_filename,
                    archive_year,
                    archive_month,
                    created_at,
                    verification_status,
                    retention_expires_at
                FROM public.backup_archives
                WHERE archive_year = %s
                  AND archive_month = %s
                """,
                (year, month)
            )
            return cursor.fetchone()

def validate_monthly_archive_path(archive_path):
    """Validate a monthly archive path and return its year and month."""
    archive_path = Path(archive_path)

    if any(part in (".", "..")for part in archive_path.parts):
        raise ValueError("Archive path contains invalid directory components")
  
    if not archive_path.is_absolute():
        raise ValueError("Archive path must be absolute")
    
    archive_root = Path("/backups/archives")
    
    if archive_path.parent.parent != archive_root:
        raise ValueError("Invalid archive directory")

    year_text = archive_path.parent.name
    filename = archive_path.name

    if(
        len(year_text) != 4
        or not year_text.isascii()
        or not year_text.isdecimal()
    ):
        raise ValueError("Invalid archive year directory")

    year = int(year_text)

    if not 2000 <= year <= 9999:
        raise ValueError("Archive year is outside the allowed range")

    expected_filename_prefix = f"{year}-"

    if(
        not filename.startswith(expected_filename_prefix)
        or not filename.endswith(".tar.gz")
        or len(filename) != 14
    ):
        raise ValueError("Invalid monthly archive filename")

    month_text = filename[5:7]

    if not month_text.isascii() or not month_text.isdecimal():
        raise ValueError("Invalid archive month")

    month = int(month_text)

    if not 1 <= month <= 12:
        raise ValueError("Archive month must be between 01 and 12")

    return year, month

def validate_monthly_archive_symlinks(archive_path):
    """Reject symbolic links in an existig monthly archive path."""
    archive_path = Path(archive_path)

    #Validate the expected directory and filename first.
    validate_monthly_archive_path(archive_path)

    archive_root = Path("/backups/archives")
    year_directory = archive_path.parent

    for path in (
        Path("/backups"),
        archive_root,
        year_directory,
        archive_path,
    ):
        if path.is_symlink():
            raise ValueError(f"Symbolic link not allowed: {path}")

    if not archive_path.is_file():
        raise FileNotFoundError(
            f"Monthly archive does not exist: {archive_path}"
        )

    return True

def open_monthly_archive_safely(archive_path):
    """Open an existing monthly archive using secure diretory descriptors"""
    return open_monthly_archive_by_descriptor(archive_path)
       
#-----------------BACKUP RETENTION FUNCTIONS--------------
def get_latest_successful_backup():
    """Return the filename of the most recent completed backup"""

    with psycopg.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT filename
                FROM public.backup_jobs
                WHERE status = 'completed'
                  AND filename IS NOT NULL
                ORDER BY completed_at DESC, id DESC
                LIMIT 1
                """
            )

            result = cursor.fetchone()
            
    return result[0] if result else None

def verify_protected_backup():
    """Check whether the latest successful backup file exists"""

    filename = get_latest_successful_backup()

    if filename is None:
        return False

    backup_path = Path("/backups")/filename

    return backup_path.is_file() #Return true when successful backup record exists

#-----------ARCHIVE CREATION AND PATHING------------
def ensure_archive_directory():
    """Create the directory for monthly backup archives."""

    archive_directory = Path("/backups/archives")

    archive_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    return archive_directory

def ensure_year_archive_directory(year):
    """Create and return the archive directory for a given year."""
    year = int(year)

    if year < 2000 or year > 9999:
        raise ValueError("Invalid archive year")

    archive_directory = ensure_archive_directory()

    year_directory = archive_directory / str(year)

    year_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    return year_directory

def get_monthly_archive_path(year, month):
    """Return the compressed archive path for a given year and month."""

    year = int(year)
    month = int(month)

    if month < 1 or month >12:
        raise ValueError("Invalid Archive Month")

    if year < 2000 or year > 9999:
        raise ValueError("Invalid archive year")

    archive_directory = Path("/backups/archives") / str(year)

    archive_filename = f"{year}-{month:02d}.tar.gz"

    return archive_directory/archive_filename

def get_completed_backup_filenames():
    """Return filenames associated with completed backup jobs."""

    with psycopg.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT filename
                FROM public.backup_jobs
                WHERE status = 'completed'
                  AND filename IS NOT NULL
                """
            )

            results = cursor.fetchall()

    return {row[0]for row in results}

def preview_monthly_archive_groups():
    """Group expired backup files by their modification year and month"""

    backup_directory = Path("/backups")
    expired_files = preview_expired_backups()
    completed_filenames = get_completed_backup_filenames()
    protect_filename = get_latest_successful_backup()

    archive_groups = {}

    for filename in expired_files:
        if filename == protect_filename:
            continue

        if filename not in completed_filenames:
            continue

        backup_file = backup_directory / filename

        if not backup_file.is_file():
            continue

        modified_time = datetime.fromtimestamp(
            backup_file.stat().st_mtime,
            tz=timezone.utc
        )

        archive_path = get_monthly_archive_path(
            modified_time.year,
            modified_time.month
        )

        archive_key = str(archive_path)

        archive_groups.setdefault(archive_key, []).append(filename)

    return{
        path: sorted(filenames)
        for path, filenames in sorted(archive_groups.items())
    }

def open_backup_safely(backup_path):
    """Open a regular backup file without following symbolic links."""
    backup_path = Path(backup_path)

    flags = os.O_RDONLY | os.O_NOFOLLOW

    fd = os.open(backup_path, flags)

    try:
        file_info = os.fstat(fd)

        if not stat.S_ISREG(file_info.st_mode):
            raise ValueError(
                f"Backup is not a regular fle: {backup_path.name}"
            )

        return os.fdopen(fd,"rb")
    
    except Exception:
        os.close(fd)
        raise

def create_monthly_archive(archive_path, filenames):
    """Create a compressed monthly archive without deleting originals."""

    archive_path = Path(archive_path)
    backup_directory = Path("/backups")
    archive_root = Path("/backups/archives").resolve()
    archive_path = archive_path.resolve()

    if not archive_path.is_relative_to(archive_root):
        raise ValueError(
            "Archive destination must be inside /backups/archives"
        )

    if archive_path.suffixes[-2:] != [".tar", ".gz"]:
        raise ValueError(
            "Archive filename must end with .tar.gz"
        )


    if not filenames:
        raise ValueError("No backup files provided")

    if len(filenames) != len(set(filenames)):
        raise ValueError("Duplicate backup filenames are not allowed")

    if archive_path.exists():
        raise FileExistsError(
            f"Archive already exists: {archive_path}"
        )

    completed_filenames = get_completed_backup_filenames()
    protected_filename = get_latest_successful_backup()
    expired_filenames = set(preview_expired_backups())

    for filename in filenames:
        if (
            Path(filename).name != filename
            or filename not in completed_filenames
            or filename == protected_filename
            or filename not in expired_filenames
        ):
            raise ValueError(f"Backup not eligible: {filename}")

        backup_file = backup_directory / filename

        if backup_file.is_symlink():
            raise ValueError(f"Symbolic links are not allowed: {filename}")

        if not backup_file.is_file():
            raise FileNotFoundError(filename)

    archive_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to a temporary file until compression succeeds.
    temporary_path = archive_path.with_name(
        f"{archive_path.name}.{uuid.uuid4().hex}.partial"
    )
    temporary_created = False

    try:
        with temporary_path.open("xb") as output:
            temporary_created = True

            with tarfile.open(fileobj=output, mode="w:gz") as archive:
                for filename in filenames:
                    backup_path = backup_directory / filename

                    with open_backup_safely(backup_path) as source:
                        file_info = os.fstat(source.fileno())

                        archive_info = tarfile.TarInfo(name=filename)
                        archive_info.size = file_info.st_size
                        archive_info.mode = 0o600
                        archive_info.mtime = int(file_info.st_mtime)

                        archive.addfile(archive_info, fileobj=source)

        os.link(temporary_path, archive_path)
        temporary_path.unlink()

    except Exception:
        if temporary_created:
            temporary_path.unlink(missing_ok=True)
        raise

    return archive_path

def create_eligible_monthly_archive(archive_path, filenames):
    """Archive only expired, tracked backups in their correct month"""

    archive_path = Path(archive_path)
    filenames = list(filenames)

    if not filenames:
        raise ValueError("No backup files provided")

    if len(filenames) != len(set(filenames)):
        raise ValueError("Duplicate backup filenames are not allowed")

    protected_filename = get_latest_successful_backup()

    if protected_filename in filenames:
        raise ValueError(
            f"Latest successful backup is protected: {protected_filename}"
        )
    
    eligible_groups = preview_monthly_archive_groups()

    eligible_filenames = eligible_groups.get(str(archive_path))

    if eligible_filenames is None:
        raise ValueError(
            f"Archive destination is not eligible: {archive_path}"
        )

    if set(filenames) != set(eligible_filenames):
        raise ValueError(
            "Archive contents must match the eligible monthly backup group"
        )

    return create_monthly_archive(archive_path, filenames)

#---------SHA256 Integrity Functions-----------
def calculate_sha256(stream):
    """Calculate a SHA-256 hash from a binary stream."""

    digest =hashlib.sha256()

    while True:
        chunk = stream.read(1024 * 1024)

        if not chunk:
            break

        digest.update(chunk)

    return digest.hexdigest()

#--------Integrity and Security Functions-------

def verify_monthly_archive(archive_path, filenames):
    """Verify every archived backup matches its original file."""
    archive_path = Path(archive_path)
    backup_directory = Path("/backups")

    with open_monthly_archive_safely(archive_path) as archive_file:
        with tarfile.open(fileobj=archive_file, mode="r:gz") as archive:
            members = archive.getmembers()

            if len(members) != len(filenames):
                return False

            if set(archive.getnames()) != set(filenames):
                return False

            for filename in filenames:
                member = archive.getmember(filename)

                if not member.isfile():
                    return False

                original_path = backup_directory / filename

                if not original_path.is_file():
                    return False

                with original_path.open("rb") as original:
                    original_hash = calculate_sha256(original)

                with archive.extractfile(member) as archived:
                    archived_hash = calculate_sha256(archived)

                if original_hash != archived_hash:
                    return False

    return True

def verify_archive_readable(archive_path):
    """Verify every regular file in a compressed archive is readable."""

    archive_path = Path(archive_path)

    try:
        with open_monthly_archive_safely(archive_path) as archive_file:
            with tarfile.open(fileobj=archive_file, mode="r:gz") as archive:
                members = archive.getmembers()

                if not members:
                    return False

                names = [member.name for member in members]

                if len(names) != len(set(names)):
                    return False

                for member in members:
                    if not member.isfile():
                        return False

                    if Path(member.name).name != member.name:
                        return False

                    with archive.extractfile(member) as stream:
                        calculate_sha256(stream)

        return True

    except (OSError, EOFError, tarfile.TarError, ValueError):
        return False

def verify_archived_pg_dump(archive_path, filename):
    """Validate an archived PostgreSQL dump safely."""

    try:
        archive_path = Path(archive_path)

        with open_monthly_archive_safely(archive_path) as archive_file:
            with tarfile.open(fileobj=archive_file, mode="r:gz") as archive:
                try:
                    member = archive.getmember(filename)
                except KeyError:
                    return False

                if not member.isfile():
                    return False

                with archive.extractfile(member) as source:
                    process = subprocess.Popen(
                        ["pg_restore", "--list"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

                    try:
                        while True:
                            chunk = source.read(1024 * 1024)

                            if not chunk:
                                break

                            process.stdin.write(chunk)

                    except BrokenPipeError:
                        pass

                    finally:
                        process.stdin.close()

                    return process.wait() == 0

    except (OSError, EOFError, tarfile.TarError, KeyError, ValueError):
        return False

def verify_monthly_pg_archive(archive_path, filenames):
    """Validate all expected PostgreSQL dumps in a monthly archive."""

    if not filenames:
        return False

    if len(filenames) != len(set(filenames)):
        return False

    try:
        if not verify_monthly_archive(archive_path, filenames):
            return False

        if not verify_archive_readable(archive_path):
            return False

        for filename in filenames:
            if not verify_archived_pg_dump(archive_path, filename):
                return False

        return True

    except (OSError, EOFError, tarfile.TarError, KeyError):
        return False

def open_monthly_archive_by_descriptor(archive_path):
    """Open a Monthly archive without following directory symlinks."""
    archive_path = Path(archive_path)
    year, month = validate_monthly_archive_path(archive_path)

    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY

    root_fd = os.open("/", flags)

    # I know you hate nested try but this is how we can check field descriptors for Integrity safely during traversal.
     
    try:
        backups_fd = os.open("backups", flags, dir_fd=root_fd)

        try:
            archives_fd = os.open(
                "archives", flags, dir_fd=backups_fd
            )

            try:
                year_fd = os.open(
                    str(year), flags, dir_fd=archives_fd
                )

                try:
                    file_fd = os.open(
                        archive_path.name,
                        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=year_fd,
                    )

                    try:
                        file_info = os.fstat(file_fd)

                        if not stat.S_ISREG(file_info.st_mode):
                            raise ValueError(
                                "Monthly archive is not a regular file"
                            )

                        return os.fdopen(file_fd, "rb")
                    
                    except Exception:
                        os.close(file_fd)
                        raise

                finally:
                    os.close(year_fd)

            finally:
                os.close(archives_fd)

        finally:
            os.close(backups_fd)

    finally:
        os.close(root_fd)


    
 #--------Backup Flagging Functions-----------
def preview_expired_archives():
    """List monthly archives older than the configured retention period."""

    archive_root = Path("/backup/archives")
    now = datetime.now(timezone.utc)

    expired_archives =[]

    for archive_path in archive_root.glob("*/*.tar.gz"):
        year_directory = archive_path.parent.name
        archive_filename = archive_path.name

        if(
            not year_directory.isdigit()
            or len(year_directory) != 4
            or not archive_filename.startswith(year_directory + "-")
            or len(archive_filename) !=14
        ):
            continue
        month_text = archive_filename[5:7]

        if(
            not month_text.isdigit()
            or not 1 <= int(month_text) <= 12
        ):
            continue

        if not archive_path.is_file() or archive_path.is_symlink():
            continue

        modified_time = datetime.fromtimestamp(
            archive_path.stat().st_mtime,
            tz=timezone.utc
        )

        expiration_year = (
            modified_time.year + BACKUP_ARCHIVE_RETENTION_YEARS
        )

        try:
            expiration_date = modified_time.replace(
                year=expiration_year
            )
        except ValueError:
            #February 29 has no equivalent in a non-leap year.
            #Retain through February 28 and expire on March 1.
            expiration_date = modified_time.replace(
                year=expiration_year,
                month=3,
                day=1
            )

        if now >= expiration_date:
            expired_archives.append(str(archive_path))

    return sorted(expired_archives)

def preview_expired_backups():
    """Identify backup files older than the retention period."""

    backup_directory = Path("/backups")
    protected_filename = get_latest_successful_backup()

    cutoff_time = datetime.now(timezone.utc) - timedelta(
        days=BACKUP_RETENTION_DAYS
    )

    expired_files = []

    for backup_file in backup_directory.glob("otintel_*.dump"):

        if not backup_file.is_file():
            continue
        
        #exclude last successful backup
        if backup_file.name == protected_filename:
            continue

        modified_time = datetime.fromtimestamp(
            backup_file.stat().st_mtime,
            tz=timezone.utc
        )

        if modified_time < cutoff_time:
            expired_files.append(backup_file.name)

    return sorted(expired_files)

#-----------------BACKUP SCHEDULING FUNCTIONS-------------
def schedule_backup_if_due():
    """Queue a scheduled backup when the configured interval has elapsed."""

    with psycopg.connect() as connection:
        with connection.cursor() as cursor:

            # Prevent concurrent schedulers from creating duplicate jobs.
            cursor.execute(
                "SELECT pg_advisory_xact_lock(720104)"
            )

            cursor.execute(
                """
                INSERT INTO public.backup_jobs (trigger_type, status)
                SELECT 'scheduled', 'pending'
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM public.backup_jobs
                    WHERE trigger_type = 'scheduled'
                      AND requested_at >
                          NOW() - (%s * INTERVAL '1 second')
                )
                RETURNING id
                """,
                (BACKUP_INTERVAL_SECONDS,)
            )

            result = cursor.fetchone()

        connection.commit()

    if result is not None:
        print(
            f"Scheduled backup job {result[0]} created.",
            flush=True
        )
        if result is not None:
            print(
                f"Scheduled backup job {result[0]} created.",
                flush=True
            ) 

def claim_pending_job():
    """Find and safely claim one pending backup request."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                WITH next_job AS (
                    SELECT id
                    FROM public.backup_jobs
                    WHERE status = 'pending'
                    ORDER BY requested_at, id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE public.backup_jobs AS job
                SET status = 'running',
                    started_at = now()
                FROM next_job
                WHERE job.id = next_job.id
                RETURNING job.id
            """)

            row = cur.fetchone()
            return row[0] if row else None


def process_job(job_id):
    """Execute the backup and record success or failure."""

    # Record existing backup filenames.
    before = {p.name for p in BACKUP_DIR.glob("*.dump")}

    try:
        # Execute the PostgreSQL backup script.
        result = subprocess.run(
            ["sh", BACKUP_SCRIPT],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )

        print(result.stdout, flush=True)

        # Identify the newly created backup.
        after = {p.name for p in BACKUP_DIR.glob("*.dump")}
        new_files = after - before

        if len(new_files) != 1:
            raise RuntimeError(
                "Expected exactly one new backup archive."
            )

        filename = new_files.pop()
        file_size = (BACKUP_DIR / filename).stat().st_size

        # Record successful completion.
        with get_connection() as conn:
            conn.execute("""
                UPDATE public.backup_jobs
                SET status = 'completed',
                    completed_at = now(),
                    filename = %s,
                    file_size_bytes = %s
                WHERE id = %s
            """, (filename, file_size, job_id))

        print(
            f"Job {job_id} completed: {filename}",
            flush=True
        )

    except Exception as exc:

        # DEBUGGING: Show errors returned by backup.sh.
        if isinstance(exc, subprocess.CalledProcessError):
            print(
                "Backup script stdout:",
                exc.stdout,
                flush=True
            )
            print(
                "Backup script stderr:",
                exc.stderr,
                flush=True
            )

        # Record the failure in PostgreSQL.
        with get_connection() as conn:
            conn.execute("""
                UPDATE public.backup_jobs
                SET status = 'failed',
                    completed_at = now(),
                    error_message = %s
                WHERE id = %s
            """, (str(exc)[:2000], job_id))

        print(
            f"Job {job_id} failed: {exc}",
            flush=True
        )


if __name__ == "__main__":
    print("Backup worker started.", flush=True)

    while True:
        try:
            schedule_backup_if_due()

            job_id = claim_pending_job()

            if job_id is not None:
                print(
                    f"Processing backup job {job_id}...",
                    flush=True
                )
                process_job(job_id)

        except Exception as exc:
            print(
                f"Worker error: {exc}",
                flush=True
            )

        time.sleep(10)