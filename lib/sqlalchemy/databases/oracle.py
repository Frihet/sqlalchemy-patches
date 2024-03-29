# oracle.py
# Copyright (C) 2005, 2006, 2007, 2008 Michael Bayer mike_mp@zzzcomputing.com
#
# This module is part of SQLAlchemy and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php


import datetime, random, re, operator

from sqlalchemy import util, sql, schema, exceptions, logging
from sqlalchemy.engine import default, base
from sqlalchemy.sql import compiler, visitors, expression
from sqlalchemy.sql import operators as sql_operators, functions as sql_functions
from sqlalchemy import types as sqltypes

# Oracle has plenty of reserved words and they are not quotable.
RESERVED_WORDS = util.Set([
        'access', 'add', 'all', 'alter', 'and', 'any', 'arraylen',
        'as', 'asc', 'audit', 'between', 'by', 'char', 'check', 'cluster',
        'column', 'comment', 'compress', 'connect', 'create', 'current',
        'date', 'decimal', 'default', 'delete', 'desc', 'distinct', 'drop',
        'else', 'exclusive', 'exists', 'file', 'float', 'for', 'from',
        'grant', 'group', 'having', 'identified', 'immediate', 'in',
        'increment', 'index', 'initial', 'insert', 'integer', 'intersect',
        'into', 'is', 'level', 'like', 'lock', 'long', 'maxextents', 'minus',
        'mode', 'modify', 'noaudit', 'nocompress', 'not', 'notfound', 'nowait',
        'null', 'number', 'of', 'offline', 'on', 'online', 'option', 'or',
        'order', 'pctfree', 'prior', 'privileges', 'public', 'raw', 'rename',
        'resource', 'revoke', 'row', 'rowid', 'rowlabel', 'rownum', 'rows',
        'select', 'session', 'set', 'share', 'size', 'smallint', 'sqlbuf',
        'start', 'successful', 'synonym', 'sysdate', 'table', 'then', 'to',
        'trigger', 'uid', 'union', 'unique', 'update', 'user', 'validate',
        'values', 'varchar', 'varchar2', 'view', 'whenever', 'where', 'with'])


class OracleNumeric(sqltypes.Numeric):
    def get_col_spec(self):
        if self.precision is None:
            return "NUMERIC"
        else:
            return "NUMERIC(%(precision)s, %(length)s)" % {'precision': self.precision, 'length' : self.length}

class OracleInteger(sqltypes.Integer):
    def get_col_spec(self):
        return "INTEGER"

class OracleSmallInteger(sqltypes.Smallinteger):
    def get_col_spec(self):
        return "SMALLINT"

class OracleDate(sqltypes.Date):
    def get_col_spec(self):
        return "DATE"
    def bind_processor(self, dialect):
        return None

    def result_processor(self, dialect):
        def process(value):
            if not isinstance(value, datetime.datetime):
                return value
            else:
                return value.date()
        return process

class OracleDateTime(sqltypes.DateTime):
    def get_col_spec(self):
        return "DATE"

    def result_processor(self, dialect):
        def process(value):
            if value is None or isinstance(value,datetime.datetime):
                return value
            else:
                # convert cx_oracle datetime object returned pre-python 2.4
                return datetime.datetime(value.year,value.month,
                    value.day,value.hour, value.minute, value.second)
        return process

# Note:
# Oracle DATE == DATETIME
# Oracle does not allow milliseconds in DATE
# Oracle does not support TIME columns

# only if cx_oracle contains TIMESTAMP
class OracleTimestamp(sqltypes.TIMESTAMP):
    def get_col_spec(self):
        return "TIMESTAMP"

    def get_dbapi_type(self, dialect):
        return dialect.TIMESTAMP

    def result_processor(self, dialect):
        def process(value):
            if value is None or isinstance(value,datetime.datetime):
                return value
            else:
                # convert cx_oracle datetime object returned pre-python 2.4
                return datetime.datetime(value.year,value.month,
                    value.day,value.hour, value.minute, value.second)
        return process

class OracleString(sqltypes.String):
    def get_col_spec(self):
        return "VARCHAR(%(length)s)" % {'length' : self.length}

class OracleText(sqltypes.Text):
    def get_dbapi_type(self, dbapi):
        return dbapi.CLOB

    def get_col_spec(self):
        return "CLOB"

    def result_processor(self, dialect):
        super_process = super(OracleText, self).result_processor(dialect)
        lob = dialect.dbapi.LOB
        def process(value):
            if isinstance(value, lob):
                if super_process:
                    return super_process(value.read())
                else:
                    return value.read()
            else:
                if super_process:
                    return super_process(value)
                else:
                    return value
        return process


