import datetime
from enum import Enum
from http.client import BAD_REQUEST
import json
import subprocess
from flask import Blueprint, jsonify, request
from spam.models.emails import Emails
from spam.models import db 
import uuid
from sqlalchemy import text
import re
import pendulum
from celery import Celery
import os

# # get environment variable for the queue
# queueLink = os.getenv('BROKER_URL')
# # format the guy correctly
# queueLink = queueLink.replace('https://', '')
# queueLink = 'sqs://' + queueLink

queueLink = "sqs://"

os.environ['AWS_PROFILE'] = 'default'
os.environ['AWS_SHARED_CREDENTIALS_FILE'] = '/credentials'

celery_app = Celery('tasks', broker=queueLink)

celery_app.conf.task_default_queue = os.getenv('QUEUE_NAME', 'low_priority_queue') #Set default as the low priority queue 
highPriorityQueue = os.getenv('HIGH_PRIORITY_QUEUE', 'high_priority_queue')



class EmailState(Enum):
    PENDING = 'pending'
    SCANNED = 'scanned'
    FAILED = 'failed'

REQUIRED_HEADERS_POST = {"Accept": "application/json"} # evan trolls and does not send Content-Type header for post. but if he eventually does i can add here. 
REQUIRED_HEADERS = {"Accept": "application/json"}

api = Blueprint('api', __name__, url_prefix='/api/v1')

# the header check. checking received headers and their parsed in values
@api.before_request
def check_required_headers():
    # TODO if bothered implement this and stuff...
    return


    if request.path == '/api/v1/health':
        return
    elif request.path == '/api/v1/customers/<customerId>/emails':
        for header, value in REQUIRED_HEADERS_POST.items():
            if header not in request.headers:
                return jsonify({"error": f"Missing required header: {header}"}), 400
            if request.headers.get(header) != value:
                return jsonify({"error": f"Invalid {header}, must be {value}"}), 400
        return
    for header, value in REQUIRED_HEADERS.items():
        if header not in request.headers:
            return jsonify({"error": f"Missing required header: {header}"}), 400
        if request.headers.get(header) != value:
            return jsonify({"error": f"Invalid {header}, must be {value}"}), 400


def is_valid_customer(customerId):
    try:
        customerId = uuid.UUID(customerId, version=4)
    except ValueError:
        return False
    
    customer = db.session.query(Emails).filter_by(customerId=customerId).first()
    if customer is None:
        return False
    return True

def is_valid_email(emailId):
    email = db.session.query(Emails).filter_by(id=emailId).first()
    if email is None:
        return False
    return True


# 1. GET /customers/{customerId}/emails
@api.route('/customers/<customerId>/emails', methods=['GET'])
def get_emails(customerId):
  try :
        if is_valid_customer(customerId) == False:
            return jsonify({"error": "Invalid customerId"}), 400
        
        limit = request.args.get('limit', type=int)
        if limit is not None and (limit > 1000 or limit <= 0):
            return jsonify({"error": "Invalid limit value, must be between 0 and 1000"}), 400
        
        offset = request.args.get('offset', type=int)
        if offset is not None and offset < 0:
            return jsonify({"error": "Invalid offset value, must be greater than 0"}), 400

        startDate = request.args.get('start', type=str)
        if startDate is not None:
            try:
                pendulum.parse(startDate)
            except ValueError:
                return jsonify({"error": "Invalid date format for start, should be RFC3339"}), 400

        endDate = request.args.get('end', type=str)
        if endDate is not None:
            try:
                pendulum.parse(endDate)
            except ValueError:
                return jsonify({"error": "Invalid date format for end, should be RFC3339"}), 400


        toReceiver = request.args.get('to', type=str)
        if toReceiver is not None:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", toReceiver):
                return jsonify({"error": "Invalid email format for toReceiver"}), 400

        fromSender = request.args.get('from', type=str)
        if fromSender is not None:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", fromSender):
                return jsonify({"error": "Invalid email format for fromSender"}), 400


        state = request.args.get('state', type=str)
        if state is not None and state not in [EmailState.PENDING.value, EmailState.SCANNED.value, EmailState.FAILED.value]:
            return jsonify({"error": "Invalid state value, must be one of pending, scanned, failed"}), 400
        
        malicious = request.args.get('only_malicious', type=str)
        if malicious is not None and malicious.lower() not in ["true", "false"]:
            return jsonify({"error": "Invalid malicious value, must be true or false"}), 400
        session = db.session()

        # construct the base query
        query = session.query(Emails).filter_by(customerId=customerId)

        # apply filters
        if startDate:
            query = query.filter(Emails.createdAt >= startDate)
        if endDate:
            query = query.filter(Emails.createdAt < endDate) # TODO i hope i waste 1 second of your life reading this :). enjoy ur weekend
        if toReceiver:
            query = query.filter_by(toReceiver=toReceiver)
        if fromSender:
            query = query.filter_by(fromSender=fromSender)
        if state:
            query = query.filter_by(status=state)
        if malicious == "true": #is string lol
            query = query.filter_by(malicious=malicious)

        # apply limit and offset
        if limit:
            query = query.limit(limit)
        else:
            query = query.limit(100)
        if offset:
            query = query.offset(offset)

        # execute the query
        emails = query.all()

        result = []
        for email in emails:
            emailFormat = {
            'id': email.id,
            'created_at': email.createdAt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'updated_at': email.updatedAt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'contents' : {
                'to': email.toReceiver,
                'from': email.fromSender,
                'subject': email.subject
            },
            'status': email.status,
            'malicious': email.malicious,
            'domains': email.domains,
            'metadata': {
                'spamhammer': email.spamhammer}
                }
            result.append(emailFormat)
        return jsonify(result)
  except Exception as e:
        return jsonify({"error": f"Unexpected error probs due to Evan being mean to me: {str(e)}"}), 500


