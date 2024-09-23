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
    DBNAME = 'agape_wgzg'
    DBUSER = 'eftebebu'
    DBPASSWORD = 'xs5KGVeHNpQjQygRk2camXRKi7cSi7Xs'
    DBHOST = 'dpg-croilh9u0jms73c9mhhg-a.frankfurt-postgres.render.com'

class ProdConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    LANGUAGES = ['en', 'fr']
    DBNAME = 'agape_wgzg'
    DBUSER = 'eftebebu'
    DBPASSWORD = 'xs5KGVeHNpQjQygRk2camXRKi7cSi7Xs'
    DBHOST = 'dpg-croilh9u0jms73c9mhhg-a.frankfurt-postgres.render.com'