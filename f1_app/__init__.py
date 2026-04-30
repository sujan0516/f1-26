from flask import Flask
from .routes import api
import logging

def create_app():
    app = Flask(
        __name__,
        static_folder='../static',
        static_url_path='',
        template_folder='../templates',
    )
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('f1_app')
    logger.info("Initializing F1 2026 AI Championship Predictor (Modular)")

    # Register Blueprints
    app.register_blueprint(api)
    from .legacy import legacy_api
    app.register_blueprint(legacy_api)

    return app
