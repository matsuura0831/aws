import json
import os

from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

import boto3
import requests

SLACK_WEBHOOK_URL = os.environ['SLACK_WEBHOOK_URL']
SLACK_CHANNEL = os.environ['SLACK_CHANNEL']

def get_cost():
    begin = datetime.today()
    end = begin + relativedelta(months=1)

    client = boto3.client("ce")
    result = client.get_cost_and_usage(
            TimePeriod={
                "Start": datetime.strftime(begin, "%Y-%m-01"),
                "End": datetime.strftime(end, "%Y-%m-01")
                },
            Granularity='MONTHLY',
            Metrics=["BlendedCost"]
            )

    cost = result["ResultsByTime"][0]["Total"]["BlendedCost"]

    return cost # {"Amount": "<float_str>", "Unit": "USD" }

def build_message(cost, channel=SLACK_CHANNEL):
    amount = float(cost['Amount'])
    unit = cost['Unit']

    amount_rounded = round(amount, 2)

    return {
        'text': f'今月のAWS料金は {amount_rounded} {unit}',
        'channel': channel,
        'username': 'BillingCheck',
        'icon_emoji': ':aws:',
        }

def post_message(msg, webhook=SLACK_WEBHOOK_URL):
    response = requests.post(webhook, data=json.dumps(msg))
    response.raise_for_status()

def lambda_handler(event, context):
    cost = get_cost()
    msg = build_message(cost)
    post_message(msg)
