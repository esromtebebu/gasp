import click
import psycopg2

from flask import current_app, g, abort


class DatabaseError(Exception):
    pass


def set_connection(fn):
    def wrapped(*args, **kwargs):
        if 'db' not in g:
            init_connection()
        return fn(g.db, *args, **kwargs)
    return wrapped


def abort_on_db_error(fn):
    """Decorator to catch DatabaseErrors and abort."""
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except DatabaseError:
            abort(500)
    return wrapped


@click.command('init-db')
@set_connection
def init_db(connection):
    with current_app.open_resource('sql/schema.sql') as f:
        cursor = connection.cursor()
        cursor.execute(f.read().decode('utf8'))
        connection.commit()


@set_connection
def execute_query(*args, commit_after_query=False, **kwargs):
    error = None
    try:
        connection, query, parameters = args[0], args[1], args[2:]
        cursor = connection.cursor()

        cursor.execute(query, parameters)
        if commit_after_query:
            commit()

        return cursor
    except MemoryError:
        error = "Not enough Memory to execute DB Query."
    except psycopg2.Error as e:
        if len(e.args) > 0:
            error = "DB error: {}".format(e.args[0])
        else:
            error = ("DB error: unidentified problem during the execution of the query.")
    except Exception as e:
        current_app.logger.error(error)
        current_app.logger.error(f"Query: {query} - {parameters}")
        raise e
    if error:
        current_app.logger.error(error)
        current_app.logger.error(f"Query: {query} - {parameters}")
        raise DatabaseError(error)


@set_connection
def commit(connection):
    try:
        connection.commit()
    except psycopg2.Error as e:
        error = "Query execution error: {}".format(e.args[0])
        current_app.logger.error(error)
        raise DatabaseError(error)


@set_connection
def rollback(connection):
    try:
        connection.rollback()
    except psycopg2.Error as e:
        error = "Query execution error: {}".format(e.args[0])
        current_app.logger.error(error)
        raise DatabaseError(error)


def init_connection():
    try:
        g.db = psycopg2.connect(dbname=current_app.config['DBNAME'],
                                user=current_app.config['DBUSER'],
                                password=current_app.config['DBPASSWORD'],
                                host=current_app.config['DBHOST'])
    except psycopg2.Error as e:
        error = "Database connexion error - {}".format(e.args[0])
        current_app.logger.error(error)
        close_connection()
        raise DatabaseError(error)


def close_connection(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_connection)
    app.cli.add_command(init_db)


#import psycopg2
#
#import click
#from flask import current_app, g
#
#
#class DatabaseError(Exception):
#    pass
#
#
#def init_connection():
#    try:
#        g.db = psycopg2.connect(dbname=current_app.config['DBNAME'],
#                                user=current_app.config['DBUSER'],
#                                password=current_app.config['DBPASSWORD'],
#                                host=current_app.config['DBHOST'])
#    except psycopg2.Error as e:
#        error = "Database connexion error - {}".format(e.args[0])
#        current_app.logger.error(error)
#        close_db()
#        raise DatabaseError(error)
#
#
#def get_db():
#    if 'db' not in g:
#        init_connection()
#
#    return g.db
#
#
#def close_db(e=None):
#    db = g.pop('db', None)
#
#    if db is not None:
#        db.close()
#
#
#def init_db():
#    db = get_db()
#
#    with current_app.open_resource('sql/schema.sql') as f:
#        cursor = db.cursor()
#        cursor.execute(f.read().decode('utf8'))
#        db.commit()
#
#
#@click.command('init-db')
#def init_db_command():
#    """Clear the existing data and create new tables."""
#    init_db()
#    click.echo('Initialized the database.')
#
#
#def init_app(app):
#    app.teardown_appcontext(close_db)
#    app.cli.add_command(init_db_command)
