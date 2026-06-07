"""Use PyMySQL as the MySQLdb driver for Django's mysql backend.

PyMySQL is pure-Python (no system libs to build), so it installs everywhere.
The version_info override satisfies Django's mysqlclient >= 1.4.3 check.
"""

import pymysql

pymysql.version_info = (1, 4, 6, "final", 0)
pymysql.install_as_MySQLdb()
