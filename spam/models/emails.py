from . import db 
from sqlalchemy.dialects.postgresql import UUID, ARRAY


# TODO double check what is nullable
class Emails(db.Model): 
    __tablename__ = 'emails'
    id = db.Column(UUID(as_uuid=True), primary_key=True)
    customerId = db.Column(UUID(as_uuid=True), nullable=False)
    createdAt = db.Column(db.DateTime, nullable=False)
    updatedAt = db.Column(db.DateTime, nullable=False)
    toReceiver = db.Column(db.Text, nullable=False)
    fromSender = db.Column(db.Text, nullable=False)
    subject = db.Column(db.Text, nullable=True)
    body = db.Column(db.Text, nullable=True)
    status = db.Column(db.Text, nullable=False)
    malicious = db.Column(db.Boolean, nullable=True)
    domains = db.Column(ARRAY(db.Text), nullable=True)
    spamhammer = db.Column(db.Text, nullable=True)

    # def __repr__(self): 
    #    return f'<Todo {self.id} {self.title}>'

    def as_dict(self):
        return {
            'id': str(self.id),
            'customerId': str(self.customerId),
            'createdAt': self.createdAt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'updatedAt': self.updatedAt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'to': self.toReceiver,
            'from': self.fromSender,
            'subject': self.subject,
            'status': self.status,
            'malicious': self.malicious,
            'domains': self.domains,
            'spamhammer': self.spamhammer, 
            'body': self.body
        }
    
    def as_dict_for_queue(self):
        return {
            'id': str(self.id)
        }