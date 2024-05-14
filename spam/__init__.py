from os import environ
from flask import Flask
from flask_sqlalchemy import SQLAlchemy 
from datetime import datetime
from uuid import uuid4

def create_app(config_overrides=None): 
   app = Flask(__name__) 
 
   app.config['SQLALCHEMY_DATABASE_URI'] = environ.get("SQLALCHEMY_DATABASE_URI", "sqlite:///db.sqlite")

   if 'postgresql' in app.config ['SQLALCHEMY_DATABASE_URI']:
      print("Using PostgreSQL")

   if config_overrides: 
       app.config.update(config_overrides)
 
   # Load the models 
   from spam.models import db 
   from spam.models.emails import Emails
   db.init_app(app) 
 

    #TODO figure out how to do the below section before gunicorn comes here. 
   # Create the database tables 
   with app.app_context(): 
      try:
        db.create_all() 
        db.session.commit()
      except Exception:
         print("caught table bad error lol")
 
   # Register the blueprints 
   from spam.views.routes import api 
   app.register_blueprint(api) 
 
   return app