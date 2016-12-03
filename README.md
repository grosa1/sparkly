# Sparkly

[![Sparkly PyPi Version](http://img.shields.io/pypi/v/sparkly.svg)](https://pypi.python.org/pypi/sparkly)
[![Sparkly Build Status](https://travis-ci.org/Tubular/sparkly.svg?branch=master)](https://travis-ci.org/Tubular/sparkly)
[![Documentation Status](https://readthedocs.org/projects/sparkly/badge/?version=latest)](http://sparkly.readthedocs.io/en/latest/?badge=latest)

Helpers & syntax sugar for PySpark. There are several features to make your life easier:
- Definition of spark packages, external jars, UDFs and spark options within your code;
- Simplified reader/writer api for Cassandra, Elastic, MySQL;
- Testing framework for spark applications.

More details could be found in [the official documentation](https://sparkly.readthedocs.org).

## Installation

Sparkly itself is easy to install:
```
pip install sparkly
```

The tricky part is `pyspark`. There is no official distribution on PyPI. As a workaround we can suggest:

1) Use env variable `PYTHONPATH` to point to your Spark installation, something like:
```
export PYTHONPATH="/usr/local/spark/python/lib/pyspark.zip:/usr/local/spark/python/lib/py4j-0.9-src.zip"
```
2) Use our `setup.py` file for `pyspark`. Just add this to your `requirements.txt`:
```
-e git+https://github.com/Tubular/spark@branch-1.6#egg=pyspark&subdirectory=python
```

Here in Tubular, we published `pyspark` to our internal PyPi repository.

## Getting Started

Here is a small code snippet to show how to easily read Cassandra table
and write its content to ElasticSearch index:
```
from sparkly import SparklyContext


class MyContext(SparklyContext):
    packages = [
        'datastax:spark-cassandra-connector:1.6.1-s_2.10',
        'org.elasticsearch:elasticsearch-spark_2.10:2.3.0',
    ]
    

if __name__ == '__main__':
    hc = MyContext()
    df = hc.read_ext.cassandra('localhost', 'my_keyspace', 'my_table')
    df.write_ext.elastic('localhost', 'my_index', 'my_type')
```

See [the online documentation](https://sparkly.readthedocs.org) for more details. 

## Testing

To run tests  you have to have [docker](https://www.docker.com/) 
and [docker-compose](https://docs.docker.com/compose/) installed on your system.
If you are working on MacOS we highly recommend you to use [docker-machine](https://docs.docker.com/machine/).
As soon as the tools mentioned above have been installed, all you need is to run:
```
make test
```

## Supported Spark Versions
At the moment we support only Spark 1.6.x.
In the nearest future, we are going to add support for Spark 2.x.