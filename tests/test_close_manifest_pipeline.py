import json
import os
import sys
import time
from unittest import mock

import boto3
import pytest
from moto import mock_sns, mock_sqs, mock_events

from lambdas.manifest_close_statemachine_handler import ClosePipeline

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

os.environ['SQS_PERSIST_HISTORICAL_ARN'] = "os_environ_SQS_PERSIST_HISTORICAL_ARN"


@pytest.fixture
def event():
    event = [{
        "batch_id": str(int(time.time())),
        "queueUrl": None,
        "receiptHandle": "test",
        "is_historical": "false"
    }]
    yield event


class MockMessage:
    def __init__(self, *args, **kwargs):
        """left empty because mock method"""
        pass

    def delete(self):
        """left empty because mock method"""
        pass


class MockSQS:

    def Message(self, *args, **kwargs):
        return MockMessage(*args, **kwargs)

    def get_queue_by_name(self, *args, **kwargs):
        return MockQueue()


class MockQueue:
    def __init__(*args, **kwargs):
        """left empty because mock method"""
        pass

    def send_message(self, *args, **kwargs):
        """left empty because mock method"""
        pass


@mock_sns
def test_publish_message_to_sns():
    """
    Creates a message and tests publish_message_to_sns via mock_sns
    """
    batch_id = str(int(time.time()))
    topic_name = "dev-dot-sdc-cloudwatch-alarms-notification-topic"
    message = {"BatchId": batch_id, "Status": "Manifest generation completed"}
    sns = boto3.client('sns', region_name='us-east-1')
    response = sns.create_topic(Name=topic_name)
    os.environ["BATCH_NOTIFICATION_SNS"] = response['TopicArn']
    close_pipeline_obj = ClosePipeline()
    close_pipeline_obj.sns.publish = mock.MagicMock()
    close_pipeline_obj.publish_message_to_sns(message)
    close_pipeline_obj.sns.publish.assert_called_with(
        TargetArn=os.environ['BATCH_NOTIFICATION_SNS'],
        Message=json.dumps({'default': json.dumps(message)}),
        MessageStructure='json'
    )


@mock_sqs
def test_put_message_sqs():
    sqs = boto3.client('sqs', region_name='us-east-1')
    response = sqs.create_queue(QueueName='dev-dot-sdc-waze-data-persistence-orchestration',
                                Attributes={'FifoQueue': "false", 'DelaySeconds': "5",
                                            'MaximumMessageSize': "262144", 'MessageRetentionPeriod': "1209600",
                                            'VisibilityTimeout': "960"})
    queue_url = response['QueueUrl']

    queue_name = queue_url[queue_url.rfind('/') + 1: len(queue_url)]
    generated_batch_id = str(int(time.time()))
    close_pipeline_obj = ClosePipeline()
    close_pipeline_obj.sqs = MockSQS()
    close_pipeline_obj.put_message_sqs(generated_batch_id, queue_name)


@mock_sqs
def test_put_message_sqs_exception():
    with pytest.raises(Exception):
        sqs = boto3.client('sqs', region_name='us-east-1')
        sqs.create_queue(QueueName='dev-dot-sdc-waze-data-persistence-orchestration',
                         Attributes={'FifoQueue': "false", 'DelaySeconds': "5",
                                     'MaximumMessageSize': "262144", 'MessageRetentionPeriod': "1209600",
                                     'VisibilityTimeout': "960"})
        generated_batch_id = str(int(time.time()))
        close_pipeline_obj = ClosePipeline()

        # close_pipeline_obj.sqs = MockSQS()
        close_pipeline_obj.put_message_sqs(generated_batch_id, "")


@mock_events
def test_close_pipeline():
    with pytest.raises(Exception):
        close_pipeline_obj = ClosePipeline()
        assert close_pipeline_obj.close_pipeline(None, None) is None


@mock_sqs
def test_delete_sqs_message_assign_persistence_queue(event):
    os.environ['SQS_PERSIST_ARN'] = "os_environ_SQS_PERSIST_ARN"
    sqs = boto3.client('sqs', region_name='us-east-1')

    # configure queue_events
    response = sqs.create_queue(QueueName='dev-dot-sdc-waze-data-persistence-orchestration',
                                Attributes={'FifoQueue': "false", 'DelaySeconds': "5",
                                            'MaximumMessageSize': "262144", 'MessageRetentionPeriod': "1209600",
                                            'VisibilityTimeout': "960"})
    queue_url = response['QueueUrl']
    queue_events = event
    queue_events[0]["queueUrl"] = queue_url

    # set up ClosePipeline instance for testing
    close_pipeline_obj = ClosePipeline()
    close_pipeline_obj.put_message_sqs = mock.MagicMock()
    close_pipeline_obj.publish_message_to_sns = mock.MagicMock()

    # delete_sqs_message
    close_pipeline_obj.sqs = MockSQS()
    close_pipeline_obj.delete_sqs_message(queue_events, None)

    # verify the persistence queue name that was passed to self.put_message_sqs(batchId, persistenceQueue)
    close_pipeline_obj.put_message_sqs.assert_called_once_with(event[0]["batch_id"],
                                                               os.environ['SQS_PERSIST_ARN'])


@mock_sqs
def test_delete_sqs_message_assign_historical_persistence_queue(event):
    os.environ['SQS_PERSIST_ARN'] = "os_environ_SQS_PERSIST_ARN"
    sqs = boto3.client('sqs', region_name='us-east-1')

    # configure queue_events
    response = sqs.create_queue(QueueName='dev-dot-sdc-waze-data-persistence-orchestration',
                                Attributes={'FifoQueue': "false", 'DelaySeconds': "5",
                                            'MaximumMessageSize': "262144", 'MessageRetentionPeriod': "1209600",
                                            'VisibilityTimeout': "960"})
    queue_url = response['QueueUrl']
    queue_events = event
    queue_events[0]["queueUrl"] = queue_url
    queue_events[0]["is_historical"] = "true"

    # set up ClosePipeline instance for testing
    close_pipeline_obj = ClosePipeline()
    close_pipeline_obj.sqs = MockSQS()
    close_pipeline_obj.publish_message_to_sns = mock.MagicMock()
    close_pipeline_obj.put_message_sqs = mock.MagicMock()

    # delete_sqs_message
    close_pipeline_obj.delete_sqs_message(queue_events, None)

    # verify the persistence queue name that was passed to self.put_message_sqs(batchId, persistenceQueue)
    close_pipeline_obj.put_message_sqs.assert_called_once_with(event[0]["batch_id"],
                                                               os.environ['SQS_PERSIST_HISTORICAL_ARN'])
