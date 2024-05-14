from celery import Celery
from sqlalchemy import create_engine, Column, DateTime, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
import os
import json
import subprocess
import datetime
from kombu import Queue

os.environ['AWS_PROFILE'] = 'default'
os.environ['AWS_SHARED_CREDENTIALS_FILE'] = '/credentials'


# broker_url = os.getenv('BROKER_URL')
# print(broker_url)

# format the guy correctly
# broker_url = broker_url.replace('https://', '')
# broker_url = 'sqs://' + broker_url


broker_url = 'sqs://' #https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/sqs.html

db_url = os.getenv('DB_URL')



# Create the Celery app
app = Celery('spamworker', broker=broker_url)
app.conf.task_default_queue = os.getenv('QUEUE_NAME', 'low_priority_queue')
app.conf.broker_connection_retry_on_startup = True # allow indefinitely retrying to connect to the broker

# allow listening to both queues and ensure it serves the one it assigned.
if os.getenv('QUEUE_NAME') == 'low_priority_queue':
    highQueuePriority = 0
    lowQueuePriority = 1
else:
    highQueuePriority = 1
    lowQueuePriority = 0
app.conf.task_queues = [
    Queue('low_priority_queue', priority=lowQueuePriority),
    Queue('high_priority_queue', priority=highQueuePriority)
]

# Set up SQLAlchemy
engine = create_engine(db_url, pool_size=4, max_overflow=1, pool_pre_ping=True, connect_args={'connect_timeout': 30})
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

Base = declarative_base()

class Emails(Base): 
    __tablename__ = 'emails'
    id = Column(UUID(as_uuid=True), primary_key=True)
    customerId = Column(UUID(as_uuid=True), nullable=False)
    createdAt = Column(DateTime, nullable=False)
    updatedAt = Column(DateTime, nullable=False)
    toReceiver = Column(Text, nullable=False)
    fromSender = Column(Text, nullable=False)
    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    status = Column(Text, nullable=False)
    malicious = Column(Boolean, nullable=True)
    domains = Column(ARRAY(Text), nullable=True)
    spamhammer = Column(Text, nullable=True)

@app.task(name="process_message")
def process_message(message):


    session = Session()

    # Query the database for the existing email entry
    email = session.query(Emails).filter_by(id=message['id']).first()

    

    if email is not None:
        emailId = email.id
        emailBody = email.body
        emailMetadata = email.spamhammer

        session.close()

        # SpamHammer
        try:
            spamHammerInput = {
                "id": str(emailId),
                "content": emailBody,
                "metadata": emailMetadata
            }
            
            spamHammerInputJson = json.dumps(spamHammerInput)

            spamHammerOutputJson = subprocess.check_output(['./spamworker/spamhammer', 'scan', '--input', '-', '--output', '-'], input=spamHammerInputJson, text=True)

            spamHammerOutput = json.loads(spamHammerOutputJson)
            malicious = spamHammerOutput.get('malicious', False)

            session = Session()

            # Query the database for the existing email entry
            email = session.query(Emails).filter_by(id=message['id']).first()

            # Update the email in the database
            email.malicious = malicious
            email.updatedAt = datetime.datetime.utcnow()
            email.status = 'scanned'
            session.commit()

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"Error calling SpamHammer: {str(e)}")

    session.close()



if __name__ == '__main__':
    app.worker_main(['worker', '-c', '68']) # we love the Toyota 86. i have a red one. i like red 
    #TODO maybe above can have more 