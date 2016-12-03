FROM ubuntu:16.04

MAINTAINER "dev@tubularlabs.com"

# Install OpenJDK 8
RUN apt-get update && apt-get install -y default-jre

# Install Spark 1.6.2
RUN apt-get install -y curl
RUN curl -s http://d3kbcqa49mib13.cloudfront.net/spark-1.6.2-bin-hadoop2.6.tgz | tar -xz -C /usr/local/
RUN cd /usr/local && ln -s spark-1.6.2-bin-hadoop2.6 spark

ENV SPARK_HOME "/usr/local/spark/"
ENV PYTHONPATH "/usr/local/spark/python/lib/pyspark.zip:/usr/local/spark/python/lib/py4j-0.9-src.zip"
ENV SPARK_TESTING true

# Install Python testing utils
RUN apt-get install -y python python3-pip
RUN python3 -m pip install tox==2.4.1

# Remove noisy spark logging
COPY spark.log4j.properties /usr/local/spark/conf/log4j.properties

# Make integration tests faster
RUN /usr/local/spark/bin/spark-shell --packages=\
com.databricks:spark-csv_2.10:1.4.0,\
datastax:spark-cassandra-connector:1.6.1-s_2.10,\
org.elasticsearch:elasticsearch-spark_2.10:2.3.0

# Python env
RUN apt-get install -y git
ENV CASS_DRIVER_NO_EXTENSIONS=1
COPY requirements.txt /tmp/requirements.txt
COPY requirements_dev.txt /tmp/requirements_dev.txt
RUN python3 -m pip install -r /tmp/requirements.txt
RUN python3 -m pip install -r /tmp/requirements_dev.txt

# Provision Sparkly
ADD . /opt/sparkly/
WORKDIR /opt/sparkly/