#!/usr/bin/env python

import json
from urllib import request, parse
import time
import logging
import sys

class RetryLimitException(Exception):
    def __init__(self, message):
        super(RetryLimitException, self).__init__(message)

def retry(fn, count=5, duration=2):
    for i in range(count):
        try:
            result = fn()
            return result
        except:
            if i < count - 1:
                time.sleep(duration)
                duration *= duration
            else:
                raise RetryLimitException('Retries exceeded: {retries}'.format(retries=count))

def geolocation(address):
    encoded_address = parse.quote(address)
    url = 'https://maps.googleapis.com/maps/api/geocode/json?address={address}'.format(address=encoded_address)
    req = request.Request(url, method='GET')
    with request.urlopen(req) as f:
        resp = f.read().decode('utf-8')
    body = json.loads(resp)
    return body['results'][0]['geometry']['location']

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    logger = logging.getLogger('geolocation')
    
    output = []
    with open('addresses.txt') as f:
        for line in f:
            address = line.strip()
            try:
                result = retry(lambda: geolocation(address))
                result = {
                    'address': address,
                    'status': 'FOUND',
                    'location': result,
                }
            except RetryLimitException:
                result = {
                    'address': address,
                    'status': 'NOT_FOUND',
                    'location': {
                        'lat': None,
                        'lng': None,
                    }
                }
            except Exception as e:
                logger.error(e)
            logger.debug('Received result {result}'.format(result=result))
            output.append(result)
    
    with open('output.json', 'w') as f:
        json.dump(output, f, indent=2, sort_keys=True)
