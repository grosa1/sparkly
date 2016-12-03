from shutil import rmtree
from tempfile import mkdtemp

from sparkly.utils import absolute_path
from sparkly.testing import (
    SparklyGlobalContextTest,
    CassandraFixture,
    ElasticFixture,
    MysqlFixture,
)
from tests.integration.base import _TestContext


TEST_DATA = [
    {'uid': 'v1', 'title': 'Video A', 'views': 1000},
    {'uid': 'v2', 'title': 'Video B', 'views': 2000},
    {'uid': 'v3', 'title': 'Video C', 'views': 3000},
]


class TestWriteByURL(SparklyGlobalContextTest):
    context = _TestContext

    def setUp(self):
        self.temp_dir = mkdtemp()

    def tearDown(self):
        rmtree(self.temp_dir)

    def test_write_csv(self):
        dst_path = '{}/test_csv'.format(self.temp_dir)
        df = self.hc.createDataFrame(TEST_DATA)

        df.write_ext.by_url('csv://{}?mode=overwrite&header=true'.format(dst_path))

        written_df = self.hc.read_ext.by_url('csv://{}'.format(dst_path))
        self.assertDataFrameEqual(written_df, TEST_DATA)

    def test_write_parquet(self):
        dst_path = '{}/test_parquet'.format(self.temp_dir)
        df = self.hc.createDataFrame(TEST_DATA)

        df.write_ext.by_url('parquet://{}?mode=overwrite'.format(dst_path))

        written_df = self.hc.read_ext.by_url('parquet://{}'.format(dst_path))
        self.assertDataFrameEqual(written_df, TEST_DATA)


class TestWriteCassandra(SparklyGlobalContextTest):
    context = _TestContext

    fixtures = [
        CassandraFixture(
            'cassandra.docker',
            absolute_path(__file__, 'resources', 'test_write', 'cassandra_setup.cql'),
            absolute_path(__file__, 'resources', 'test_write', 'cassandra_teardown.cql'),
        )
    ]

    def test_write_cassandra(self):
        df = self.hc.createDataFrame(TEST_DATA)

        df.write_ext.cassandra(
            host='cassandra.docker',
            port=9042,
            keyspace='sparkly_test',
            table='test_writer',
            consistency='ONE',
            mode='overwrite',
        )

        written_df = self.hc.read_ext.by_url(
            'cassandra://cassandra.docker/'
            'sparkly_test/test_writer'
            '?consistency=ONE'
        )
        self.assertDataFrameEqual(written_df, TEST_DATA)


class TestWriteElastic(SparklyGlobalContextTest):
    context = _TestContext

    fixtures = [
        ElasticFixture(
            'elastic.docker',
            'sparkly_test',
            'test',
            None,
            absolute_path(__file__, 'resources', 'test_write', 'elastic_setup.json')
        )
    ]

    def test_write_elastic(self):
        df = self.hc.createDataFrame(TEST_DATA)

        df.write_ext.elastic(
            host='elastic.docker',
            port=9200,
            es_index='sparkly_test',
            es_type='test_writer',
            mode='overwrite',
            options={
                'es.mapping.id': 'uid',
            }
        )

        df = self.hc.read_ext.by_url(
            'elastic://elastic.docker/sparkly_test/test_writer?es.read.metadata=false'
        )
        self.assertDataFrameEqual(df, TEST_DATA)


class TestWriteMysql(SparklyGlobalContextTest):
    context = _TestContext

    fixtures = [
        MysqlFixture(
            'mysql.docker',
            'root',
            None,
            absolute_path(__file__, 'resources', 'test_write', 'mysql_setup.sql'),
            absolute_path(__file__, 'resources', 'test_write', 'mysql_teardown.sql'),
        )
    ]

    def test_write_mysql(self):
        df = self.hc.createDataFrame(TEST_DATA)

        df.write_ext.mysql(
            host='mysql.docker',
            port=3306,
            database='sparkly_test',
            table='test_writer',
            mode='overwrite',
            options={'user': 'root', 'password': ''}
        )

        df = self.hc.read_ext.by_url(
            'mysql://mysql.docker/'
            'sparkly_test/test_writer'
            '?user=root&password='
        )
        self.assertDataFrameEqual(df, TEST_DATA)