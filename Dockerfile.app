# FROM ubuntu:22.04
# # Installing dependencies for running a python application
# RUN apt-get update && apt-get install -y python3 python3-pip postgresql-client libpq-dev wget
# # Install pipenv
# RUN pip3 install poetry
# # Setting the working directory
# WORKDIR /app
# # Install pipenv dependencies
# COPY pyproject.toml ./
# RUN poetry install --no-root
# # Copying our application into the container
# COPY spam spam
# COPY credentials /
# RUN dpkg --print-architecture | grep -q "amd64" && export SPAMHAMMER_ARCH="amd64" || export SPAMHAMMER_ARCH="arm64" && wget https://github.com/CSSE6400/SpamHammer/releases/download/v1.0.0/spamhammer-v1.0.0-linux-${SPAMHAMMER_ARCH} -O spam/spamhammer && chmod +x spam/spamhammer
# # Running our application
# CMD ["bash", "-c", "sleep 10 && poetry run flask --app spam run --host 0.0.0.0 --port 8080"]



FROM ubuntu:22.04
# Installing dependencies and cleaning up
RUN apt-get update && \
        apt-get install -y python3 python3-pip postgresql-client libpq-dev libcurl4-openssl-dev libssl-dev wget && \
        apt-get clean && \
        rm -rf /var/lib/apt/lists/*
# Install pipenv
RUN pip3 install poetry
# Setting the working directory
WORKDIR /app
# Install pipenv dependencies
COPY pyproject.toml ./
RUN poetry install --no-root
# Copying our application into the container
COPY spam spam
COPY bin bin
COPY credentials /
RUN dpkg --print-architecture | grep -q "amd64" && export SPAMHAMMER_ARCH="amd64" || export SPAMHAMMER_ARCH="arm64" && wget https://github.com/86LAK/SpamHammer/releases/download/v1.0.0/spamhammer-v1.0.0-linux-${SPAMHAMMER_ARCH} -O spam/spamhammer && chmod +x spam/spamhammer && chmod +x bin/docker-entrypoint
# Running our application
ENTRYPOINT ["/app/bin/docker-entrypoint"]
CMD ["serve"]