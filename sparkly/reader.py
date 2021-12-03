#
# Copyright 2017 Tubular Labs, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import json

from pyspark.sql import functions as F

from sparkly.exceptions import InvalidArgumentError
from sparkly.utils import kafka_get_topics_offsets

try:
    from urllib.parse import urlparse, parse_qsl
except ImportError:
    from urlparse import urlparse, parse_qsl

from sparkly.utils import parse_schema


class SparklyReader(object):
    """A set of tools to create DataFrames from the external storages.

    Note:
        This is a private class to the library. You should not use it directly.
        The instance of the class is available under `SparklyContext` via `read_ext` attribute.
    """
    def __init__(self, spark):
        """Constructor.

        Args:
            spark (sparkly.SparklySession)
        """
        self._spark = spark

    def by_url(self, url):
        """Create a dataframe using `url`.

        The main idea behind the method is to unify data access interface for different
        formats and locations. A generic schema looks like::

            format:[protocol:]//host[:port][/location][?configuration]

        Supported formats:

            - CSV ``csv://``
            - Cassandra ``cassandra://``
            - Elastic ``elastic://``
            - MySQL ``mysql://``
            - Parquet ``parquet://``
            - Hive Metastore table ``table://``

        Query string arguments are passed as parameters to the relevant reader.\n
        For instance, the next data source URL::

            cassandra://localhost:9042/my_keyspace/my_table?consistency=ONE
                &parallelism=3&spark.cassandra.connection.compression=LZ4

        Is an equivalent for::

            hc.read_ext.cassandra(
                host='localhost',
                port=9042,
                keyspace='my_keyspace',
                table='my_table',
                consistency='ONE',
                parallelism=3,
                options={'spark.cassandra.connection.compression': 'LZ4'},
            )

        More examples::

            table://table_name
            csv:s3://some-bucket/some_directory?header=true
            csv://path/on/local/file/system?header=false
            parquet:s3://some-bucket/some_directory
            elastic://elasticsearch.host/es_index/es_type?parallelism=8
            cassandra://cassandra.host/keyspace/table?consistency=QUORUM
            mysql://mysql.host/database/table

        Args:
            url (str): Data source URL.

        Returns:
            pyspark.sql.DataFrame
        """
        parsed_url = urlparse(url)
        parsed_qs = dict(parse_qsl(parsed_url.query))

        # Used across all readers
        if 'parallelism' in parsed_qs:
            parsed_qs['parallelism'] = int(parsed_qs['parallelism'])

        try:
            resolver = getattr(self, '_resolve_{}'.format(parsed_url.scheme))
        except AttributeError:
            raise NotImplementedError('Data source is not supported: {}'.format(url))
        else:
            return resolver(parsed_url, parsed_qs)

    def cassandra(self, host, keyspace, table, consistency=None, port=None,
                  parallelism=None, options=None):
        """Create a dataframe from a Cassandra table.

        Args:
            host (str): Cassandra server host.
            keyspace (str) Cassandra keyspace to read from.
            table (str): Cassandra table to read from.
            consistency (str): Read consistency level: ``ONE``, ``QUORUM``, ``ALL``, etc.
            port (int|None): Cassandra server port.
            parallelism (int|None): The max number of parallel tasks that could be executed
                during the read stage (see :ref:`controlling-the-load`).
            options (dict[str,str]|None): Additional options for `org.apache.spark.sql.cassandra`
                format (see configuration for :ref:`cassandra`).

        Returns:
            pyspark.sql.DataFrame
        """
        reader_options = {
            'format': 'org.apache.spark.sql.cassandra',
            'spark.cassandra.connection.host': host,
            'keyspace': keyspace,
            'table': table,
        }

        if consistency:
            reader_options['spark.cassandra.input.consistency.level'] = consistency

        if port:
            reader_options['spark.cassandra.connection.port'] = str(port)

        return self._basic_read(reader_options, options, parallelism)

    def elastic(self, host, es_index, es_type, query='', fields=None, port=None,
                parallelism=None, options=None):
        """Create a dataframe from an ElasticSearch index.

        Args:
            host (str): Elastic server host.
            es_index (str): Elastic index.
            es_type (str|None): Elastic type. Deprecated in Elasticsearch 7 but required in below 7
            query (str): Pre-filter es documents, e.g. '?q=views:>10'.
            fields (list[str]|None): Select only specified fields.
            port (int|None) Elastic server port.
            parallelism (int|None): The max number of parallel tasks that could be executed
                during the read stage (see :ref:`controlling-the-load`).
            options (dict[str,str]): Additional options for `org.elasticsearch.spark.sql` format
                (see configuration for :ref:`elastic`).

        Returns:
            pyspark.sql.DataFrame
        """
        reader_options = {
            'path': '{}/{}'.format(es_index, es_type) if es_type else es_index,
            'format': 'org.elasticsearch.spark.sql',
            'es.nodes': host,
            'es.query': query,
            'es.read.metadata': 'true',
        }

        if fields:
            reader_options['es.read.field.include'] = ','.join(fields)

        if port:
            reader_options['es.port'] = str(port)

        return self._basic_read(reader_options, options, parallelism)

    def mysql(self, host, database, table, port=None, parallelism=None, options=None):
        """Create a dataframe from a MySQL table.

        Options should include user and password.

        Args:
            host (str): MySQL server address.
            database (str): Database to connect to.
            table (str): Table to read rows from.
            port (int|None): MySQL server port.
            parallelism (int|None): The max number of parallel tasks that could be executed
                during the read stage (see :ref:`controlling-the-load`).
            options (dict[str,str]|None): Additional options for JDBC reader
                (see configuration for :ref:`mysql`).

        Returns:
            pyspark.sql.DataFrame
        """
        reader_options = {
            'format': 'jdbc',
            'driver': 'com.mysql.jdbc.Driver',
            'url': 'jdbc:mysql://{host}{port}/{database}'.format(
                host=host,
                port=':{}'.format(port) if port else '',
                database=database,
            ),
            'dbtable': table,
        }

        return self._basic_read(reader_options, options, parallelism)

    def kafka(self,
              host,
              topic,
              offset_ranges=None,
              key_deserializer=None,
              value_deserializer=None,
              schema=None,
              port=9092,
              parallelism=None,
              options=None,
              include_meta_cols=None):
        """Creates dataframe from specified set of messages from Kafka topic.

        Defining ranges:
            - If `offset_ranges` is specified it defines which specific range to read.
            - If `offset_ranges` is omitted it will auto-discover it's partitions.

        The `schema` parameter, if specified, should contain two top level fields:
        `key` and `value`. It is only required if deserializers are used.

        Parameters `key_deserializer` and `value_deserializer` are callables
        which get bytes as input and should return python structures as output.

        Args:
            host (str): Kafka host.
            topic (str|List[str]|None): Kafka topic(s) to read from.
            offset_ranges (list[(int, int, int)]|None): List of partition ranges
                [(partition, start_offset, end_offset)].
            key_deserializer (function): Function used to deserialize the key.
            value_deserializer (function): Function used to deserialize the value.
            schema (pyspark.sql.types.StructType): Schema to apply to create a Dataframe.
            port (int): Kafka port.
            options (dict|None): Additional kafka parameters, see KafkaUtils.createRDD docs.
            include_meta_cols (bool|None): If true, also return "metadata" columns
                like offset, topic, etc.

        Returns:
            pyspark.sql.DataFrame

        Raises:
            InvalidArgumentError
        """
        if isinstance(topic, str):
            topic = [topic]

        reader = (
            self._spark.read.format('kafka')
            .option('kafka.bootstrap.servers', f'{host}:{port}')
            .option('subscribe', ','.join(topic))
        )

        def get_offsets(offsets, which):
            return {
                offset[0]: offset[which]
                for offset in offsets
            }

        if offset_ranges:
            if len(topic) > 1:
                raise InvalidArgumentError(
                    'Specifying offset_ranges for multiple topics is not currently supported; '
                    'please specify options "startingOffsets" and "endingOffsets" manually'
                )
            starting_offsets = json.dumps({t: get_offsets(offset_ranges, 1) for t in topic})
            ending_offsets = json.dumps({t: get_offsets(offset_ranges, 2) for t in topic})
            reader = (
                reader
                .option('startingOffsets',  starting_offsets)
                .option('endingOffsets', ending_offsets)
            )

        for key, value in (options or {}).items():
            reader = reader.option(key, value)

        df = reader.load()

        def get_schema(field):
            if schema is None:
                raise InvalidArgumentError(
                    'Cannot use a deserializer without specifying schema'
                )
            candidates = [x for x in schema.fields if x.name == field]
            if not candidates:
                raise InvalidArgumentError(
                    f'Cannot find field: {field} in schema: {schema.simpleString()}'
                )
            result = candidates[0].dataType
            return result

        if key_deserializer is not None:
            df = df.withColumn(
                'key',
                F.udf(
                    key_deserializer,
                    returnType=get_schema('key'),
                )(F.col('key')),
            )
        if value_deserializer is not None:
            df = df.withColumn(
                'value',
                F.udf(
                    value_deserializer,
                    returnType=get_schema('value'),
                )(F.col('value')),
            )

        if not include_meta_cols:
            df = df.select('key', 'value')

        if parallelism:
            df = df.coalesce(parallelism)

        return df

    def _basic_read(self, reader_options, additional_options, parallelism):
        reader_options.update(additional_options or {})

        df = self._spark.read.load(**reader_options)
        if parallelism:
            df = df.coalesce(parallelism)

        return df

    def _resolve_cassandra(self, parsed_url, parsed_qs):
        return self.cassandra(
            host=parsed_url.hostname,
            keyspace=parsed_url.path.split('/')[1],
            table=parsed_url.path.split('/')[2],
            consistency=parsed_qs.pop('consistency', None),
            port=parsed_url.port,
            parallelism=parsed_qs.pop('parallelism', None),
            options=parsed_qs,
        )

    def _resolve_csv(self, parsed_url, parsed_qs):
        parallelism = parsed_qs.pop('parallelism', None)

        if 'schema' in parsed_qs:
            parsed_qs['schema'] = parse_schema(parsed_qs.pop('schema'))

        df = self._spark.read.csv(
            path=parsed_url.path,
            **parsed_qs
        )

        if parallelism:
            df = df.coalesce(int(parallelism))

        return df

    def _resolve_elastic(self, parsed_url, parsed_qs):
        kwargs = {}

        if 'q' in parsed_qs:
            kwargs['query'] = '?q={}'.format(parsed_qs.pop('q'))

        if 'fields' in parsed_qs:
            kwargs['fields'] = parsed_qs.pop('fields').split(',')

        path_segments = parsed_url.path.split('/')

        return self.elastic(
            host=parsed_url.netloc,
            es_index=path_segments[1],
            es_type=path_segments[2] if len(path_segments) > 2 else None,
            port=parsed_url.port,
            parallelism=parsed_qs.pop('parallelism', None),
            options=parsed_qs,
            **kwargs
        )

    def _resolve_mysql(self, parsed_url, parsed_qs):
        return self.mysql(
            host=parsed_url.hostname,
            database=parsed_url.path.split('/')[1],
            table=parsed_url.path.split('/')[2],
            port=parsed_url.port,
            parallelism=parsed_qs.pop('parallelism', None),
            options=parsed_qs,
        )

    def _resolve_parquet(self, parsed_url, parsed_qs):
        parallelism = parsed_qs.pop('parallelism', None)

        df = self._spark.read.load(
            path=parsed_url.path,
            format=parsed_url.scheme,
            **parsed_qs
        )

        if parallelism:
            df = df.coalesce(int(parallelism))

        return df

    def _resolve_table(self, parsed_url, parsed_qs):
        df = self._spark.table(parsed_url.netloc)

        parallelism = parsed_qs.pop('parallelism', None)
        if parallelism:
            df = df.coalesce(int(parallelism))

        return df