class OracleChar(sqltypes.CHAR):
    def get_col_spec(self):
        return "CHAR(%(length)s)" % {'length' : self.length}

class OracleBinary(sqltypes.Binary):
    def get_dbapi_type(self, dbapi):
        return dbapi.BLOB

    def get_col_spec(self):
        return "BLOB"

    def bind_processor(self, dialect):
        return None

    def result_processor(self, dialect):
        lob = dialect.dbapi.LOB
        def process(value):
            if isinstance(value, lob):
                return value.read()
            else:
                return value
        return process

class OracleRaw(OracleBinary):
    def get_col_spec(self):
        return "RAW(%(length)s)" % {'length' : self.length}

class OracleBoolean(sqltypes.Boolean):
    def get_col_spec(self):
        return "SMALLINT"

    def result_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return value and True or False
        return process

    def bind_processor(self, dialect):
        def process(value):
            if value is True:
                return 1
            elif value is False:
                return 0
            elif value is None:
                return None
            else:
                return value and True or False
        return process

colspecs = {
    sqltypes.Integer : OracleInteger,
    sqltypes.Smallinteger : OracleSmallInteger,
    sqltypes.Numeric : OracleNumeric,
    sqltypes.Float : OracleNumeric,
    sqltypes.DateTime : OracleDateTime,
    sqltypes.Date : OracleDate,
    sqltypes.String : OracleString,
    sqltypes.Binary : OracleBinary,
    sqltypes.Boolean : OracleBoolean,
    sqltypes.Text : OracleText,
    sqltypes.TIMESTAMP : OracleTimestamp,
    sqltypes.CHAR: OracleChar,
}

ischema_names = {
    'VARCHAR2' : OracleString,
    'DATE' : OracleDateTime,
    'DATETIME' : OracleDateTime,
    'NUMBER' : OracleNumeric,
    'BLOB' : OracleBinary,
    'CLOB' : OracleText,
    'TIMESTAMP' : OracleTimestamp,
    'RAW' : OracleRaw,
    'FLOAT' : OracleNumeric,
    'DOUBLE PRECISION' : OracleNumeric,
    'LONG' : OracleText,
}

def descriptor():
    return {'name':'oracle',
    'description':'Oracle',
    'arguments':[
        ('dsn', 'Data Source Name', None),
        ('user', 'Username', None),
        ('password', 'Password', None)
    ]}

# Functions for compatibility

class OracleFunction(sql_functions.GenericFunction):
    def __init__(self, *args, **kwargs):
        sql_functions.GenericFunction.__init__(self, *args, **kwargs)
        self.packagenames.append('sqlalchemy')

class is_equal(OracleFunction):
    __return_type__ = sqltypes.Integer
    def __init__(self, *args, **kwargs):
        OracleFunction.__init__(self, args=args, **kwargs)

class is_not_equal(OracleFunction):
    __return_type__ = sqltypes.Integer
    def __init__(self, *args, **kwargs):
        OracleFunction.__init__(self, args=args, **kwargs)

class OracleExecutionContext(default.DefaultExecutionContext):
    def pre_exec(self):
        super(OracleExecutionContext, self).pre_exec()
        if self.dialect.auto_setinputsizes:
            self.set_input_sizes()
        if self.compiled_parameters is not None and len(self.compiled_parameters) == 1:
            for key in self.compiled.binds:
                bindparam = self.compiled.binds[key]
                name = self.compiled.bind_names[bindparam]
                value = self.compiled_parameters[0][name]
                if bindparam.isoutparam:
                    dbtype = bindparam.type.dialect_impl(self.dialect).get_dbapi_type(self.dialect.dbapi)
                    if not hasattr(self, 'out_parameters'):
                        self.out_parameters = {}
                    self.out_parameters[name] = self.cursor.var(dbtype)
                    self.parameters[0][name] = self.out_parameters[name]

    def get_result_proxy(self):
        if hasattr(self, 'out_parameters'):
            if self.compiled_parameters is not None and len(self.compiled_parameters) == 1:
                 for bind, name in self.compiled.bind_names.iteritems():
                     if name in self.out_parameters:
                         type = bind.type
                         self.out_parameters[name] = type.dialect_impl(self.dialect).result_processor(self.dialect)(self.out_parameters[name].getvalue())
            else:
                 for k in self.out_parameters:
                     self.out_parameters[k] = self.out_parameters[k].getvalue()

        if self.cursor.description is not None:
            for column in self.cursor.description:
                type_code = column[1]
                if type_code in self.dialect.ORACLE_BINARY_TYPES:
                    return base.BufferedColumnResultProxy(self)

        return base.ResultProxy(self)