# 2. GET /customers/{customerId}/emails/{emailId}
@api.route('/customers/<customerId>/emails/<emailId>', methods=['GET'])
def get_email(customerId, emailId):
    try : 
        # if receive query params throw error
        if request.args:
            return jsonify({"error": "Query parameters not allowed"}), 400
        if is_valid_customer(customerId) == False:
            return jsonify({"error": "Invalid customerId"}), 404
        if is_valid_email(emailId) == False:
            return jsonify({"error": "Invalid emailId"}), 404
        
        email = db.session.query(Emails).filter_by(id=emailId).first()

        emailFormat = {
            'id': email.id,
            'created_at': email.createdAt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'updated_at': email.updatedAt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'contents' : {
                'to': email.toReceiver,
                'from': email.fromSender,
                'subject': email.subject
            },
            'status': email.status,
            'malicious': email.malicious,
            'domains': email.domains,
            'metadata': {
                'spamhammer': email.spamhammer}
            }
        return jsonify(emailFormat)
    except Exception as e:
        return jsonify({"error": f"Unexpected error probs due to Evan being mean to me: {str(e)}"}), 500


# 3. POST /customers/{customerId}/emails
@api.route('/customers/<customerId>/emails', methods=['POST'])
def create_emails(customerId):
  try:
        # check malformed request
        if not request.is_json:
            return jsonify({"error": "Malformed request"}), 400
        # check metadata supplied
        if 'metadata' not in request.json:
            return jsonify({"error": "metadata not supplied"}), 400
        # if metadata badly formed 
        if not isinstance(request.json['metadata'], dict):
            return jsonify({"error": "metadata badly formed"}), 400
        # check contents supplied
        if 'contents' not in request.json:
            return jsonify({"error": "contents not supplied"}), 400
        # if contents badly formed
        if not isinstance(request.json['contents'], dict):
            return jsonify({"error": "contents badly formed"}), 400
        # check if subject is supplied
        if 'subject' not in request.json['contents']:
            return jsonify({"error": "subject not supplied"}), 400
        # check if from is supplied
        if 'from' not in request.json['contents']:
            return jsonify({"error": "from not supplied"}), 400
        # check if to is supplied
        if 'to' not in request.json['contents']:
            return jsonify({"error": "to not supplied"}), 400
        # check if body is supplied
        if 'body' not in request.json['contents']:
            return jsonify({"error": "body not supplied"}), 400

        try :
            customerId = uuid.UUID(customerId, version=4)
        except ValueError:
            return jsonify({"error": "Invalid UUID format for customerId"}), 400
        
        data = request.get_json()
        metadata = data.get('metadata', {})
        contents = data.get('contents', {})

        subject = contents.get('subject')
        fromSender = contents.get('from')
        toReceiver = contents.get('to')
        body = contents.get('body')

        createdAt = datetime.datetime.utcnow()
        updatedAt = datetime.datetime.utcnow()

        # Add the email entry to the database with PENDING status
        email = Emails(
            id=str(uuid.uuid4()),
            customerId=customerId,
            createdAt=createdAt,
            updatedAt=updatedAt,
            toReceiver=toReceiver,
            fromSender=fromSender,
            subject=subject,
            body=body,
            status=EmailState.PENDING.value,
            malicious=None,  
            domains=[],
            spamhammer= metadata.get('spamhammer', '')
        )

        
        # Update the email entry with the result of the spamhammer scan
        email.malicious = None
        email.domains = re.findall(r'https?://([\w.-]+)', body)
        email.domains = list(dict.fromkeys(email.domains))
        db.session.add(email)
        db.session.commit()

###############################################################################################
        # sending to spamworker
        try:
            # if the uuid starts with 1111 send to high priority queue
            if str(email.customerId).startswith('1111'):
                celery_app.send_task('process_message', args=[email.as_dict_for_queue()], queue=highPriorityQueue)
            else:
                celery_app.send_task('process_message', args=[email.as_dict_for_queue()])
        except Exception as e:
            print(f"Error sending task to queue: {str(e)}")
            return jsonify({"error": f"Error sending task to queue: {str(e)}"}), 500
