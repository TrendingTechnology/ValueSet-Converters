"""Get value sets from VSAC

Docs:
- https://documentation.uts.nlm.nih.gov/rest/authentication.html
"""
from bs4 import BeautifulSoup
import urllib3.util
import requests

from value_set_vsac_json_to_n3c_json.config import config


API_KEY = config['vsac_api_key']


def get_ticket_granting_ticket() -> str:
    """Get TGT (Ticket-granting ticket)"""
    # 'curl -X POST https://utslogin.nlm.nih.gov/cas/v1/api-key -H 'content-type: application/x-www-form-urlencoded'
    #   -d apikey={your_api_key_here}'
    response = requests.post(
        url='https://utslogin.nlm.nih.gov/cas/v1/api-key',
        data={'apikey': API_KEY})
    # Siggie: Sometimes the URL returned works as TGT; and sometimes the TGT string itself will serve as the TGT.
    soup = BeautifulSoup(response.text, 'html.parser')
    tgt_url = soup.find('form').attrs['action']
    ticket_granting_ticket = urllib3.util.parse_url(tgt_url).path.split('/')[-1]

    return ticket_granting_ticket


def get_service_ticket(tgt) -> str:
    """Get single-use service ticket

    Params:
        tgt (str): Ticket granting ticket
    """
    # curl -X POST https://utslogin.nzlm.nih.gov/cas/v1/tickets/{your_TGT_here} -H 'content-type:
    #   application/x-www-form-urlencoded' -d service=http%3A%2F%2Fumlsks.nlm.nih.gov
    # - Any of the 3 urls below will work
    response2 = requests.post(
        url='https://utslogin.nlm.nih.gov/cas/v1/tickets/{}'.format(tgt),
        # url='https://utslogin.nlm.nih.gov/cas/v1/api-key/{}'.format(ticket_granting_ticket),
        # url='https://vsac.nlm.nih.gov/vsac/ws/Ticket/{}'.format(ticket_granting_ticket),
        data={'service': 'http://umlsks.nlm.nih.gov'},
        headers={'Content-type': 'application/x-www-form-urlencoded'})
    service_ticket = response2.text

    return service_ticket