class OracleDialect(default.DefaultDialect):
    supports_alter = True
    supports_unicode_statements = False
    max_identifier_length = 30
    reserved_words_are_reserved_for_eternity = True
    supports_sane_rowcount = True
    supports_sane_multi_rowcount = False
    preexecute_pk_sequences = True
    supports_pk_autoincrement = False

    def __init__(self, use_ansi=True, auto_setinputsizes=True, auto_convert_lobs=True, threaded=True, allow_twophase=True, **kwargs):
        default.DefaultDialect.__init__(self, default_paramstyle='named', **kwargs)
        self.use_ansi = use_ansi
        self.threaded = threaded
        self.allow_twophase = allow_twophase
        self.supports_timestamp = self.dbapi is None or hasattr(self.dbapi, 'TIMESTAMP' )
        self.auto_setinputsizes = auto_setinputsizes
        self.auto_convert_lobs = auto_convert_lobs
        if self.dbapi is None or not self.auto_convert_lobs or not 'CLOB' in self.dbapi.__dict__:
            self.dbapi_type_map = {}
            self.ORACLE_BINARY_TYPES = []
        else:
            # only use this for LOB objects.  using it for strings, dates
            # etc. leads to a little too much magic, reflection doesn't know if it should
            # expect encoded strings or unicodes, etc.
            self.dbapi_type_map = {
                self.dbapi.CLOB: OracleText(),
                self.dbapi.BLOB: OracleBinary(),
                self.dbapi.BINARY: OracleRaw(),
            }
            self.ORACLE_BINARY_TYPES = [getattr(self.dbapi, k) for k in ["BFILE", "CLOB", "NCLOB", "BLOB"] if hasattr(self.dbapi, k)]

    def dbapi(cls):
        import cx_Oracle
        return cx_Oracle
    dbapi = classmethod(dbapi)

    def create_connect_args(self, url):
        dialect_opts = dict(url.query)
        for opt in ('use_ansi', 'auto_setinputsizes', 'auto_convert_lobs',
                    'threaded', 'allow_twophase'):
            if opt in dialect_opts:
                util.coerce_kw_type(dialect_opts, opt, bool)
                setattr(self, opt, dialect_opts[opt])

        if url.database:
            # if we have a database, then we have a remote host
            port = url.port
            if port:
                port = int(port)
            else:
                port = 1521
            dsn = self.dbapi.makedsn(url.host, port, url.database)
        else:
            # we have a local tnsname
            dsn = url.host

        opts = dict(
            user=url.username,
            password=url.password,
            dsn=dsn,
            threaded=self.threaded,
            twophase=self.allow_twophase,
            )
        if 'mode' in url.query:
            opts['mode'] = url.query['mode']
            if isinstance(opts['mode'], basestring):
                mode = opts['mode'].upper()
                if mode == 'SYSDBA':
                    opts['mode'] = self.dbapi.SYSDBA
                elif mode == 'SYSOPER':
                    opts['mode'] = self.dbapi.SYSOPER
                else:
                    util.coerce_kw_type(opts, 'mode', int)
        # Can't set 'handle' or 'pool' via URL query args, use connect_args

        return ([], opts)

    def is_disconnect(self, e):
        if isinstance(e, self.dbapi.InterfaceError):
            return "not connected" in str(e)
        else:
            return "ORA-03114" in str(e) or "ORA-03113" in str(e)

    def type_descriptor(self, typeobj):
        return sqltypes.adapt_type(typeobj, colspecs)

    def oid_column_name(self, column = None, table = None):
        if column:
            table = column.table
        if not isinstance(table, (sql.TableClause, sql.Select)):
            return None
        else:
            if "rowid_" in table.columns:
                return "rowid_"
            return "rowid"

    def create_xid(self):
        """create a two-phase transaction ID.

        this id will be passed to do_begin_twophase(), do_rollback_twophase(),
        do_commit_twophase().  its format is unspecified."""

        id = random.randint(0,2**128)
        return (0x1234, "%032x" % 9, "%032x" % id)

    def do_release_savepoint(self, connection, name):
        # Oracle does not support RELEASE SAVEPOINT
        pass

    def do_begin_twophase(self, connection, xid):
        connection.connection.begin(*xid)

    def do_prepare_twophase(self, connection, xid):
        connection.connection.prepare()

    def do_rollback_twophase(self, connection, xid, is_prepared=True, recover=False):
        self.do_rollback(connection.connection)

    def do_commit_twophase(self, connection, xid, is_prepared=True, recover=False):
        self.do_commit(connection.connection)

    def do_recover_twophase(self, connection):
        pass

    def create_execution_context(self, *args, **kwargs):
        return OracleExecutionContext(self, *args, **kwargs)

    def has_table(self, connection, table_name, schema=None):
        cursor = connection.execute("""select table_name from user_tables where table_name=:name""", {'name':self._denormalize_name(table_name)})
        return bool( cursor.fetchone() is not None )

    def has_sequence(self, connection, sequence_name):
        cursor = connection.execute("""select sequence_name from user_sequences where sequence_name=:name""", {'name':self._denormalize_name(sequence_name)})
        return bool( cursor.fetchone() is not None )

    def _normalize_name(self, name):
        if name is None:
            return None
        elif name.upper() == name and not self.identifier_preparer._requires_quotes(name.lower().decode(self.encoding)):
            return name.lower().decode(self.encoding)
        else:
            return name.decode(self.encoding)

    def _denormalize_name(self, name):
        if name is None:
            return None
        elif name.lower() == name and not self.identifier_preparer._requires_quotes(name.lower()):
            return name.upper().encode(self.encoding)
        else:
            return name.encode(self.encoding)

    def get_default_schema_name(self, connection):
        return connection.execute('SELECT USER FROM DUAL').scalar()
    get_default_schema_name = base.connection_memoize(
        ('dialect', 'default_schema_name'))(get_default_schema_name)

    def table_names(self, connection, schema):
        # note that table_names() isnt loading DBLINKed or synonym'ed tables
        if schema is None:
            s = "select table_name from user_tables where tablespace_name NOT IN ('SYSTEM', 'SYSAUX')"
            cursor = connection.execute(s)
        else:
            s = "select table_name from user_tables where tablespace_name NOT IN ('SYSTEM','SYSAUX') AND OWNER = :owner"
            cursor = connection.execute(s,{'owner':self._denormalize_name(schema)})
        return [self._normalize_name(row[0]) for row in cursor]

    def _resolve_synonym(self, connection, desired_owner=None, desired_synonym=None, desired_table=None):
        """search for a local synonym matching the given desired owner/name.

        if desired_owner is None, attempts to locate a distinct owner.

        returns the actual name, owner, dblink name, and synonym name if found.
        """

        sql = """select OWNER, TABLE_OWNER, TABLE_NAME, DB_LINK, SYNONYM_NAME
                   from   USER_SYNONYMS WHERE """

        clauses = []
        params = {}
        if desired_synonym:
            clauses.append("SYNONYM_NAME=:synonym_name")
            params['synonym_name'] = desired_synonym
        if desired_owner:
            clauses.append("TABLE_OWNER=:desired_owner")
            params['desired_owner'] = desired_owner
        if desired_table:
            clauses.append("TABLE_NAME=:tname")
            params['tname'] = desired_table

        sql += " AND ".join(clauses)

        result = connection.execute(sql, **params)
        if desired_owner:
            row = result.fetchone()
            if row:
                return row['TABLE_NAME'], row['TABLE_OWNER'], row['DB_LINK'], row['SYNONYM_NAME']
            else:
                return None, None, None, None
        else:
            rows = result.fetchall()
            if len(rows) > 1:
                raise exceptions.AssertionError("There are multiple tables visible to the schema, you must specify owner")
            elif len(rows) == 1:
                row = rows[0]
                return row['TABLE_NAME'], row['TABLE_OWNER'], row['DB_LINK'], row['SYNONYM_NAME']
            else:
                return None, None, None, None

    def reflecttable(self, connection, table, include_columns):
        preparer = self.identifier_preparer

        resolve_synonyms = table.kwargs.get('oracle_resolve_synonyms', False)

        if resolve_synonyms:
            actual_name, owner, dblink, synonym = self._resolve_synonym(connection, desired_owner=self._denormalize_name(table.schema), desired_synonym=self._denormalize_name(table.name))
        else:
            actual_name, owner, dblink, synonym = None, None, None, None

        if not actual_name:
            actual_name = self._denormalize_name(table.name)
        if not dblink:
            dblink = ''
        if not owner:
            owner = self._denormalize_name(table.schema) or self.get_default_schema_name(connection)

        c = connection.execute ("select COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE, DATA_DEFAULT from USER_TAB_COLUMNS%(dblink)s where TABLE_NAME = :table_name and OWNER = :owner" % {'dblink':dblink}, {'table_name':actual_name, 'owner':owner})

        while True:
            row = c.fetchone()
            if row is None:
                break
            found_table = True

            #print "ROW:" , row
            (colname, coltype, length, precision, scale, nullable, default) = (self._normalize_name(row[0]), row[1], row[2], row[3], row[4], row[5]=='Y', row[6])

            if include_columns and colname not in include_columns:
                continue

            # INTEGER if the scale is 0 and precision is null
            # NUMBER if the scale and precision are both null
            # NUMBER(9,2) if the precision is 9 and the scale is 2
            # NUMBER(3) if the precision is 3 and scale is 0
            #length is ignored except for CHAR and VARCHAR2
            if coltype=='NUMBER' :
                if precision is None and scale is None:
                    coltype = OracleNumeric
                elif precision is None and scale == 0  :
                    coltype = OracleInteger
                else :
                    coltype = OracleNumeric(precision, scale)
            elif coltype=='CHAR' or coltype=='VARCHAR2':
                coltype = ischema_names.get(coltype, OracleString)(length)
            else:
                coltype = re.sub(r'\(\d+\)', '', coltype)
                try:
                    coltype = ischema_names[coltype]
                except KeyError:
                    util.warn("Did not recognize type '%s' of column '%s'" %
                              (coltype, colname))
                    coltype = sqltypes.NULLTYPE

            colargs = []
            if default is not None:
                colargs.append(schema.PassiveDefault(sql.text(default)))

            table.append_column(schema.Column(colname, coltype, nullable=nullable, *colargs))

        if not table.columns:
           raise exceptions.AssertionError("Couldn't find any column information for table %s" % actual_name)

        c = connection.execute("""SELECT
             ac.constraint_name,
             ac.constraint_type,
             loc.column_name AS local_column,
             rem.table_name AS remote_table,
             rem.column_name AS remote_column,
             rem.owner AS remote_owner
           FROM user_constraints%(dblink)s ac,
             user_cons_columns%(dblink)s loc,
             user_cons_columns%(dblink)s rem
           WHERE ac.table_name = :table_name
           AND ac.constraint_type IN ('R','P')
           AND ac.owner = :owner
           AND ac.owner = loc.owner
           AND ac.constraint_name = loc.constraint_name
           AND ac.r_owner = rem.owner(+)
           AND ac.r_constraint_name = rem.constraint_name(+)
           -- order multiple primary keys correctly
           ORDER BY ac.constraint_name, loc.position, rem.position"""
         % {'dblink':dblink}, {'table_name' : actual_name, 'owner' : owner})

        fks = {}
        while True:
            row = c.fetchone()
            if row is None:
                break
            #print "ROW:" , row
            (cons_name, cons_type, local_column, remote_table, remote_column, remote_owner) = row[0:2] + tuple([self._normalize_name(x) for x in row[2:]])
            if cons_type == 'P':
                table.primary_key.add(table.c[local_column])
            elif cons_type == 'R':
                try:
                    fk = fks[cons_name]
                except KeyError:
                   fk = ([], [])
                   fks[cons_name] = fk
                if remote_table is None:
                    # ticket 363
                    util.warn(
                        ("Got 'None' querying 'table_name' from "
                         "user_cons_columns%(dblink)s - does the user have "
                         "proper rights to the table?") % {'dblink':dblink})
                    continue

                if resolve_synonyms:
                    ref_remote_name, ref_remote_owner, ref_dblink, ref_synonym = self._resolve_synonym(connection, desired_owner=self._denormalize_name(remote_owner), desired_table=self._denormalize_name(remote_table))
                    if ref_synonym:
                        remote_table = self._normalize_name(ref_synonym)
                        remote_owner = self._normalize_name(ref_remote_owner)

                if not table.schema and self._denormalize_name(remote_owner) == owner:
                    refspec =  ".".join([remote_table, remote_column])
                    t = schema.Table(remote_table, table.metadata, autoload=True, autoload_with=connection, oracle_resolve_synonyms=resolve_synonyms, useexisting=True)
                else:
                    refspec =  ".".join([x for x in [remote_owner, remote_table, remote_column] if x])
                    t = schema.Table(remote_table, table.metadata, autoload=True, autoload_with=connection, schema=remote_owner, oracle_resolve_synonyms=resolve_synonyms, useexisting=True)

                if local_column not in fk[0]:
                    fk[0].append(local_column)
                if refspec not in fk[1]:
                    fk[1].append(refspec)

        for name, value in fks.iteritems():
            table.append_constraint(schema.ForeignKeyConstraint(value[0], value[1], name=name))


