import testenv; testenv.configure_for_tests()
import datetime, re, operator
from sqlalchemy import *
from sqlalchemy import exceptions, sql, util
from sqlalchemy.sql import table, column
from sqlalchemy.databases import sqlite, postgres, mysql, oracle, firebird, mssql
from testlib import *

table1 = table('mytable',
    column('myid', Integer),
    column('name', String),
    column('description', String),
)

table2 = table(
    'myothertable',
    column('otherid', Integer),
    column('othername', String),
)

table3 = table(
    'thirdtable',
    column('userid', Integer),
    column('otherstuff', String),
)

metadata = MetaData()
table4 = Table(
    'remotetable', metadata,
    Column('rem_id', Integer, primary_key=True),
    Column('datatype_id', Integer),
    Column('value', String(20)),
    schema = 'remote_owner'
)

users = table('users',
    column('user_id'),
    column('user_name'),
    column('password'),
)

addresses = table('addresses',
    column('address_id'),
    column('user_id'),
    column('street'),
    column('city'),
    column('state'),
    column('zip')
)

class SelectTest(TestBase, AssertsCompiledSQL):

    def test_attribute_sanity(self):
        assert hasattr(table1, 'c')
        assert hasattr(table1.select(), 'c')
        assert not hasattr(table1.c.myid.self_group(), 'columns')
        assert hasattr(table1.select().self_group(), 'columns')
        assert not hasattr(select([table1.c.myid]).as_scalar().self_group(), 'columns')
        assert not hasattr(table1.c.myid, 'columns')
        assert not hasattr(table1.c.myid, 'c')
        assert not hasattr(table1.select().c.myid, 'c')
        assert not hasattr(table1.select().c.myid, 'columns')
        assert not hasattr(table1.alias().c.myid, 'columns')
        assert not hasattr(table1.alias().c.myid, 'c')

    def test_table_select(self):
        self.assert_compile(table1.select(), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable")

        self.assert_compile(select([table1, table2]), "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, \
myothertable.othername FROM mytable, myothertable")

    def test_from_subquery(self):
        """tests placing select statements in the column clause of another select, for the
        purposes of selecting from the exported columns of that select."""
        
        s = select([table1], table1.c.name == 'jack')
        self.assert_compile(
            select(
                [s],
                s.c.myid == 7
            )
            ,
        "SELECT myid, name, description FROM (SELECT mytable.myid AS myid, mytable.name AS name, mytable.description AS description FROM mytable "\
        "WHERE mytable.name = :mytable_name_1) WHERE myid = :myid_1")

        sq = select([table1])
        self.assert_compile(
            sq.select(),
            "SELECT myid, name, description FROM (SELECT mytable.myid AS myid, mytable.name AS name, mytable.description AS description FROM mytable)"
        )

        sq = select(
            [table1],
        ).alias('sq')

        self.assert_compile(
            sq.select(sq.c.myid == 7),
            "SELECT sq.myid, sq.name, sq.description FROM \
(SELECT mytable.myid AS myid, mytable.name AS name, mytable.description AS description FROM mytable) AS sq WHERE sq.myid = :sq_myid_1"
        )

        sq = select(
            [table1, table2],
            and_(table1.c.myid ==7, table2.c.otherid==table1.c.myid),
            use_labels = True
        ).alias('sq')

        sqstring = "SELECT mytable.myid AS mytable_myid, mytable.name AS mytable_name, \
mytable.description AS mytable_description, myothertable.otherid AS myothertable_otherid, \
myothertable.othername AS myothertable_othername FROM mytable, myothertable \
WHERE mytable.myid = :mytable_myid_1 AND myothertable.otherid = mytable.myid"

        self.assert_compile(sq.select(), "SELECT sq.mytable_myid, sq.mytable_name, sq.mytable_description, sq.myothertable_otherid, \
sq.myothertable_othername FROM (" + sqstring + ") AS sq")

        sq2 = select(
            [sq],
            use_labels = True
        ).alias('sq2')

        self.assert_compile(sq2.select(), "SELECT sq2.sq_mytable_myid, sq2.sq_mytable_name, sq2.sq_mytable_description, \
sq2.sq_myothertable_otherid, sq2.sq_myothertable_othername FROM \
(SELECT sq.mytable_myid AS sq_mytable_myid, sq.mytable_name AS sq_mytable_name, \
sq.mytable_description AS sq_mytable_description, sq.myothertable_otherid AS sq_myothertable_otherid, \
sq.myothertable_othername AS sq_myothertable_othername FROM (" + sqstring + ") AS sq) AS sq2")

    def test_nested_uselabels(self):
        """test nested anonymous label generation.  this
        essentially tests the ANONYMOUS_LABEL regex.
        """

        s1 = table1.select()
        s2 = s1.alias()
        s3 = select([s2], use_labels=True)
        s4 = s3.alias()
        s5 = select([s4], use_labels=True)
        self.assert_compile(s5, "SELECT anon_1.anon_2_myid AS anon_1_anon_2_myid, anon_1.anon_2_name AS anon_1_anon_2_name, "\
        "anon_1.anon_2_description AS anon_1_anon_2_description FROM (SELECT anon_2.myid AS anon_2_myid, anon_2.name AS anon_2_name, "\
        "anon_2.description AS anon_2_description FROM (SELECT mytable.myid AS myid, mytable.name AS name, mytable.description "\
        "AS description FROM mytable) AS anon_2) AS anon_1")

    def test_dont_overcorrelate(self):
        self.assert_compile(select([table1], from_obj=[table1, table1.select()]), """SELECT mytable.myid, mytable.name, mytable.description FROM mytable, (SELECT mytable.myid AS myid, mytable.name AS name, mytable.description AS description FROM mytable)""")
    
    def test_intentional_full_correlate(self):
        """test a subquery that has no FROM clause."""
        
        t = table('t', column('a'), column('b'))
        s = select([t.c.a]).where(t.c.a==1).correlate(t).as_scalar()

        s2 = select([t.c.a, s])
        self.assert_compile(s2, """SELECT t.a, (SELECT t.a WHERE t.a = :t_a_1) AS anon_1 FROM t""")
        
    def test_exists(self):
        self.assert_compile(exists([table1.c.myid], table1.c.myid==5).select(), "SELECT EXISTS (SELECT mytable.myid FROM mytable WHERE mytable.myid = :mytable_myid_1)", params={'mytable_myid':5})

        self.assert_compile(select([table1, exists([1], from_obj=table2)]), "SELECT mytable.myid, mytable.name, mytable.description, EXISTS (SELECT 1 FROM myothertable) FROM mytable", params={})

        self.assert_compile(select([table1, exists([1], from_obj=table2).label('foo')]), "SELECT mytable.myid, mytable.name, mytable.description, EXISTS (SELECT 1 FROM myothertable) AS foo FROM mytable", params={})

        self.assert_compile(
          table1.select(exists([1], table2.c.otherid == table1.c.myid).correlate(table1)),
          "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE EXISTS (SELECT 1 FROM myothertable WHERE myothertable.otherid = mytable.myid)"
        )

        self.assert_compile(
          table1.select(exists([1]).where(table2.c.otherid == table1.c.myid).correlate(table1)),
          "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE EXISTS (SELECT 1 FROM myothertable WHERE myothertable.otherid = mytable.myid)"
        )

        self.assert_compile(
          table1.select(exists([1]).where(table2.c.otherid == table1.c.myid).correlate(table1)).replace_selectable(table2, table2.alias()),
          "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE EXISTS (SELECT 1 FROM myothertable AS myothertable_1 WHERE myothertable_1.otherid = mytable.myid)"
        )

        self.assert_compile(
          table1.select(exists([1]).where(table2.c.otherid == table1.c.myid).correlate(table1)).select_from(table1.join(table2, table1.c.myid==table2.c.otherid)).replace_selectable(table2, table2.alias()),
          "SELECT mytable.myid, mytable.name, mytable.description FROM mytable JOIN myothertable AS myothertable_1 ON mytable.myid = myothertable_1.otherid WHERE EXISTS (SELECT 1 FROM myothertable AS myothertable_1 WHERE myothertable_1.otherid = mytable.myid)"
        )

    def test_where_subquery(self):
        s = select([addresses.c.street], addresses.c.user_id==users.c.user_id, correlate=True).alias('s')
        self.assert_compile(
            select([users, s.c.street], from_obj=s),
            """SELECT users.user_id, users.user_name, users.password, s.street FROM users, (SELECT addresses.street AS street FROM addresses WHERE addresses.user_id = users.user_id) AS s""")

        self.assert_compile(
            table1.select(table1.c.myid == select([table1.c.myid], table1.c.name=='jack')),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = (SELECT mytable.myid FROM mytable WHERE mytable.name = :mytable_name_1)"
        )

        self.assert_compile(
            table1.select(table1.c.myid == select([table2.c.otherid], table1.c.name == table2.c.othername)),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = (SELECT myothertable.otherid FROM myothertable WHERE mytable.name = myothertable.othername)"
        )

        self.assert_compile(
            table1.select(exists([1], table2.c.otherid == table1.c.myid)),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE EXISTS (SELECT 1 FROM myothertable WHERE myothertable.otherid = mytable.myid)"
        )


        talias = table1.alias('ta')
        s = subquery('sq2', [talias], exists([1], table2.c.otherid == talias.c.myid))
        self.assert_compile(
            select([s, table1])
            ,"SELECT sq2.myid, sq2.name, sq2.description, mytable.myid, mytable.name, mytable.description FROM (SELECT ta.myid AS myid, ta.name AS name, ta.description AS description FROM mytable AS ta WHERE EXISTS (SELECT 1 FROM myothertable WHERE myothertable.otherid = ta.myid)) AS sq2, mytable")

        s = select([addresses.c.street], addresses.c.user_id==users.c.user_id, correlate=True).alias('s')
        self.assert_compile(
            select([users, s.c.street], from_obj=s),
            """SELECT users.user_id, users.user_name, users.password, s.street FROM users, (SELECT addresses.street AS street FROM addresses WHERE addresses.user_id = users.user_id) AS s""")

        # test constructing the outer query via append_column(), which occurs in the ORM's Query object
        s = select([], exists([1], table2.c.otherid==table1.c.myid), from_obj=table1)
        s.append_column(table1)
        self.assert_compile(
            s,
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE EXISTS (SELECT 1 FROM myothertable WHERE myothertable.otherid = mytable.myid)"
        )


    def test_orderby_subquery(self):
        self.assert_compile(
            table1.select(order_by=[select([table2.c.otherid], table1.c.myid==table2.c.otherid)]),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable ORDER BY (SELECT myothertable.otherid FROM myothertable WHERE mytable.myid = myothertable.otherid)"
        )
        self.assert_compile(
            table1.select(order_by=[desc(select([table2.c.otherid], table1.c.myid==table2.c.otherid))]),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable ORDER BY (SELECT myothertable.otherid FROM myothertable WHERE mytable.myid = myothertable.otherid) DESC"
        )

    @testing.uses_deprecated('scalar option')
    def test_scalar_select(self):
        try:
            s = select([table1.c.myid, table1.c.name]).as_scalar()
            assert False
        except exceptions.InvalidRequestError, err:
            assert str(err) == "Scalar select can only be created from a Select object that has exactly one column expression.", str(err)

        try:
            # generic function which will look at the type of expression
            func.coalesce(select([table1.c.myid]))
            assert False
        except exceptions.InvalidRequestError, err:
            assert str(err) == "Select objects don't have a type.  Call as_scalar() on this Select object to return a 'scalar' version of this Select.", str(err)

        s = select([table1.c.myid], scalar=True, correlate=False)
        self.assert_compile(select([table1, s]), "SELECT mytable.myid, mytable.name, mytable.description, (SELECT mytable.myid FROM mytable) AS anon_1 FROM mytable")

        s = select([table1.c.myid], scalar=True)
        self.assert_compile(select([table2, s]), "SELECT myothertable.otherid, myothertable.othername, (SELECT mytable.myid FROM mytable) AS anon_1 FROM myothertable")

        s = select([table1.c.myid]).correlate(None).as_scalar()
        self.assert_compile(select([table1, s]), "SELECT mytable.myid, mytable.name, mytable.description, (SELECT mytable.myid FROM mytable) AS anon_1 FROM mytable")

        s = select([table1.c.myid]).as_scalar()
        self.assert_compile(select([table2, s]), "SELECT myothertable.otherid, myothertable.othername, (SELECT mytable.myid FROM mytable) AS anon_1 FROM myothertable")

        # test expressions against scalar selects
        self.assert_compile(select([s - literal(8)]), "SELECT (SELECT mytable.myid FROM mytable) - :param_1 AS anon_1")
        self.assert_compile(select([select([table1.c.name]).as_scalar() + literal('x')]), "SELECT (SELECT mytable.name FROM mytable) || :param_1 AS anon_1")
        self.assert_compile(select([s > literal(8)]), "SELECT (SELECT mytable.myid FROM mytable) > :param_1 AS anon_1")

        self.assert_compile(select([select([table1.c.name]).label('foo')]), "SELECT (SELECT mytable.name FROM mytable) AS foo")

        # scalar selects should not have any attributes on their 'c' or 'columns' attribute
        s = select([table1.c.myid]).as_scalar()
        try:
            s.c.foo
        except exceptions.InvalidRequestError, err:
            assert str(err) == 'Scalar Select expression has no columns; use this object directly within a column-level expression.'

        try:
            s.columns.foo
        except exceptions.InvalidRequestError, err:
            assert str(err) == 'Scalar Select expression has no columns; use this object directly within a column-level expression.'

        zips = table('zips',
            column('zipcode'),
            column('latitude'),
            column('longitude'),
        )
        places = table('places',
            column('id'),
            column('nm')
        )
        zip = '12345'
        qlat = select([zips.c.latitude], zips.c.zipcode == zip).correlate(None).as_scalar()
        qlng = select([zips.c.longitude], zips.c.zipcode == zip).correlate(None).as_scalar()

        q = select([places.c.id, places.c.nm, zips.c.zipcode, func.latlondist(qlat, qlng).label('dist')],
                         zips.c.zipcode==zip,
                         order_by = ['dist', places.c.nm]
                         )

        self.assert_compile(q,"SELECT places.id, places.nm, zips.zipcode, latlondist((SELECT zips.latitude FROM zips WHERE "
        "zips.zipcode = :zips_zipcode_1), (SELECT zips.longitude FROM zips WHERE zips.zipcode = :zips_zipcode_2)) AS dist "
        "FROM places, zips WHERE zips.zipcode = :zips_zipcode_3 ORDER BY dist, places.nm")

        zalias = zips.alias('main_zip')
        qlat = select([zips.c.latitude], zips.c.zipcode == zalias.c.zipcode, scalar=True)
        qlng = select([zips.c.longitude], zips.c.zipcode == zalias.c.zipcode, scalar=True)
        q = select([places.c.id, places.c.nm, zalias.c.zipcode, func.latlondist(qlat, qlng).label('dist')],
                         order_by = ['dist', places.c.nm]
                         )
        self.assert_compile(q, "SELECT places.id, places.nm, main_zip.zipcode, latlondist((SELECT zips.latitude FROM zips WHERE zips.zipcode = main_zip.zipcode), (SELECT zips.longitude FROM zips WHERE zips.zipcode = main_zip.zipcode)) AS dist FROM places, zips AS main_zip ORDER BY dist, places.nm")

        a1 = table2.alias('t2alias')
        s1 = select([a1.c.otherid], table1.c.myid==a1.c.otherid, scalar=True)
        j1 = table1.join(table2, table1.c.myid==table2.c.otherid)
        s2 = select([table1, s1], from_obj=j1)
        self.assert_compile(s2, "SELECT mytable.myid, mytable.name, mytable.description, (SELECT t2alias.otherid FROM myothertable AS t2alias WHERE mytable.myid = t2alias.otherid) AS anon_1 FROM mytable JOIN myothertable ON mytable.myid = myothertable.otherid")

    def test_label_comparison(self):
        x = func.lala(table1.c.myid).label('foo')
        self.assert_compile(select([x], x==5), "SELECT lala(mytable.myid) AS foo FROM mytable WHERE lala(mytable.myid) = :param_1")

    def test_conjunctions(self):
        self.assert_compile(
            and_(table1.c.myid == 12, table1.c.name=='asdf', table2.c.othername == 'foo', "sysdate() = today()"),
            "mytable.myid = :mytable_myid_1 AND mytable.name = :mytable_name_1 "\
            "AND myothertable.othername = :myothertable_othername_1 AND sysdate() = today()"
        )

        self.assert_compile(
            and_(
                table1.c.myid == 12,
                or_(table2.c.othername=='asdf', table2.c.othername == 'foo', table2.c.otherid == 9),
                "sysdate() = today()",
            ),
            "mytable.myid = :mytable_myid_1 AND (myothertable.othername = :myothertable_othername_1 OR "\
            "myothertable.othername = :myothertable_othername_2 OR myothertable.otherid = :myothertable_otherid_1) AND sysdate() = today()",
            checkparams = {'myothertable_othername_1': 'asdf', 'myothertable_othername_2':'foo', 'myothertable_otherid_1': 9, 'mytable_myid_1': 12}
        )

    def test_distinct(self):
        self.assert_compile(
            select([table1.c.myid.distinct()]), "SELECT DISTINCT mytable.myid FROM mytable"
        )

        self.assert_compile(
            select([distinct(table1.c.myid)]), "SELECT DISTINCT mytable.myid FROM mytable"
        )

        self.assert_compile(
            select([table1.c.myid]).distinct(), "SELECT DISTINCT mytable.myid FROM mytable"
        )

        self.assert_compile(
            select([func.count(table1.c.myid.distinct())]), "SELECT count(DISTINCT mytable.myid) AS count_1 FROM mytable"
        )

        self.assert_compile(
            select([func.count(distinct(table1.c.myid))]), "SELECT count(DISTINCT mytable.myid) AS count_1 FROM mytable"
        )

    def test_operators(self):
        for (py_op, sql_op) in ((operator.add, '+'), (operator.mul, '*'),
                                (operator.sub, '-'), (operator.div, '/'),
                                ):
            for (lhs, rhs, res) in (
                (5, table1.c.myid, ':mytable_myid_1 %s mytable.myid'),
                (5, literal(5), ':param_1 %s :param_2'),
                (table1.c.myid, 'b', 'mytable.myid %s :mytable_myid_1'),
                (table1.c.myid, literal(2.7), 'mytable.myid %s :param_1'),
                (table1.c.myid, table1.c.myid, 'mytable.myid %s mytable.myid'),
                (literal(5), 8, ':param_1 %s :param_2'),
                (literal(6), table1.c.myid, ':param_1 %s mytable.myid'),
                (literal(7), literal(5.5), ':param_1 %s :param_2'),
                ):
                self.assert_compile(py_op(lhs, rhs), res % sql_op)

        dt = datetime.datetime.today()
        # exercise comparison operators
        for (py_op, fwd_op, rev_op) in ((operator.lt, '<', '>'),
                                        (operator.gt, '>', '<'),
                                        (operator.eq, '=', '='),
                                        (operator.ne, '!=', '!='),
                                        (operator.le, '<=', '>='),
                                        (operator.ge, '>=', '<=')):
            for (lhs, rhs, l_sql, r_sql) in (
                ('a', table1.c.myid, ':mytable_myid_1', 'mytable.myid'),
                ('a', literal('b'), ':param_2', ':param_1'), # note swap!
                (table1.c.myid, 'b', 'mytable.myid', ':mytable_myid_1'),
                (table1.c.myid, literal('b'), 'mytable.myid', ':param_1'),
                (table1.c.myid, table1.c.myid, 'mytable.myid', 'mytable.myid'),
                (literal('a'), 'b', ':param_1', ':param_2'),
                (literal('a'), table1.c.myid, ':param_1', 'mytable.myid'),
                (literal('a'), literal('b'), ':param_1', ':param_2'),
                (dt, literal('b'), ':param_2', ':param_1'),
                (literal('b'), dt, ':param_1', ':param_2'),
                ):

                # the compiled clause should match either (e.g.):
                # 'a' < 'b' -or- 'b' > 'a'.
                compiled = str(py_op(lhs, rhs))
                fwd_sql = "%s %s %s" % (l_sql, fwd_op, r_sql)
                rev_sql = "%s %s %s" % (r_sql, rev_op, l_sql)

                self.assert_(compiled == fwd_sql or compiled == rev_sql,
                             "\n'" + compiled + "'\n does not match\n'" +
                             fwd_sql + "'\n or\n'" + rev_sql + "'")

        self.assert_compile(
         table1.select((table1.c.myid != 12) & ~(table1.c.name=='john')),
         "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid != :mytable_myid_1 AND mytable.name != :mytable_name_1"
        )

        self.assert_compile(
         table1.select((table1.c.myid != 12) & ~(table1.c.name.between('jack','john'))),
         "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid != :mytable_myid_1 AND "\
         "NOT (mytable.name BETWEEN :mytable_name_1 AND :mytable_name_2)"
        )

        self.assert_compile(
         table1.select((table1.c.myid != 12) & ~and_(table1.c.name=='john', table1.c.name=='ed', table1.c.name=='fred')),
         "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid != :mytable_myid_1 AND "\
         "NOT (mytable.name = :mytable_name_1 AND mytable.name = :mytable_name_2 AND mytable.name = :mytable_name_3)"
        )

        self.assert_compile(
         table1.select((table1.c.myid != 12) & ~table1.c.name),
         "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid != :mytable_myid_1 AND NOT mytable.name"
        )

        self.assert_compile(
         literal("a") + literal("b") * literal("c"), ":param_1 || :param_2 * :param_3"
        )

        # test the op() function, also that its results are further usable in expressions
        self.assert_compile(
            table1.select(table1.c.myid.op('hoho')(12)==14),
            "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE (mytable.myid hoho :mytable_myid_1) = :param_1"
        )

        # test that clauses can be pickled (operators need to be module-level, etc.)
        clause = (table1.c.myid == 12) & table1.c.myid.between(15, 20) & table1.c.myid.like('hoho')
        assert str(clause) == str(util.pickle.loads(util.pickle.dumps(clause)))


    def test_like(self):
        for expr, check, dialect in [
            (table1.c.myid.like('somstr'), "mytable.myid LIKE :mytable_myid_1", None),
            (~table1.c.myid.like('somstr'), "mytable.myid NOT LIKE :mytable_myid_1", None),
            (table1.c.myid.like('somstr', escape='\\'), "mytable.myid LIKE :mytable_myid_1 ESCAPE '\\'", None),
            (~table1.c.myid.like('somstr', escape='\\'), "mytable.myid NOT LIKE :mytable_myid_1 ESCAPE '\\'", None),
            (table1.c.myid.ilike('somstr', escape='\\'), "lower(mytable.myid) LIKE lower(:mytable_myid_1) ESCAPE '\\'", None),
            (~table1.c.myid.ilike('somstr', escape='\\'), "lower(mytable.myid) NOT LIKE lower(:mytable_myid_1) ESCAPE '\\'", None),
            (table1.c.myid.ilike('somstr', escape='\\'), "mytable.myid ILIKE %(mytable_myid_1)s ESCAPE '\\'", postgres.PGDialect()),
            (~table1.c.myid.ilike('somstr', escape='\\'), "mytable.myid NOT ILIKE %(mytable_myid_1)s ESCAPE '\\'", postgres.PGDialect()),
            (table1.c.name.ilike('%something%'), "lower(mytable.name) LIKE lower(:mytable_name_1)", None),
            (table1.c.name.ilike('%something%'), "mytable.name ILIKE %(mytable_name_1)s", postgres.PGDialect()),
            (~table1.c.name.ilike('%something%'), "lower(mytable.name) NOT LIKE lower(:mytable_name_1)", None),
            (~table1.c.name.ilike('%something%'), "mytable.name NOT ILIKE %(mytable_name_1)s", postgres.PGDialect()),
        ]:
            self.assert_compile(expr, check, dialect=dialect)
        
    def test_composed_string_comparators(self):
        self.assert_compile(
            table1.c.name.contains('jo'), "mytable.name LIKE '%%' || :mytable_name_1 || '%%'" , checkparams = {'mytable_name_1': u'jo'},
        )
        self.assert_compile(
            table1.c.name.contains('jo'), "mytable.name LIKE concat(concat('%%', %s), '%%')" , checkparams = {'mytable_name_1': u'jo'},
            dialect=mysql.dialect()
        )
        self.assert_compile(
            table1.c.name.contains('jo', escape='\\'), "mytable.name LIKE '%%' || :mytable_name_1 || '%%' ESCAPE '\\'" , checkparams = {'mytable_name_1': u'jo'},
        )
        self.assert_compile( table1.c.name.startswith('jo', escape='\\'), "mytable.name LIKE :mytable_name_1 || '%%' ESCAPE '\\'" )
        self.assert_compile( table1.c.name.endswith('jo', escape='\\'), "mytable.name LIKE '%%' || :mytable_name_1 ESCAPE '\\'" )
        self.assert_compile( table1.c.name.endswith('hn'), "mytable.name LIKE '%%' || :mytable_name_1", checkparams = {'mytable_name_1': u'hn'}, )
        self.assert_compile(
            table1.c.name.endswith('hn'), "mytable.name LIKE concat('%%', %s)",
            checkparams = {'mytable_name_1': u'hn'}, dialect=mysql.dialect()
        )
        self.assert_compile(
            table1.c.name.startswith(u"hi \xf6 \xf5"), "mytable.name LIKE :mytable_name_1 || '%%'",
            checkparams = {'mytable_name_1': u'hi \xf6 \xf5'},
        )
        self.assert_compile(column('name').endswith(text("'foo'")), "name LIKE '%%' || 'foo'"  )
        self.assert_compile(column('name').endswith(literal_column("'foo'")), "name LIKE '%%' || 'foo'"  )
        self.assert_compile(column('name').startswith(text("'foo'")), "name LIKE 'foo' || '%%'"  )
        self.assert_compile(column('name').startswith(text("'foo'")), "name LIKE concat('foo', '%%')", dialect=mysql.dialect())
        self.assert_compile(column('name').startswith(literal_column("'foo'")), "name LIKE 'foo' || '%%'"  )
        self.assert_compile(column('name').startswith(literal_column("'foo'")), "name LIKE concat('foo', '%%')", dialect=mysql.dialect())

    def test_multiple_col_binds(self):
        self.assert_compile(
            select(["*"], or_(table1.c.myid == 12, table1.c.myid=='asdf', table1.c.myid == 'foo')),
            "SELECT * FROM mytable WHERE mytable.myid = :mytable_myid_1 OR mytable.myid = :mytable_myid_2 OR mytable.myid = :mytable_myid_3"
        )

    def test_orderby_groupby(self):
        self.assert_compile(
            table2.select(order_by = [table2.c.otherid, asc(table2.c.othername)]),
            "SELECT myothertable.otherid, myothertable.othername FROM myothertable ORDER BY myothertable.otherid, myothertable.othername ASC"
        )

        self.assert_compile(
            table2.select(order_by = [table2.c.otherid, table2.c.othername.desc()]),
            "SELECT myothertable.otherid, myothertable.othername FROM myothertable ORDER BY myothertable.otherid, myothertable.othername DESC"
        )

        # generative order_by
        self.assert_compile(
            table2.select().order_by(table2.c.otherid).order_by(table2.c.othername.desc()),
            "SELECT myothertable.otherid, myothertable.othername FROM myothertable ORDER BY myothertable.otherid, myothertable.othername DESC"
        )

        self.assert_compile(
            table2.select().order_by(table2.c.otherid).order_by(table2.c.othername.desc()).order_by(None),
            "SELECT myothertable.otherid, myothertable.othername FROM myothertable"
        )

        self.assert_compile(
            select([table2.c.othername, func.count(table2.c.otherid)], group_by = [table2.c.othername]),
            "SELECT myothertable.othername, count(myothertable.otherid) AS count_1 FROM myothertable GROUP BY myothertable.othername"
        )

        # generative group by
        self.assert_compile(
            select([table2.c.othername, func.count(table2.c.otherid)]).group_by(table2.c.othername),
            "SELECT myothertable.othername, count(myothertable.otherid) AS count_1 FROM myothertable GROUP BY myothertable.othername"
        )

        self.assert_compile(
            select([table2.c.othername, func.count(table2.c.otherid)]).group_by(table2.c.othername).group_by(None),
            "SELECT myothertable.othername, count(myothertable.otherid) AS count_1 FROM myothertable"
        )

        self.assert_compile(
            select([table2.c.othername, func.count(table2.c.otherid)], group_by = [table2.c.othername], order_by = [table2.c.othername]),
            "SELECT myothertable.othername, count(myothertable.otherid) AS count_1 FROM myothertable GROUP BY myothertable.othername ORDER BY myothertable.othername"
        )

    def test_for_update(self):
        self.assert_compile(table1.select(table1.c.myid==7, for_update=True), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid_1 FOR UPDATE")

        self.assert_compile(table1.select(table1.c.myid==7, for_update="nowait"), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid_1 FOR UPDATE")

        self.assert_compile(table1.select(table1.c.myid==7, for_update="nowait"), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid_1 FOR UPDATE NOWAIT", dialect=oracle.dialect())

        self.assert_compile(table1.select(table1.c.myid==7, for_update="read"), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = %s LOCK IN SHARE MODE", dialect=mysql.dialect())

        self.assert_compile(table1.select(table1.c.myid==7, for_update=True), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = %s FOR UPDATE", dialect=mysql.dialect())

        self.assert_compile(table1.select(table1.c.myid==7, for_update=True), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid_1 FOR UPDATE", dialect=oracle.dialect())

    def test_alias(self):
        # test the alias for a table1.  column names stay the same, table name "changes" to "foo".
        self.assert_compile(
            select([table1.alias('foo')])
            ,"SELECT foo.myid, foo.name, foo.description FROM mytable AS foo")

        for dialect in (firebird.dialect(), oracle.dialect()):
            self.assert_compile(
                select([table1.alias('foo')])
                ,"SELECT foo.myid, foo.name, foo.description FROM mytable foo"
                ,dialect=dialect)

        self.assert_compile(
            select([table1.alias()])
            ,"SELECT mytable_1.myid, mytable_1.name, mytable_1.description FROM mytable AS mytable_1")

        # create a select for a join of two tables.  use_labels means the column names will have
        # labels tablename_columnname, which become the column keys accessible off the Selectable object.
        # also, only use one column from the second table and all columns from the first table1.
        q = select([table1, table2.c.otherid], table1.c.myid == table2.c.otherid, use_labels = True)

        # make an alias of the "selectable".  column names stay the same (i.e. the labels), table name "changes" to "t2view".
        a = alias(q, 't2view')

        # select from that alias, also using labels.  two levels of labels should produce two underscores.
        # also, reference the column "mytable_myid" off of the t2view alias.
        self.assert_compile(
            a.select(a.c.mytable_myid == 9, use_labels = True),
            "SELECT t2view.mytable_myid AS t2view_mytable_myid, t2view.mytable_name AS t2view_mytable_name, \
t2view.mytable_description AS t2view_mytable_description, t2view.myothertable_otherid AS t2view_myothertable_otherid FROM \
(SELECT mytable.myid AS mytable_myid, mytable.name AS mytable_name, mytable.description AS mytable_description, \
myothertable.otherid AS myothertable_otherid FROM mytable, myothertable \
WHERE mytable.myid = myothertable.otherid) AS t2view WHERE t2view.mytable_myid = :t2view_mytable_myid_1"
        )


    def test_prefixes(self):
        self.assert_compile(table1.select().prefix_with("SQL_CALC_FOUND_ROWS").prefix_with("SQL_SOME_WEIRD_MYSQL_THING"),
            "SELECT SQL_CALC_FOUND_ROWS SQL_SOME_WEIRD_MYSQL_THING mytable.myid, mytable.name, mytable.description FROM mytable"
        )

    def test_text(self):
        self.assert_compile(
            text("select * from foo where lala = bar") ,
            "select * from foo where lala = bar"
        )

        # test bytestring
        self.assert_compile(select(
            ["foobar(a)", "pk_foo_bar(syslaal)"],
            "a = 12",
            from_obj = ["foobar left outer join lala on foobar.foo = lala.foo"]
        ),
        "SELECT foobar(a), pk_foo_bar(syslaal) FROM foobar left outer join lala on foobar.foo = lala.foo WHERE a = 12")

        # test unicode
        self.assert_compile(select(
            [u"foobar(a)", u"pk_foo_bar(syslaal)"],
            u"a = 12",
            from_obj = [u"foobar left outer join lala on foobar.foo = lala.foo"]
        ),
        u"SELECT foobar(a), pk_foo_bar(syslaal) FROM foobar left outer join lala on foobar.foo = lala.foo WHERE a = 12")

        # test building a select query programmatically with text
        s = select()
        s.append_column("column1")
        s.append_column("column2")
        s.append_whereclause("column1=12")
        s.append_whereclause("column2=19")
        s = s.order_by("column1")
        s.append_from("table1")
        self.assert_compile(s, "SELECT column1, column2 FROM table1 WHERE column1=12 AND column2=19 ORDER BY column1")

        self.assert_compile(
            select(["column1", "column2"], from_obj=table1).alias('somealias').select(),
            "SELECT somealias.column1, somealias.column2 FROM (SELECT column1, column2 FROM mytable) AS somealias"
        )

        # test that use_labels doesnt interfere with literal columns
        self.assert_compile(
            select(["column1", "column2", table1.c.myid], from_obj=table1, use_labels=True),
            "SELECT column1, column2, mytable.myid AS mytable_myid FROM mytable"
        )

        # test that use_labels doesnt interfere with literal columns that have textual labels
        self.assert_compile(
            select(["column1 AS foobar", "column2 AS hoho", table1.c.myid], from_obj=table1, use_labels=True),
            "SELECT column1 AS foobar, column2 AS hoho, mytable.myid AS mytable_myid FROM mytable"
        )

        print "---------------------------------------------"
        s1 = select(["column1 AS foobar", "column2 AS hoho", table1.c.myid], from_obj=[table1])
        print "---------------------------------------------"
        # test that "auto-labeling of subquery columns" doesnt interfere with literal columns,
        # exported columns dont get quoted
        self.assert_compile(
            select(["column1 AS foobar", "column2 AS hoho", table1.c.myid], from_obj=[table1]).select(),
            "SELECT column1 AS foobar, column2 AS hoho, myid FROM (SELECT column1 AS foobar, column2 AS hoho, mytable.myid AS myid FROM mytable)"
        )
        
        self.assert_compile(
            select(['col1','col2'], from_obj='tablename').alias('myalias'),
            "SELECT col1, col2 FROM tablename"
        )

    def test_binds_in_text(self):
        self.assert_compile(
            text("select * from foo where lala=:bar and hoho=:whee", bindparams=[bindparam('bar', 4), bindparam('whee', 7)]),
                "select * from foo where lala=:bar and hoho=:whee",
                checkparams={'bar':4, 'whee': 7},
        )

        self.assert_compile(
            text("select * from foo where clock='05:06:07'"),
                "select * from foo where clock='05:06:07'",
                checkparams={},
                params={},
        )

        dialect = postgres.dialect()
        self.assert_compile(
            text("select * from foo where lala=:bar and hoho=:whee", bindparams=[bindparam('bar',4), bindparam('whee',7)]),
                "select * from foo where lala=%(bar)s and hoho=%(whee)s",
                checkparams={'bar':4, 'whee': 7},
                dialect=dialect
        )
        self.assert_compile(
            text("select * from foo where clock='05:06:07' and mork='\:mindy'"),
            "select * from foo where clock='05:06:07' and mork=':mindy'",
            checkparams={},
            params={},
            dialect=dialect
        )

        dialect = sqlite.dialect()
        self.assert_compile(
            text("select * from foo where lala=:bar and hoho=:whee", bindparams=[bindparam('bar',4), bindparam('whee',7)]),
                "select * from foo where lala=? and hoho=?",
                checkparams={'bar':4, 'whee':7},
                dialect=dialect
        )

        self.assert_compile(select(
            [table1, table2.c.otherid, "sysdate()", "foo, bar, lala"],
            and_(
                "foo.id = foofoo(lala)",
                "datetime(foo) = Today",
                table1.c.myid == table2.c.otherid,
            )
        ),
        "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, sysdate(), foo, bar, lala \
FROM mytable, myothertable WHERE foo.id = foofoo(lala) AND datetime(foo) = Today AND mytable.myid = myothertable.otherid")

        self.assert_compile(select(
            [alias(table1, 't'), "foo.f"],
            "foo.f = t.id",
            from_obj = ["(select f from bar where lala=heyhey) foo"]
        ),
        "SELECT t.myid, t.name, t.description, foo.f FROM mytable AS t, (select f from bar where lala=heyhey) foo WHERE foo.f = t.id")

    def test_literal(self):
        self.assert_compile(select([literal("foo") + literal("bar")], from_obj=[table1]),
            "SELECT :param_1 || :param_2 AS anon_1 FROM mytable")

    def test_calculated_columns(self):
         value_tbl = table('values',
             column('id', Integer),
             column('val1', Float),
             column('val2', Float),
         )

         self.assert_compile(
             select([value_tbl.c.id, (value_tbl.c.val2 -
     value_tbl.c.val1)/value_tbl.c.val1]),
             "SELECT values.id, (values.val2 - values.val1) / values.val1 AS anon_1 FROM values"
         )

         self.assert_compile(
             select([value_tbl.c.id], (value_tbl.c.val2 -
     value_tbl.c.val1)/value_tbl.c.val1 > 2.0),
             "SELECT values.id FROM values WHERE (values.val2 - values.val1) / values.val1 > :param_1"
         )

         self.assert_compile(
             select([value_tbl.c.id], value_tbl.c.val1 / (value_tbl.c.val2 - value_tbl.c.val1) /value_tbl.c.val1 > 2.0),
             "SELECT values.id FROM values WHERE values.val1 / (values.val2 - values.val1) / values.val1 > :param_1"
         )

    def test_extract(self):
        """test the EXTRACT function"""
        self.assert_compile(select([extract("month", table3.c.otherstuff)]), "SELECT extract(month FROM thirdtable.otherstuff) AS extract_1 FROM thirdtable")

        self.assert_compile(select([extract("day", func.to_date("03/20/2005", "MM/DD/YYYY"))]), "SELECT extract(day FROM to_date(:to_date_1, :to_date_2)) AS extract_1")

    def test_joins(self):
        self.assert_compile(
            join(table2, table1, table1.c.myid == table2.c.otherid).select(),
            "SELECT myothertable.otherid, myothertable.othername, mytable.myid, mytable.name, \
mytable.description FROM myothertable JOIN mytable ON mytable.myid = myothertable.otherid"
        )

        self.assert_compile(
            select(
             [table1],
                from_obj = [join(table1, table2, table1.c.myid == table2.c.otherid)]
            ),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable JOIN myothertable ON mytable.myid = myothertable.otherid")

        self.assert_compile(
            select(
                [join(join(table1, table2, table1.c.myid == table2.c.otherid), table3, table1.c.myid == table3.c.userid)
            ]),
            "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername, thirdtable.userid, thirdtable.otherstuff FROM mytable JOIN myothertable ON mytable.myid = myothertable.otherid JOIN thirdtable ON mytable.myid = thirdtable.userid"
        )

        self.assert_compile(
            join(users, addresses, users.c.user_id==addresses.c.user_id).select(),
            "SELECT users.user_id, users.user_name, users.password, addresses.address_id, addresses.user_id, addresses.street, addresses.city, addresses.state, addresses.zip FROM users JOIN addresses ON users.user_id = addresses.user_id"
        )

        self.assert_compile(
                select([table1, table2, table3],

                from_obj = [join(table1, table2, table1.c.myid == table2.c.otherid).outerjoin(table3, table1.c.myid==table3.c.userid)]

                #from_obj = [outerjoin(join(table, table2, table1.c.myid == table2.c.otherid), table3, table1.c.myid==table3.c.userid)]
                )
                ,"SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername, thirdtable.userid, thirdtable.otherstuff FROM mytable JOIN myothertable ON mytable.myid = myothertable.otherid LEFT OUTER JOIN thirdtable ON mytable.myid = thirdtable.userid"
            )
        self.assert_compile(
                select([table1, table2, table3],
                from_obj = [outerjoin(table1, join(table2, table3, table2.c.otherid == table3.c.userid), table1.c.myid==table2.c.otherid)]
                )
                ,"SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername, thirdtable.userid, thirdtable.otherstuff FROM mytable LEFT OUTER JOIN (myothertable JOIN thirdtable ON myothertable.otherid = thirdtable.userid) ON mytable.myid = myothertable.otherid"
            )

        query = select(
                [table1, table2],
                or_(
                    table1.c.name == 'fred',
                    table1.c.myid == 10,
                    table2.c.othername != 'jack',
                    "EXISTS (select yay from foo where boo = lar)"
                ),
                from_obj = [ outerjoin(table1, table2, table1.c.myid == table2.c.otherid) ]
                )
        self.assert_compile(query,
            "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername \
FROM mytable LEFT OUTER JOIN myothertable ON mytable.myid = myothertable.otherid \
WHERE mytable.name = :mytable_name_1 OR mytable.myid = :mytable_myid_1 OR \
myothertable.othername != :myothertable_othername_1 OR \
EXISTS (select yay from foo where boo = lar)",
            )

    def test_compound_selects(self):
        try:
            union(table3.select(), table1.select())
        except exceptions.ArgumentError, err:
            assert str(err) == "All selectables passed to CompoundSelect must have identical numbers of columns; select #1 has 2 columns, select #2 has 3"
    
        x = union(
              select([table1], table1.c.myid == 5),
              select([table1], table1.c.myid == 12),
              order_by = [table1.c.myid],
        )

        self.assert_compile(x, "SELECT mytable.myid, mytable.name, mytable.description \
FROM mytable WHERE mytable.myid = :mytable_myid_1 UNION \
SELECT mytable.myid, mytable.name, mytable.description \
FROM mytable WHERE mytable.myid = :mytable_myid_2 ORDER BY mytable.myid")

        u1 = union(
            select([table1.c.myid, table1.c.name]),
            select([table2]),
            select([table3])
        )
        self.assert_compile(u1,
        "SELECT mytable.myid, mytable.name \
FROM mytable UNION SELECT myothertable.otherid, myothertable.othername \
FROM myothertable UNION SELECT thirdtable.userid, thirdtable.otherstuff FROM thirdtable")

        assert u1.corresponding_column(table2.c.otherid) is u1.c.myid

        # TODO - why is there an extra space before the LIMIT ?
        self.assert_compile(
            union(
                select([table1.c.myid, table1.c.name]),
                select([table2]),
                order_by=['myid'],
                offset=10,
                limit=5
            )
        ,    "SELECT mytable.myid, mytable.name \
FROM mytable UNION SELECT myothertable.otherid, myothertable.othername \
FROM myothertable ORDER BY myid  LIMIT 5 OFFSET 10"
        )

        self.assert_compile(
            union(
                select([table1.c.myid, table1.c.name, func.max(table1.c.description)], table1.c.name=='name2', group_by=[table1.c.myid, table1.c.name]),
                table1.select(table1.c.name=='name1')
            )
            ,
            "SELECT mytable.myid, mytable.name, max(mytable.description) AS max_1 FROM mytable \
WHERE mytable.name = :mytable_name_1 GROUP BY mytable.myid, mytable.name UNION SELECT mytable.myid, mytable.name, mytable.description \
FROM mytable WHERE mytable.name = :mytable_name_2"
        )

        self.assert_compile(
            union(
                select([literal(100).label('value')]),
                select([literal(200).label('value')])
                ),
                "SELECT :param_1 AS value UNION SELECT :param_2 AS value"
        )

        self.assert_compile(
            union_all(
                select([table1.c.myid]),
                union(
                    select([table2.c.otherid]),
                    select([table3.c.userid]),
                )
            )
            ,
            "SELECT mytable.myid FROM mytable UNION ALL (SELECT myothertable.otherid FROM myothertable UNION \
SELECT thirdtable.userid FROM thirdtable)"
        )
        # This doesn't need grouping, so don't group to not give sqlite unnecessarily hard time
        self.assert_compile(
            union(
                except_(
                    select([table2.c.otherid]),
                    select([table3.c.userid]),
                ),
                select([table1.c.myid])
            )
            ,
            "SELECT myothertable.otherid FROM myothertable EXCEPT SELECT thirdtable.userid FROM thirdtable \
UNION SELECT mytable.myid FROM mytable"
        )

    @testing.uses_deprecated('//get_params')
    def test_binds(self):
        for (
             stmt,
             expected_named_stmt,
             expected_positional_stmt,
             expected_default_params_dict,
             expected_default_params_list,
             test_param_dict,
             expected_test_params_dict,
             expected_test_params_list
             ) in [
              (
                  select(
                      [table1, table2],
                     and_(
                         table1.c.myid == table2.c.otherid,
                         table1.c.name == bindparam('mytablename')
                     )),
                     """SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername FROM mytable, myothertable WHERE mytable.myid = myothertable.otherid AND mytable.name = :mytablename""",
                     """SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername FROM mytable, myothertable WHERE mytable.myid = myothertable.otherid AND mytable.name = ?""",
                 {'mytablename':None}, [None],
                 {'mytablename':5}, {'mytablename':5}, [5]
             ),
             (
                 select([table1], or_(table1.c.myid==bindparam('myid'), table2.c.otherid==bindparam('myid'))),
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = :myid OR myothertable.otherid = :myid",
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = ? OR myothertable.otherid = ?",
                 {'myid':None}, [None, None],
                 {'myid':5}, {'myid':5}, [5,5]
             ),
             (
                 text("SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = :myid OR myothertable.otherid = :myid"),
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = :myid OR myothertable.otherid = :myid",
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = ? OR myothertable.otherid = ?",
                 {'myid':None}, [None, None],
                 {'myid':5}, {'myid':5}, [5,5]
             ),
             (
                 select([table1], or_(table1.c.myid==bindparam('myid', unique=True), table2.c.otherid==bindparam('myid', unique=True))),
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = :myid_1 OR myothertable.otherid = :myid_2",
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = ? OR myothertable.otherid = ?",
                 {'myid_1':None, 'myid_2':None}, [None, None],
                 {'myid_1':5, 'myid_2': 6}, {'myid_1':5, 'myid_2':6}, [5,6]
             ),
             (
                bindparam('test', type_=String) + text("'hi'"),
                ":test || 'hi'",
                "? || 'hi'",
                {'test':None}, [None],
                {}, {'test':None}, [None]
             ),
             (
                 select([table1], or_(table1.c.myid==bindparam('myid'), table2.c.otherid==bindparam('myotherid'))).params({'myid':8, 'myotherid':7}),
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = :myid OR myothertable.otherid = :myotherid",
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = ? OR myothertable.otherid = ?",
                 {'myid':8, 'myotherid':7}, [8, 7],
                 {'myid':5}, {'myid':5, 'myotherid':7}, [5,7]
             ),
             (
                 select([table1], or_(table1.c.myid==bindparam('myid', value=7, unique=True), table2.c.otherid==bindparam('myid', value=8, unique=True))),
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = :myid_1 OR myothertable.otherid = :myid_2",
                 "SELECT mytable.myid, mytable.name, mytable.description FROM mytable, myothertable WHERE mytable.myid = ? OR myothertable.otherid = ?",
                 {'myid_1':7, 'myid_2':8}, [7,8],
                 {'myid_1':5, 'myid_2':6}, {'myid_1':5, 'myid_2':6}, [5,6]
             ),
             ]:

                self.assert_compile(stmt, expected_named_stmt, params=expected_default_params_dict)
                self.assert_compile(stmt, expected_positional_stmt, dialect=sqlite.dialect())
                nonpositional = stmt.compile()
                positional = stmt.compile(dialect=sqlite.dialect())
                pp = positional.get_params()
                assert [pp[k] for k in positional.positiontup] == expected_default_params_list
                assert nonpositional.get_params(**test_param_dict) == expected_test_params_dict, "expected :%s got %s" % (str(expected_test_params_dict), str(nonpositional.get_params(**test_param_dict)))
                pp = positional.get_params(**test_param_dict)
                assert [pp[k] for k in positional.positiontup] == expected_test_params_list

        # check that params() doesnt modify original statement
        s = select([table1], or_(table1.c.myid==bindparam('myid'), table2.c.otherid==bindparam('myotherid')))
        s2 = s.params({'myid':8, 'myotherid':7})
        s3 = s2.params({'myid':9})
        assert s.compile().params == {'myid':None, 'myotherid':None}
        assert s2.compile().params == {'myid':8, 'myotherid':7}
        assert s3.compile().params == {'myid':9, 'myotherid':7}

        # test using same 'unique' param object twice in one compile
        s = select([table1.c.myid]).where(table1.c.myid==12).as_scalar()
        s2 = select([table1, s], table1.c.myid==s)
        self.assert_compile(s2,
            "SELECT mytable.myid, mytable.name, mytable.description, (SELECT mytable.myid FROM mytable WHERE mytable.myid = "\
            ":mytable_myid_1) AS anon_1 FROM mytable WHERE mytable.myid = (SELECT mytable.myid FROM mytable WHERE mytable.myid = :mytable_myid_1)")
        positional = s2.compile(dialect=sqlite.dialect())

        pp = positional.get_params()
        assert [pp[k] for k in positional.positiontup] == [12, 12]

        # check that conflicts with "unique" params are caught
        s = select([table1], or_(table1.c.myid==7, table1.c.myid==bindparam('mytable_myid_1')))
        try:
            print str(s)
            assert False
        except exceptions.CompileError, err:
            assert str(err) == "Bind parameter 'mytable_myid_1' conflicts with unique bind parameter of the same name"

        s = select([table1], or_(table1.c.myid==7, table1.c.myid==8, table1.c.myid==bindparam('mytable_myid_1')))
        try:
            str(s)
            assert False
        except exceptions.CompileError, err:
            assert str(err) == "Bind parameter 'mytable_myid_1' conflicts with unique bind parameter of the same name"

    def test_bind_as_col(self):
        t = table('foo', column('id'))

        s = select([t, literal('lala').label('hoho')])
        self.assert_compile(s, "SELECT foo.id, :param_1 AS hoho FROM foo")
        assert [str(c) for c in s.c] == ["id", "hoho"]

    def test_in(self):
        self.assert_compile(select([table1], table1.c.myid.in_(['a'])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1)")

        self.assert_compile(select([table1], ~table1.c.myid.in_(['a'])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid NOT IN (:mytable_myid_1)")

        self.assert_compile(select([table1], table1.c.myid.in_(['a', 'b'])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1, :mytable_myid_2)")

        self.assert_compile(select([table1], table1.c.myid.in_(iter(['a', 'b']))),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1, :mytable_myid_2)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal('a')])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal('a'), 'b'])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1, :mytable_myid_1)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal('a'), literal('b')])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1, :param_2)")

        self.assert_compile(select([table1], table1.c.myid.in_(['a', literal('b')])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1, :param_1)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal(1) + 'a'])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1 + :param_2)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal('a') +'a', 'b'])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1 || :param_2, :mytable_myid_1)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal('a') + literal('a'), literal('b')])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1 || :param_2, :param_3)")

        self.assert_compile(select([table1], table1.c.myid.in_([1, literal(3) + 4])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1, :param_1 + :param_2)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal('a') < 'b'])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1 < :param_2)")

        self.assert_compile(select([table1], table1.c.myid.in_([table1.c.myid])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (mytable.myid)")

        self.assert_compile(select([table1], table1.c.myid.in_(['a', table1.c.myid])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1, mytable.myid)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal('a'), table1.c.myid])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1, mytable.myid)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal('a'), table1.c.myid +'a'])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1, mytable.myid + :mytable_myid_1)")

        self.assert_compile(select([table1], table1.c.myid.in_([literal(1), 'a' + table1.c.myid])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:param_1, :mytable_myid_1 + mytable.myid)")

        self.assert_compile(select([table1], table1.c.myid.in_([1, 2, 3])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1, :mytable_myid_2, :mytable_myid_3)")

        self.assert_compile(select([table1], table1.c.myid.in_(select([table2.c.otherid]))),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (SELECT myothertable.otherid FROM myothertable)")

        self.assert_compile(select([table1], ~table1.c.myid.in_(select([table2.c.otherid]))),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid NOT IN (SELECT myothertable.otherid FROM myothertable)")

        self.assert_compile(select([table1], table1.c.myid.in_(
            union(
                  select([table1], table1.c.myid == 5),
                  select([table1], table1.c.myid == 12),
            )
        )), "SELECT mytable.myid, mytable.name, mytable.description FROM mytable \
WHERE mytable.myid IN (\
SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid_1 \
UNION SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid = :mytable_myid_2)")

        # test that putting a select in an IN clause does not blow away its ORDER BY clause
        self.assert_compile(
            select([table1, table2],
                table2.c.otherid.in_(
                    select([table2.c.otherid], order_by=[table2.c.othername], limit=10, correlate=False)
                ),
                from_obj=[table1.join(table2, table1.c.myid==table2.c.otherid)], order_by=[table1.c.myid]
            ),
            "SELECT mytable.myid, mytable.name, mytable.description, myothertable.otherid, myothertable.othername FROM mytable "\
            "JOIN myothertable ON mytable.myid = myothertable.otherid WHERE myothertable.otherid IN (SELECT myothertable.otherid "\
            "FROM myothertable ORDER BY myothertable.othername  LIMIT 10) ORDER BY mytable.myid"
        )

        # test empty in clause
        self.assert_compile(select([table1], table1.c.myid.in_([])),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE (CASE WHEN (mytable.myid IS NULL) THEN NULL ELSE 0 END = 1)")

    @testing.uses_deprecated('passing in_')
    def test_in_deprecated_api(self):
        self.assert_compile(select([table1], table1.c.myid.in_('abc')),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1)")

        self.assert_compile(select([table1], table1.c.myid.in_(1)),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1)")

        self.assert_compile(select([table1], table1.c.myid.in_(1,2)),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE mytable.myid IN (:mytable_myid_1, :mytable_myid_2)")

        self.assert_compile(select([table1], table1.c.myid.in_()),
        "SELECT mytable.myid, mytable.name, mytable.description FROM mytable WHERE (CASE WHEN (mytable.myid IS NULL) THEN NULL ELSE 0 END = 1)")

    def test_cast(self):
        tbl = table('casttest',
                    column('id', Integer),
                    column('v1', Float),
                    column('v2', Float),
                    column('ts', TIMESTAMP),
                    )

        def check_results(dialect, expected_results, literal):
            self.assertEqual(len(expected_results), 5, 'Incorrect number of expected results')
            self.assertEqual(str(cast(tbl.c.v1, Numeric).compile(dialect=dialect)), 'CAST(casttest.v1 AS %s)' %expected_results[0])
            self.assertEqual(str(cast(tbl.c.v1, Numeric(12, 9)).compile(dialect=dialect)), 'CAST(casttest.v1 AS %s)' %expected_results[1])
            self.assertEqual(str(cast(tbl.c.ts, Date).compile(dialect=dialect)), 'CAST(casttest.ts AS %s)' %expected_results[2])
            self.assertEqual(str(cast(1234, TEXT).compile(dialect=dialect)), 'CAST(%s AS %s)' %(literal, expected_results[3]))
            self.assertEqual(str(cast('test', String(20)).compile(dialect=dialect)), 'CAST(%s AS %s)' %(literal, expected_results[4]))
            # fixme: shoving all of this dialect-specific stuff in one test
            # is now officialy completely ridiculous AND non-obviously omits
            # coverage on other dialects.
            sel = select([tbl, cast(tbl.c.v1, Numeric)]).compile(dialect=dialect)
            if isinstance(dialect, type(mysql.dialect())):
                self.assertEqual(str(sel), "SELECT casttest.id, casttest.v1, casttest.v2, casttest.ts, CAST(casttest.v1 AS DECIMAL(10, 2)) AS anon_1 \nFROM casttest")
            else:
                self.assertEqual(str(sel), "SELECT casttest.id, casttest.v1, casttest.v2, casttest.ts, CAST(casttest.v1 AS NUMERIC(10, 2)) AS anon_1 \nFROM casttest")

        # first test with Postgres engine
        check_results(postgres.dialect(), ['NUMERIC(10, 2)', 'NUMERIC(12, 9)', 'DATE', 'TEXT', 'VARCHAR(20)'], '%(param_1)s')

        # then the Oracle engine
        check_results(oracle.dialect(), ['NUMERIC(10, 2)', 'NUMERIC(12, 9)', 'DATE', 'CLOB', 'VARCHAR(20)'], ':param_1')

        # then the sqlite engine
        check_results(sqlite.dialect(), ['NUMERIC(10, 2)', 'NUMERIC(12, 9)', 'DATE', 'TEXT', 'VARCHAR(20)'], '?')

        # then the MySQL engine
        check_results(mysql.dialect(), ['DECIMAL(10, 2)', 'DECIMAL(12, 9)', 'DATE', 'CHAR', 'CHAR(20)'], '%s')

        self.assert_compile(cast(text('NULL'), Integer), "CAST(NULL AS INTEGER)", dialect=sqlite.dialect())
        self.assert_compile(cast(null(), Integer), "CAST(NULL AS INTEGER)", dialect=sqlite.dialect())
        self.assert_compile(cast(literal_column('NULL'), Integer), "CAST(NULL AS INTEGER)", dialect=sqlite.dialect())
        
    def test_date_between(self):
        import datetime
        table = Table('dt', metadata,
            Column('date', Date))
        self.assert_compile(table.select(table.c.date.between(datetime.date(2006,6,1), datetime.date(2006,6,5))),
            "SELECT dt.date FROM dt WHERE dt.date BETWEEN :dt_date_1 AND :dt_date_2", checkparams={'dt_date_1':datetime.date(2006,6,1), 'dt_date_2':datetime.date(2006,6,5)})

        self.assert_compile(table.select(sql.between(table.c.date, datetime.date(2006,6,1), datetime.date(2006,6,5))),
            "SELECT dt.date FROM dt WHERE dt.date BETWEEN :param_1 AND :param_2", checkparams={'param_1':datetime.date(2006,6,1), 'param_2':datetime.date(2006,6,5)})

    def test_operator_precedence(self):
        table = Table('op', metadata,
            Column('field', Integer))
        self.assert_compile(table.select((table.c.field == 5) == None),
            "SELECT op.field FROM op WHERE (op.field = :op_field_1) IS NULL")
        self.assert_compile(table.select((table.c.field + 5) == table.c.field),
            "SELECT op.field FROM op WHERE op.field + :op_field_1 = op.field")
        self.assert_compile(table.select((table.c.field + 5) * 6),
            "SELECT op.field FROM op WHERE (op.field + :op_field_1) * :param_1")
        self.assert_compile(table.select((table.c.field * 5) + 6),
            "SELECT op.field FROM op WHERE op.field * :op_field_1 + :param_1")
        self.assert_compile(table.select(5 + table.c.field.in_([5,6])),
            "SELECT op.field FROM op WHERE :param_1 + (op.field IN (:op_field_1, :op_field_2))")
        self.assert_compile(table.select((5 + table.c.field).in_([5,6])),
            "SELECT op.field FROM op WHERE :op_field_1 + op.field IN (:param_1, :param_2)")
        self.assert_compile(table.select(not_(and_(table.c.field == 5, table.c.field == 7))),
            "SELECT op.field FROM op WHERE NOT (op.field = :op_field_1 AND op.field = :op_field_2)")
        self.assert_compile(table.select(not_(table.c.field == 5)),
            "SELECT op.field FROM op WHERE op.field != :op_field_1")
        self.assert_compile(table.select(not_(table.c.field.between(5, 6))),
            "SELECT op.field FROM op WHERE NOT (op.field BETWEEN :op_field_1 AND :op_field_2)")
        self.assert_compile(table.select(not_(table.c.field) == 5),
            "SELECT op.field FROM op WHERE (NOT op.field) = :param_1")
        self.assert_compile(table.select((table.c.field == table.c.field).between(False, True)),
            "SELECT op.field FROM op WHERE (op.field = op.field) BETWEEN :param_1 AND :param_2")
        self.assert_compile(table.select(between((table.c.field == table.c.field), False, True)),
            "SELECT op.field FROM op WHERE (op.field = op.field) BETWEEN :param_1 AND :param_2")
    
    def test_naming(self):
        s1 = select([table1.c.myid, table1.c.myid.label('foobar'), func.hoho(table1.c.name), func.lala(table1.c.name).label('gg')])
        assert s1.c.keys() == ['myid', 'foobar', 'hoho(mytable.name)', 'gg']

        from sqlalchemy.databases.sqlite import SLNumeric
        meta = MetaData()
        t1 = Table('mytable', meta, Column('col1', Integer))
        
        for col, key, expr, label in (
            (table1.c.name, 'name', 'mytable.name', None),
            (table1.c.myid==12, 'mytable.myid = :mytable_myid_1', 'mytable.myid = :mytable_myid_1', 'anon_1'),
            (func.hoho(table1.c.myid), 'hoho(mytable.myid)', 'hoho(mytable.myid)', 'hoho_1'),
            (cast(table1.c.name, SLNumeric), 'CAST(mytable.name AS NUMERIC(10, 2))', 'CAST(mytable.name AS NUMERIC(10, 2))', 'anon_1'),
            (t1.c.col1, 'col1', 'mytable.col1', None),
            (column('some wacky thing'), 'some wacky thing', '"some wacky thing"', '')
        ):
            s1 = select([col], from_obj=getattr(col, 'table', None) or table1)
            assert s1.c.keys() == [key], s1.c.keys()
        
            if label:
                self.assert_compile(s1, "SELECT %s AS %s FROM mytable" % (expr, label))
            else:
                self.assert_compile(s1, "SELECT %s FROM mytable" % (expr,))
            
            s1 = select([s1])
            if label:
                self.assert_compile(s1, "SELECT %s FROM (SELECT %s AS %s FROM mytable)" % (label, expr, label))
            elif col.table is not None:
                # sqlite rule labels subquery columns
                self.assert_compile(s1, "SELECT %s FROM (SELECT %s AS %s FROM mytable)" % (key,expr, key))
            else:
                self.assert_compile(s1, "SELECT %s FROM (SELECT %s FROM mytable)" % (expr,expr))
                
class CRUDTest(TestBase, AssertsCompiledSQL):
    def test_insert(self):
        # generic insert, will create bind params for all columns
        self.assert_compile(insert(table1), "INSERT INTO mytable (myid, name, description) VALUES (:myid, :name, :description)")

        # insert with user-supplied bind params for specific columns,
        # cols provided literally
        self.assert_compile(
            insert(table1, {table1.c.myid : bindparam('userid'), table1.c.name : bindparam('username')}),
            "INSERT INTO mytable (myid, name) VALUES (:userid, :username)")

        # insert with user-supplied bind params for specific columns, cols
        # provided as strings
        self.assert_compile(
            insert(table1, dict(myid = 3, name = 'jack')),
            "INSERT INTO mytable (myid, name) VALUES (:myid, :name)"
        )

        # test with a tuple of params instead of named
        self.assert_compile(
            insert(table1, (3, 'jack', 'mydescription')),
            "INSERT INTO mytable (myid, name, description) VALUES (:myid, :name, :description)",
            checkparams = {'myid':3, 'name':'jack', 'description':'mydescription'}
        )

        self.assert_compile(
            insert(table1, values={table1.c.myid : bindparam('userid')}).values({table1.c.name : bindparam('username')}),
            "INSERT INTO mytable (myid, name) VALUES (:userid, :username)"
        )

        self.assert_compile(insert(table1, values=dict(myid=func.lala())), "INSERT INTO mytable (myid) VALUES (lala())")

    def test_inline_insert(self):
        metadata = MetaData()
        table = Table('sometable', metadata,
            Column('id', Integer, primary_key=True),
            Column('foo', Integer, default=func.foobar()))
        self.assert_compile(table.insert(values={}, inline=True), "INSERT INTO sometable (foo) VALUES (foobar())")
        self.assert_compile(table.insert(inline=True), "INSERT INTO sometable (foo) VALUES (foobar())", params={})

    def test_update(self):
        self.assert_compile(update(table1, table1.c.myid == 7), "UPDATE mytable SET name=:name WHERE mytable.myid = :mytable_myid_1", params = {table1.c.name:'fred'})
        self.assert_compile(table1.update().where(table1.c.myid==7).values({table1.c.myid:5}), "UPDATE mytable SET myid=:myid WHERE mytable.myid = :mytable_myid_1", checkparams={'myid':5, 'mytable_myid_1':7})
        self.assert_compile(update(table1, table1.c.myid == 7), "UPDATE mytable SET name=:name WHERE mytable.myid = :mytable_myid_1", params = {'name':'fred'})
        self.assert_compile(update(table1, values = {table1.c.name : table1.c.myid}), "UPDATE mytable SET name=mytable.myid")
        self.assert_compile(update(table1, whereclause = table1.c.name == bindparam('crit'), values = {table1.c.name : 'hi'}), "UPDATE mytable SET name=:name WHERE mytable.name = :crit", params = {'crit' : 'notthere'}, checkparams={'crit':'notthere', 'name':'hi'})
        self.assert_compile(update(table1, table1.c.myid == 12, values = {table1.c.name : table1.c.myid}), "UPDATE mytable SET name=mytable.myid, description=:description WHERE mytable.myid = :mytable_myid_1", params = {'description':'test'}, checkparams={'description':'test', 'mytable_myid_1':12})
        self.assert_compile(update(table1, table1.c.myid == 12, values = {table1.c.myid : 9}), "UPDATE mytable SET myid=:myid, description=:description WHERE mytable.myid = :mytable_myid_1", params = {'mytable_myid_1': 12, 'myid': 9, 'description': 'test'})
        self.assert_compile(update(table1, table1.c.myid ==12), "UPDATE mytable SET myid=:myid WHERE mytable.myid = :mytable_myid_1", params={'myid':18}, checkparams={'myid':18, 'mytable_myid_1':12})
        s = table1.update(table1.c.myid == 12, values = {table1.c.name : 'lala'})
        c = s.compile(column_keys=['mytable_id', 'name'])
        self.assert_compile(update(table1, table1.c.myid == 12, values = {table1.c.name : table1.c.myid}).values({table1.c.name:table1.c.name + 'foo'}), "UPDATE mytable SET name=(mytable.name || :mytable_name_1), description=:description WHERE mytable.myid = :mytable_myid_1", params = {'description':'test'})
        self.assert_(str(s) == str(c))

        self.assert_compile(update(table1,
            (table1.c.myid == func.hoho(4)) &
            (table1.c.name == literal('foo') + table1.c.name + literal('lala')),
            values = {
            table1.c.name : table1.c.name + "lala",
            table1.c.myid : func.do_stuff(table1.c.myid, literal('hoho'))
            }), "UPDATE mytable SET myid=do_stuff(mytable.myid, :param_1), name=(mytable.name || :mytable_name_1) "
            "WHERE mytable.myid = hoho(:hoho_1) AND mytable.name = :param_2 || mytable.name || :param_3")

    def test_correlated_update(self):
        # test against a straight text subquery
        u = update(table1, values = {table1.c.name : text("(select name from mytable where id=mytable.id)")})
        self.assert_compile(u, "UPDATE mytable SET name=(select name from mytable where id=mytable.id)")

        mt = table1.alias()
        u = update(table1, values = {table1.c.name : select([mt.c.name], mt.c.myid==table1.c.myid)})
        self.assert_compile(u, "UPDATE mytable SET name=(SELECT mytable_1.name FROM mytable AS mytable_1 WHERE mytable_1.myid = mytable.myid)")

        # test against a regular constructed subquery
        s = select([table2], table2.c.otherid == table1.c.myid)
        u = update(table1, table1.c.name == 'jack', values = {table1.c.name : s})
        self.assert_compile(u, "UPDATE mytable SET name=(SELECT myothertable.otherid, myothertable.othername FROM myothertable WHERE myothertable.otherid = mytable.myid) WHERE mytable.name = :mytable_name_1")

        # test a non-correlated WHERE clause
        s = select([table2.c.othername], table2.c.otherid == 7)
        u = update(table1, table1.c.name==s)
        self.assert_compile(u, "UPDATE mytable SET myid=:myid, name=:name, description=:description WHERE mytable.name = "\
            "(SELECT myothertable.othername FROM myothertable WHERE myothertable.otherid = :myothertable_otherid_1)")

        # test one that is actually correlated...
        s = select([table2.c.othername], table2.c.otherid == table1.c.myid)
        u = table1.update(table1.c.name==s)
        self.assert_compile(u, "UPDATE mytable SET myid=:myid, name=:name, description=:description WHERE mytable.name = "\
            "(SELECT myothertable.othername FROM myothertable WHERE myothertable.otherid = mytable.myid)")

    def test_delete(self):
        self.assert_compile(delete(table1, table1.c.myid == 7), "DELETE FROM mytable WHERE mytable.myid = :mytable_myid_1")
        self.assert_compile(table1.delete().where(table1.c.myid == 7), "DELETE FROM mytable WHERE mytable.myid = :mytable_myid_1")
        self.assert_compile(table1.delete().where(table1.c.myid == 7).where(table1.c.name=='somename'), "DELETE FROM mytable WHERE mytable.myid = :mytable_myid_1 AND mytable.name = :mytable_name_1")
        
    def test_correlated_delete(self):
        # test a non-correlated WHERE clause
        s = select([table2.c.othername], table2.c.otherid == 7)
        u = delete(table1, table1.c.name==s)
        self.assert_compile(u, "DELETE FROM mytable WHERE mytable.name = "\
        "(SELECT myothertable.othername FROM myothertable WHERE myothertable.otherid = :myothertable_otherid_1)")

        # test one that is actually correlated...
        s = select([table2.c.othername], table2.c.otherid == table1.c.myid)
        u = table1.delete(table1.c.name==s)
        self.assert_compile(u, "DELETE FROM mytable WHERE mytable.name = (SELECT myothertable.othername FROM myothertable WHERE myothertable.otherid = mytable.myid)")

class InlineDefaultTest(TestBase, AssertsCompiledSQL):
    def test_insert(self):
        m = MetaData()
        foo =  Table('foo', m,
            Column('id', Integer))

        t = Table('test', m,
            Column('col1', Integer, default=func.foo(1)),
            Column('col2', Integer, default=select([func.coalesce(func.max(foo.c.id))])),
            )

        self.assert_compile(t.insert(inline=True, values={}), "INSERT INTO test (col1, col2) VALUES (foo(:foo_1), (SELECT coalesce(max(foo.id)) AS coalesce_1 FROM foo))")

    def test_update(self):
        m = MetaData()
        foo =  Table('foo', m,
            Column('id', Integer))

        t = Table('test', m,
            Column('col1', Integer, onupdate=func.foo(1)),
            Column('col2', Integer, onupdate=select([func.coalesce(func.max(foo.c.id))])),
            Column('col3', String(30))
            )

        self.assert_compile(t.update(inline=True, values={'col3':'foo'}), "UPDATE test SET col1=foo(:foo_1), col2=(SELECT coalesce(max(foo.id)) AS coalesce_1 FROM foo), col3=:col3")

class SchemaTest(TestBase, AssertsCompiledSQL):
    @testing.fails_on('mssql')
    def test_select(self):
        # these tests will fail with the MS-SQL compiler since it will alias schema-qualified tables
        self.assert_compile(table4.select(), "SELECT remote_owner.remotetable.rem_id, remote_owner.remotetable.datatype_id, remote_owner.remotetable.value FROM remote_owner.remotetable")
        self.assert_compile(table4.select(and_(table4.c.datatype_id==7, table4.c.value=='hi')),
            "SELECT remote_owner.remotetable.rem_id, remote_owner.remotetable.datatype_id, remote_owner.remotetable.value FROM remote_owner.remotetable WHERE "\
            "remote_owner.remotetable.datatype_id = :remote_owner_remotetable_datatype_id_1 AND remote_owner.remotetable.value = :remote_owner_remotetable_value_1")

        s = table4.select(and_(table4.c.datatype_id==7, table4.c.value=='hi'))
        s.use_labels = True
        self.assert_compile(s, "SELECT remote_owner.remotetable.rem_id AS remote_owner_remotetable_rem_id, remote_owner.remotetable.datatype_id AS remote_owner_remotetable_datatype_id, remote_owner.remotetable.value "\
            "AS remote_owner_remotetable_value FROM remote_owner.remotetable WHERE "\
            "remote_owner.remotetable.datatype_id = :remote_owner_remotetable_datatype_id_1 AND remote_owner.remotetable.value = :remote_owner_remotetable_value_1")

    def test_alias(self):
        a = alias(table4, 'remtable')
        self.assert_compile(a.select(a.c.datatype_id==7), "SELECT remtable.rem_id, remtable.datatype_id, remtable.value FROM remote_owner.remotetable AS remtable "\
            "WHERE remtable.datatype_id = :remtable_datatype_id_1")

    def test_update(self):
        self.assert_compile(table4.update(table4.c.value=='test', values={table4.c.datatype_id:12}), "UPDATE remote_owner.remotetable SET datatype_id=:datatype_id "\
            "WHERE remote_owner.remotetable.value = :remote_owner_remotetable_value_1")

    def test_insert(self):
        self.assert_compile(table4.insert(values=(2, 5, 'test')), "INSERT INTO remote_owner.remotetable (rem_id, datatype_id, value) VALUES "\
            "(:rem_id, :datatype_id, :value)")

if __name__ == "__main__":
    testenv.main()
