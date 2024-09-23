from gasp_server.__init__ import create_app
import logging

app = create_app(logging_level=logging.WARNING, config='gasp_server.config.DevConfig')
if __name__ == '__main__':
    app.run()