OracleDialect.logger = logging.class_logger(OracleDialect)

class _OuterJoinColumn(sql.ClauseElement):
    __visit_name__ = 'outer_join_column'
    def __init__(self, column):
        self.column = column
    def _get_from_objects(self, **kwargs):
        return []

class OracleCompiler(compiler.DefaultCompiler):
    """Oracle compiler modifies the lexical structure of Select
    statements to work under non-ANSI configured Oracle databases, if
    the use_ansi flag is False.
    """

    operators = compiler.DefaultCompiler.operators.copy()
    operators.update(
        {
            sql_operators.mod : lambda x, y:"mod(%s, %s)" % (x, y)
        }
    )

    functions = compiler.DefaultCompiler.functions.copy()
    functions.update (
        {
            sql_functions.now : 'CURRENT_TIMESTAMP'
        }
    )

    def __init__(self, *args, **kwargs):
        super(OracleCompiler, self).__init__(*args, **kwargs)
        self.__wheres = {}

    def default_from(self):
        """Called when a ``SELECT`` statement has no froms, and no ``FROM`` clause is to be appended.

        The Oracle compiler tacks a "FROM DUAL" to the statement.
        """

        return " FROM DUAL"

    def apply_function_parens(self, func):
        return len(func.clauses) > 0

    def visit_bindparam(self, bindparam, **kwargs):
        value_name = compiler.DefaultCompiler.visit_bindparam(self, bindparam, **kwargs)
        if kwargs.get('_oracle_in_where', False):
            return value_name

        type_spec = None
        if not hasattr(bindparam.type, 'length') or bindparam.type.length is not None:
            try:
                type_spec = self.dialect.type_descriptor(bindparam.type).get_col_spec()
            except NotImplementedError:
                pass
        if type_spec:
            return "cast(%(value_name)s as %(type)s)" % {
                'value_name': value_name,
                'type': type_spec
                }
        else:
            return value_name

    def _get_nonansi_join_whereclause(self, froms):
        clauses = []

        def visit_join(join):
            if join.isouter:
                def visit_binary(binary):
                    if binary.operator == sql_operators.eq:
                        if binary.left.table is join.right:
                            binary.left = _OuterJoinColumn(binary.left)
                        elif binary.right.table is join.right:
                            binary.right = _OuterJoinColumn(binary.right)
                clauses.append(visitors.traverse(join.onclause, visit_binary=visit_binary, clone=True))
            else:
                clauses.append(join.onclause)

        for f in froms:
            visitors.traverse(f, visit_join=visit_join)
        return sql.and_(*clauses)

    def _get_boolean_statement(self, what, left, right, **kwargs):
        """
        Get boolean statement, acts depending on oracle_in_where value
        in kwargs.
        """
        if kwargs.get('_oracle_in_where', False):
            return "%s %s %s" % (left, compiler.OPERATORS[what], right)
        else:
            return "%s(%s, %s)" % (self.boolean_plsqlnames[what], left, right)

    def visit_outer_join_column(self, vc):
        return self.process(vc.column) + "(+)"

    def visit_sequence(self, seq):
        return self.dialect.identifier_preparer.format_sequence(seq) + ".nextval"

    def visit_alias(self, alias, asfrom=False, **kwargs):
        """Oracle doesn't like ``FROM table AS alias``.  Is the AS standard SQL??"""

        if asfrom:
            return self.process(alias.original, asfrom=asfrom, **kwargs) + " " + self.preparer.format_alias(alias, self._anonymize(alias.name))
        else:
            return self.process(alias.original, **kwargs)

    def _TODO_visit_compound_select(self, select):
        """Need to determine how to get ``LIMIT``/``OFFSET`` into a ``UNION`` for Oracle."""
        pass

    boolean_plsqlnames = {sql_operators.inv: 'sqlalchemy.is_not',
                          sql_operators.and_: 'sqlalchemy.is_and',
                          sql_operators.or_: 'sqlalchemy.is_or',
                          sql_operators.is_: 'sqlalchemy.is_is_null',
                          sql_operators.isnot: 'sqlalchemy.is_is_not_null',
                          sql_operators.eq: 'sqlalchemy.is_equal',
                          sql_operators.ne: 'sqlalchemy.is_not_equal',
                          sql_operators.gt: 'sqlalchemy.is_greater',
                          sql_operators.lt: 'sqlalchemy.is_smaller',
                          sql_operators.ge: 'sqlalchemy.is_greater_or_equal',
                          sql_operators.le: 'sqlalchemy.is_smaller_or_equal',
                          }
    
    def visit_unary(self, unary, **kwargs):
        what = unary.operator

        if ( kwargs.get('_oracle_in_where', False)
             and what in (sql_operators.inv, sql_operators.is_, sql_operators.isnot) ):
            res = '%s %s' % (compiler.OPERATORS[what], self.process(unary.element, **kwargs))
            if kwargs.get('_oracle_in_where', False) and isinstance(unary.element, expression._BindParamClause):
                res += ' = 1'
            return res
            
        elif what in self.boolean_plsqlnames:
            return "%s(%s)"  % (self.boolean_plsqlnames[what],
                                self.process(unary.element, **kwargs))
        else:
            return compiler.DefaultCompiler.visit_unary(self, unary, **kwargs)

    def visit_binary(self, binary, **kwargs):
        what = binary.operator
        if what in (sql_operators.is_, sql_operators.isnot):
            opers = [binary.left, binary.right] 

            assert isinstance(opers[0], sql.expression._Null) or isinstance(opers[1], sql.expression._Null)

            if isinstance(opers[0], sql.expression._Null) and isinstance(opers[1], sql.expression._Null):
                return "1"

            if isinstance(opers[0], sql.expression._Null):
                opers.reverse()

            if kwargs.get('_oracle_in_where', False):
                return '%s %s NULL' % (self.process(opers[0], **kwargs),
                                       compiler.OPERATORS[what])
            else:
                return "%s(%s)"  % (self.boolean_plsqlnames[what],
                                    self.process(opers[0], **kwargs))
        elif what is sql.operators.in_op and not kwargs.get('_oracle_in_where', False):
            if isinstance(binary.right, sql.expression._Grouping):
                return self.process(sql.or_(*[binary.left == clause 
                                              for clause in binary.right.elem.clauses]),
                                    **kwargs)
            elif isinstance(binary.right, (sql.expression._FromGrouping, sql.expression.Alias)):
                if isinstance(binary.right, sql.expression._FromGrouping):
                    right = binary.right.elem
                    right_alias_args = []
                else:
                    right = binary.right.selectable
                    right_alias_args = [binary.right.name]
                first_column_name = right.columns.keys()[0]
                first_column = right.columns[first_column_name]
                first_column_table = first_column.table

                # This is to have the select clause named
                first_column_table_alias = first_column_table.alias(*right_alias_args)
                first_column_alias = getattr(first_column_table_alias.columns, first_column_name)

                kwargs['asfrom'] = True
                return self.process(sql.select([sql.func.max(binary.left == first_column_alias
                                                             ).label(first_column_name)
                                                ]),
                                    **kwargs)
            else:
                import pdb
                pdb.set_trace()
                raise Exception("Unknown type of expression used to the right of IN operator")

        elif what in self.boolean_plsqlnames:
            lr_kwargs = dict(kwargs)
            lr_kwargs['_oracle_in_where'] = False

            return self._get_boolean_statement(what,
                                               self.process(binary.left, **lr_kwargs),
                                               self.process(binary.right, **lr_kwargs),
                                               **kwargs)
        else:
            # FIXME: Are there any other operators we need to handle specially?
            # import pdb
            # pdb.set_trace()
            return compiler.DefaultCompiler.visit_binary(self, binary, **kwargs)

    def visit_clauselist(self, clauselist, **kwargs):
        what = getattr(clauselist, 'operator', None)
        what = what or clauselist.clauses and getattr(clauselist.clauses[0], 'text', None)

        if what == 'WHEN':
            in_where = dict(kwargs)
            in_where['_oracle_in_where'] = True

            return "when %s then %s"  % (
                self.process(clauselist.clauses[1], **in_where),
                self.process(clauselist.clauses[3], **kwargs))
        elif what in self.boolean_plsqlnames:
            res = ""

            for subclause in reversed(clauselist.clauses):
                res_sub = self.process(subclause, **kwargs)
                if kwargs.get('_oracle_in_where', False) and isinstance(subclause, expression._BindParamClause):
                    res_sub += ' = 1'

                if not res:
                    res = res_sub
                else:
                    res = self._get_boolean_statement(what, res_sub, res, **kwargs)

            return res
        else:
            return compiler.DefaultCompiler.visit_clauselist(self, clauselist, **kwargs)

    def visit_calculatedclause(self, clause, **kwargs):
        what = getattr(clause.clause_expr, 'operator', None)
        what = what or clause.clause_expr.clauses and getattr(clause.clause_expr.clauses[0], 'text', None)

        expr = compiler.DefaultCompiler.visit_calculatedclause(self, clause, **kwargs)
        if what == 'CASE' and kwargs.get('_oracle_in_where', False):
            expr = '%s = 1' % (expr, )

        return expr

    def visit_select(self, select, **kwargs):
        """Look for ``LIMIT`` and OFFSET in a select statement, and if
        so tries to wrap it in a subquery with ``row_number()`` criterion.
        """
        if not getattr(select, '_oracle_visit', None):
            if not self.dialect.use_ansi:
                if self.stack and 'from' in self.stack[-1]:
                    existingfroms = self.stack[-1]['from']
                else:
                    existingfroms = None

                froms = select._get_display_froms(existingfroms)
                whereclause = self._get_nonansi_join_whereclause(froms)
                if whereclause:
                    select = select.where(whereclause)
                    select._oracle_visit = True

            if select._limit is not None or select._offset is not None:
                # to use ROW_NUMBER(), an ORDER BY is required.
                orderby = self.process(select._order_by_clause)
                if not orderby:
                    orderby = self.process(getattr(select, self.oid_column_name(table = select)))
                    #orderby = list(select.oid_column.proxies)[0]
                    #orderby = self.process(orderby)

                select = select.column(sql.literal_column("ROW_NUMBER() OVER (ORDER BY %s)" % orderby).label("ora_rn")).order_by(None)
                select._oracle_visit = True

                limitselect = sql.select([c for c in select.c if c.key!='ora_rn'])
                limitselect._oracle_visit = True
                limitselect._is_wrapper = True

                if select._offset is not None:
                    limitselect.append_whereclause(select.c.ora_rn > select._offset)
                    if select._limit is not None:
                        limitselect.append_whereclause(select.c.ora_rn <= select._limit + select._offset)
                else:
                    limitselect.append_whereclause(select.c.ora_rn <= select._limit)
                select = limitselect

        kwargs['iswrapper'] = getattr(select, '_is_wrapper', False)
        return compiler.DefaultCompiler.visit_select(self, select, **kwargs)

    def visit_join(self, join, **kwargs):
        if self.dialect.use_ansi:
            return (self.process(join.left, asfrom=True) + (join.isouter and " LEFT OUTER JOIN " or " JOIN ") + \
                    self.process(join.right, asfrom=True) + " ON " + self.process(join.onclause, _oracle_in_where = True))
        else:
            return self.process(join.left, asfrom=True) + ", " + self.process(join.right, asfrom=True)

    def limit_clause(self, select):
        return ""

    def for_update_clause(self, select):
        if select.for_update=="nowait":
            return " FOR UPDATE NOWAIT"
        else:
            return super(OracleCompiler, self).for_update_clause(select)

    def get_select_where(self, select, **kwargs):
        kwargs['_oracle_in_where'] = True
        return compiler.DefaultCompiler.get_select_where(self, select, **kwargs)

