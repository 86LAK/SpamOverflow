Email filtering software can filter email as it arrives or after.
SpamOverflow will implement a service that does not impede the flow of traffic (i.e. does not prevent the email arriving).
It will receive an API call when the mail server receives an email message.
The service then pulls the email from the user's inbox as fast as it can to prevent the user from seeing the malicious email or clicking any links.

Commercial email providers send an API request for each email received.
For optimal performance this service needs to be able to handle a large number of requests in a short period of time, so as to not miss any emails.

Since these emails can be dangerous, the service must be able to report that it is bad or good in a timely manner.
Though genuine emails that are incorrectly marked as dangerous should be returned to the user as quickly as possible.

Persistence is an important characteristic of the platform.
Customers will want to analyse why emails were flagged after the fact.
Upon receiving an email scan request, and after filtering, the system must guarantee that the data has been saved to persistent storage before returning a success response.
