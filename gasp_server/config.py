import os


class BaseConfig(object):
    DEBUG = False
    TESTING = False
    SOLVER = 'GLPK'
    CPLEX_PATH = '<complet path>'

class DevConfig(BaseConfig):
    DEBUG = True
    TESTING = True
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    DBNAME = 'gasp'
    DBUSER = 'gasp'
    DBPASSWORD = 'gasp.'
    DBHOST = 'localhost'

class ProdConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    LANGUAGES = ['en', 'fr']
    DBNAME = 'gasp'
    DBUSER = 'gasp'
    DBPASSWORD = 'gasp.'
    DBHOST = 'localhost'