class OracleSchemaGenerator(compiler.SchemaGenerator):
    def get_column_specification(self, column, **kwargs):
        colspec = self.preparer.format_column(column)
        colspec += " " + column.type.dialect_impl(self.dialect, _for_ddl=column).get_col_spec()
        default = self.get_column_default_string(column)
        if default is not None:
            colspec += " DEFAULT " + default

        if not column.nullable:
            colspec += " NOT NULL"
        return colspec

    def visit_sequence(self, sequence):
        if not self.checkfirst  or not self.dialect.has_sequence(self.connection, sequence.name):
            self.append("CREATE SEQUENCE %s" % self.preparer.format_sequence(sequence))
            self.execute()

class OracleSchemaDropper(compiler.SchemaDropper):
    def visit_sequence(self, sequence):
        if not self.checkfirst or self.dialect.has_sequence(self.connection, sequence.name):
            self.append("DROP SEQUENCE %s" % self.preparer.format_sequence(sequence))
            self.execute()

class OracleDefaultRunner(base.DefaultRunner):
    def visit_sequence(self, seq):
        return self.execute_string("SELECT " + self.dialect.identifier_preparer.format_sequence(seq) + ".nextval FROM DUAL", {})

class OracleIdentifierPreparer(compiler.IdentifierPreparer):
    reserved_words = RESERVED_WORDS
    def format_savepoint(self, savepoint):
        name = re.sub(r'^_+', '', savepoint.ident)
        return super(OracleIdentifierPreparer, self).format_savepoint(savepoint, name)

    def quote_identifier(self, value):
        # Oracle reserved words are not quotable so instead use the
        # truncate algorithm to handle them properly as names.

        if value in self.reserved_words:
            return value
        else:
            if len(value) > OracleDialect.max_identifier_length:
                value = self._escape_identifier(self._truncate_identifier("colident", value, value))
            return self.initial_quote + self._escape_identifier(value) + self.final_quote

dialect = OracleDialect
dialect.statement_compiler = OracleCompiler
dialect.schemagenerator = OracleSchemaGenerator
dialect.schemadropper = OracleSchemaDropper
dialect.preparer = OracleIdentifierPreparer
dialect.defaultrunner = OracleDefaultRunner
