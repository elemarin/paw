FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Add deadsnakes PPA for Python 3.12 and install system tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    gpg \
    gpg-agent \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    git \
    curl \
    wget \
    build-essential \
    sudo \
    jq \
    tree \
    vim-tiny \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Make python3.12 the default and bootstrap pip
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1 && \
    curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

# Create paw user with sudo
RUN useradd -m -s /bin/bash paw && \
    echo "paw ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/paw

# Set up PAW directories
RUN mkdir -p /home/paw/data /home/paw/plugins /home/paw/workspace && \
    chown -R paw:paw /home/paw

# Install PAW
WORKDIR /app
COPY pyproject.toml .
COPY README.md .
COPY src/ src/
COPY soul.md /app/soul.md
COPY plugins/ /app/default-plugins/

RUN pip install --no-cache-dir -e ".[dev]"

# Copy entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Switch to paw user
USER paw
WORKDIR /home/paw

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