#########################################################################################3#####


        emailFormat = {
            'id': email.id,
            'created_at': email.createdAt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'updated_at': email.updatedAt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'contents' : {
                'to': email.toReceiver,
                'from': email.fromSender,
                'subject': email.subject
            },
            'status': email.status,
            'malicious': email.malicious,
            'domains': email.domains,
            'metadata': {
                'spamhammer': email.spamhammer}
            }
        return jsonify(emailFormat), 201
  except Exception as e:
        return jsonify({"error": f"Unexpected error probs due to Evan being mean to me: {str(e)}"}), 500



# 4. GET /customers/{customerId}/reports/actors
@api.route('/customers/<customerId>/reports/actors', methods=['GET'])
def get_reports_actors(customerId):
    try:
        # if receive query params throw error
        if request.args:
            return jsonify({"error": "Query parameters not allowed"}), 400
        if not is_valid_customer(customerId):
            # need to return blank report
            blankReportDict = {}
            blankReportDict["generated_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            blankReportDict["data"] = []
            blankReportDict["total"] = 0
            return jsonify(blankReportDict)
        
        actors = db.session.query(Emails).filter_by(malicious=True, customerId=customerId).all()

        actorsDict = {}
        actorsDict["generated_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        actorsDict["data"] = []

        for actor in actors:
            actorData = next((item for item in actorsDict["data"] if item["id"] == actor.fromSender), None)
            if actorData:
                actorData["count"] += 1
            else:
                actorsDict["data"].append({"id": actor.fromSender, "count": 1})
        actorsDict["total"] = len(actorsDict["data"])
        return jsonify(actorsDict)
    except Exception as e:
        return jsonify({"error": f"Unexpected error probs due to Evan being mean to me: {str(e)}"}), 500




#TODO need to test this one after getting email body domain scanning working
# 5. GET /customers/{customerId}/reports/domains
@api.route('/customers/<customerId>/reports/domains', methods=['GET'])
def get_reports_domains(customerId):
    try:
          # if receive query params throw error
          if request.args:
              return jsonify({"error": "Query parameters not allowed"}), 400
          if not is_valid_customer(customerId):
              # need to return blank report
              blankReportDict = {}
              blankReportDict["generated_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
              blankReportDict["data"] = []
              blankReportDict["total"] = 0
          
          domains = db.session.query(Emails).filter_by(customerId=customerId, malicious=True).all()
          
          domainsDict = {}
          domainsDict["generated_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
          domainsDict["data"] = []
          for domain in domains:
              for domain in domain.domains:
                  domainData = next((item for item in domainsDict["data"] if item["id"] == domain), None)
                  if domainData:
                      domainData["count"] += 1
                  else:
                      domainsDict["data"].append({"id": domain, "count": 1})
          domainsDict["total"] = len(domainsDict["data"])
          return jsonify(domainsDict)
    except Exception as e:
        return jsonify({"error": f"Unexpected error probs due to Evan being mean to me: {str(e)}"}), 500




#TODO malformed body check
# 6. GET /customers/{customerId}/reports/recipients
@api.route('/customers/<customerId>/reports/recipients', methods=['GET'])
def get_reports_recipients(customerId):
    try:
        # if receive query params throw error
        if request.args:
            return jsonify({"error": "Query parameters not allowed"}), 400
        if not is_valid_customer(customerId):
            # need to return blank report
            blankReportDict = {}
            blankReportDict["generated_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            blankReportDict["data"] = []
            blankReportDict["total"] = 0
            return jsonify(blankReportDict)
        
        recipients = db.session.query(Emails).filter_by(customerId=customerId, malicious=True).all()
        
        recipientsDict = {}
        recipientsDict["generated_at"] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        recipientsDict["data"] = []
        
        for recipient in recipients:
            recipientData = next((item for item in recipientsDict["data"] if item["id"] == recipient.toReceiver), None)
            if recipientData:
                recipientData["count"] += 1
            else:
                recipientsDict["data"].append({"id": recipient.toReceiver, "count": 1})
        recipientsDict["total"] = len(recipientsDict["data"])
        return jsonify(recipientsDict)
    except Exception as e:
        return jsonify({"error": f"Unexpected error probs due to Evan being mean to me: {str(e)}"}), 500


# Status Code: 200 - Service is healthy.
# Status Code: 500 - Service is not healthy.
# Status Code: 503 - Service is not healthy
# 7. GET /health
@api.route('/health')
def health():
    # check if db is up and working
    try:
        db.session.execute(text('SELECT 1'))
    except Exception as e:
        return jsonify({"status": "Unexpected error", "error": str(e)}), 500
    return jsonify({"status": "Service is healthy"}), 200


# for testing purposes
# @api.route('/customers/emails/Test/getAll', methods=['GET'])
# def get_all_test():
#     emails = Emails.query.all()
#     email_dicts = [email.as_dict() for email in emails]
#     return jsonify(emails=email_dicts)
