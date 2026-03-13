FROM artifactory.aexp.com/dockerproxy/apache/age:latest

USER root

# Install pgvector for PostgreSQL 18
RUN apt-get update && \
    apt-get install -y postgresql-18-pgvector && \
    apt-get clean

USER postgres
