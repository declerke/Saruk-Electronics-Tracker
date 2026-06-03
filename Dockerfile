FROM apache/airflow:3.0.0

USER root
RUN apt-get update \
    && apt-get install -y curl \
        libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 \
        libatk-bridge2.0-0 libcups2 libdrm2 libatspi2.0-0 \
        libx11-6 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
        libxrandr2 libgbm1 libxcb1 libxkbcommon0 libpango-1.0-0 \
        libcairo2 libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages into the Airflow venv as USER airflow
USER airflow
# Pin dbt-core to 1.8.x to avoid conflict with dbt Fusion (2.0.0a1) bundled in Airflow 3.0
RUN pip install \
    playwright==1.44.0 \
    psycopg2-binary==2.9.9 \
    "dbt-core==1.8.2" \
    "dbt-postgres==1.8.2" \
    pandas==2.2.2 \
    pytest==8.2.2

RUN playwright install chromium
