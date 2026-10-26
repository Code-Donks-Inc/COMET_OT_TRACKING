
FROM postgres:17

# Install Python and the tools needed to create a virtual environment.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /worker

# Create an isolated Python environment.
RUN python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

# Install the PostgreSQL Python driver.
RUN pip install --no-cache-dir "psycopg[binary]>=3.2,<4"

# Copy the PostgreSQL backup script.
COPY backup.sh /worker/backup.sh

# Copy the Python queue processor.
COPY worker.py /worker/worker.py

# Process one pending backup job.
CMD ["python3", "/worker/worker.py"]