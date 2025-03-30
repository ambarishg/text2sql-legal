# Use a base image with Python
FROM python:3.11-slim AS builder

# Set environment variables for ODBC
ENV ODBC_VERSION=2.3.7
ENV ACCEPT_EULA=Y

# Install necessary packages and dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    unixodbc \
    unixodbc-dev \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch (check compatibility)
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 8000
# Command to run the application
CMD ["python", "app.py"]
