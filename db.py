import copy
import json
import datetime
from typing import Union, List, Dict, Optional, TypeVar, Type, Generic, Any
from contextlib import contextmanager

import boto3  # type: ignore
import botocore.exceptions  # type: ignore
from boto3.dynamodb.conditions import Key, Attr, NotEquals, In, AttributeExists, AttributeNotExists, Contains, Size, AttributeType  # type: ignore
from pydantic import BaseModel


class _BatchWriter:
    def __init__(self, writer):
        self.writer = writer

    def put(self, item: dict):
        self.writer.put_item(Item=item)

    def remove(self, item: dict):
        self.writer.delete_item(Key=item)


class _ModelBatchWriter:
    def __init__(self, writer: _BatchWriter):
        self.writer = writer

    def put(self, item: BaseModel):
        self.writer.put(item=json.loads(item.json()))

    def remove(self, item: BaseModel):
        self.writer.remove(item=json.loads(item.json()))


class CreationTimestampField:
    creation_timestamp = 'creation_timestamp'


class DynamoDBTable:
    _dynamo_db: boto3.resource = None

    def __init__(self, name, *keys, endpoint: str = ''):
        self.name = name
        self.keys = keys
        self.endpoint = endpoint
        if self.endpoint == '':
            self.table = self._get_dynamodb().Table(self.name)
        else:
            self.table = boto3.resource('dynamodb', endpoint_url=self.endpoint).Table(self.name)

    @classmethod
    def _get_dynamodb(cls):
        if cls._dynamo_db is None:
            cls._dynamo_db = boto3.resource('dynamodb')
        return cls._dynamo_db

    @contextmanager
    def batch_writer(self):
        with self.table.batch_writer() as writer:
            yield _BatchWriter(writer)

    def put(self, item: Dict):
        '''
        Wraps the boto3 put function
        Check if there is a creation_timestamp field in the item and if not add it
        '''
        if CreationTimestampField.creation_timestamp not in item:
            item[CreationTimestampField.creation_timestamp] = datetime.datetime.utcnow().isoformat()
        self.table.put_item(
            Item=item
        )

    def remove(self, item: Dict):
        self.table.delete_item(
            Key={k: item[k] for k in self.keys}
        )

    def scan(self, filter_expression: Union[None, NotEquals, In, AttributeExists, AttributeNotExists, Contains, Size, AttributeType] = None) -> List[Dict]:
        '''
        Wraps the boto3 scan function and returns the object clean without the Items key.
        Optional parameter filter_expression returns filtered results
        For more info about filter_expression parameter and his types
        https://boto3.amazonaws.com/v1/documentation/api/latest/_modules/boto3/dynamodb/conditions.html#Attr
        '''
        if filter_expression is None:
            return self.table.scan().get('Items', [])
        return self.table.scan(FilterExpression=filter_expression).get('Items', [])

    def scan_with_eq_filter(self, **kwargs) -> List[Dict]:
        assert len(kwargs) > 0
        conditions = [Attr(attr).eq(value) for attr, value in kwargs.items()]
        condition = conditions[0]
        for sub_cond in conditions[1:]:
            condition = condition & sub_cond

        result = self.table.scan(
            FilterExpression=condition
        )
        return result.get('Items')

    def scan_with_in_filter(self, **kwargs) -> List[Dict]:
        assert len(kwargs) > 0
        conditions = [Attr(attr).is_in(value)
                      for attr, value in kwargs.items()]
        condition = conditions[0]

        result = self.table.scan(
            FilterExpression=condition
        )
        return result.get('Items')

    def update_by_set(self, key: dict, attribute, value):
        self.table.update_item(
            Key={k: key[k] for k in self.keys},
            UpdateExpression="set #P = :v",
            ExpressionAttributeNames={"#P": attribute},
            ExpressionAttributeValues={":v": value}
        )

    def update_if_not_set(self, key: dict, attribute, value) -> bool:
        try:
            self.table.update_item(
                Key={k: key[k] for k in self.keys},
                UpdateExpression="set #P = :v",
                ExpressionAttributeNames={"#P": attribute},
                ExpressionAttributeValues={":v": value},
                ConditionExpression='attribute_not_exists(#P)'
            )
            return True
        except botocore.exceptions.ClientError as exc:
            if exc.response['Error']['Code'] == 'ConditionalCheckFailedException':
                return False
            raise

    def query(self, index=None, **kwargs) -> List[Dict]:
        assert len(kwargs) > 0
        conditions = [Key(key).eq(value) for key, value in kwargs.items()]
        condition = conditions[0]
        for sub_cond in conditions[1:]:
            condition = condition & sub_cond
        if index:
            result = self.table.query(
                KeyConditionExpression=condition,
                IndexName=index,
            )
        else:
            result = self.table.query(
                KeyConditionExpression=condition
            )
        return result.get('Items')

    def get_first(self, index=None, **kwargs) -> Optional[Dict]:
        result = self.query(index=index, **kwargs)
        if result:
            return result[0]
        return None


T = TypeVar('T', bound=BaseModel)


class DynamoDBModelTable(Generic[T]):
    _dynamo_db: boto3.resource = None

    def __init__(self, name, model: Type, *keys):
        self.table = DynamoDBTable(name, *keys)
        self.model = model

    @contextmanager
    def batch_writer(self):
        with self.table.batch_writer() as writer:
            yield _ModelBatchWriter(writer)

    def put(self, item: T):
        self.table.put(json.loads(item.json()))

    def remove(self, item: T):
        self.table.remove(json.loads(item.json()))

    def scan(self) -> List[T]:
        return [self.model(**d) for d in self.table.scan()]

    def scan_with_eq_filter(self, **kwargs) -> List[T]:
        return [self.model(**d) for d in self.table.scan_with_eq_filter(**kwargs)]

    def scan_with_in_filter(self, **kwargs) -> List[T]:
        return [self.model(**d) for d in self.table.scan_with_in_filter(**kwargs)]

    def query(self, index=None, **kwargs) -> List[T]:
        return [self.model(**d) for d in self.table.query(index, **kwargs)]

    def get_first(self, index=None, **kwargs) -> Optional[T]:
        result = self.query(index=index, **kwargs)
        if result:
            return result[0]
        return None


class MockDynamoDBTable:
    table_registry: Dict[str, Dict] = {}

    def __init__(self, name, *keys):
        self.name = name
        self.keys = keys
        if name in self.table_registry:
            self.items = self.table_registry[name]
        else:
            self.items = {}
            self.table_registry[name] = self.items

    def clear(self):
        self.items = {}

    @classmethod
    def clear_db(cls):
        cls.table_registry.clear()

    @contextmanager
    def batch_writer(self):
        orig_self = self

        class MockBatchWriter:
            # pylint: disable=too-few-public-methods
            @staticmethod
            def put(item):
                orig_self.put(item)

            @staticmethod
            def remove(item):
                orig_self.remove(item)

        yield MockBatchWriter()

    def update_by_set(self, key: dict, attribute: str, value: Any):
        found = False
        for item in self.items.values():
            if all(item[k] == key[k] for k in self.keys):
                item[attribute] = value
                found = True
        if not found:
            item = key.copy()
            item[attribute] = value
            self.items[key] = item

    def update_if_not_set(self, key: dict, attribute: str, value: Any) -> bool:
        found = False
        for item in self.items.values():
            if all(item[k] == key[k] for k in self.keys):
                if attribute in item:
                    return False
                item[attribute] = value
                found = True

        if not found:
            item = key.copy()
            item[attribute] = value
            self.items[key] = item
        return True

    def update_item_primary_key(self, update_fields: dict, **kwargs) -> bool:
        '''
        get kwargs as key values (to find the Item) and update_fields (to update fields)
        return True if successful, False is Item is not on DB
        '''
        complete_key = tuple(val for key, val in kwargs.items())
        item = self.items.get(complete_key)
        if item is None:
            return False
        for key, val in update_fields.items():
            item[key] = val
        self.items[complete_key] = item
        return True

    def put(self, item: Dict):
        if CreationTimestampField.creation_timestamp not in item:
            item[CreationTimestampField.creation_timestamp] = datetime.datetime.utcnow().isoformat()
        complete_key = tuple(item[key] for key in self.keys)
        self.items[complete_key] = copy.deepcopy(item)

    def remove(self, item):
        complete_key = tuple(item[key] for key in self.keys)
        del self.items[complete_key]

    def query(self, index=None, **kwargs) -> List[Dict]:
        # pylint: disable=unused-argument
        assert len(kwargs) > 0
        items = []
        for item in self.items.values():
            if all(item[key] == desired_value for key, desired_value in kwargs.items()):
                items.append(copy.deepcopy(item))
        return items

    def scan(self):
        return list(copy.deepcopy(v) for v in self.items.values())

    def print_table(self):
        for key, item in self.items.items():
            print(f"{key} -> {item}\n\n")

    def scan_with_eq_filter(self, **kwargs) -> List[Dict]:
        # pylint: disable=unused-argument
        assert len(kwargs) > 0
        items = []
        for item in self.items.values():
            if all(key in item and item[key] == desired_value for key, desired_value in kwargs.items()):
                items.append(copy.deepcopy(item))
        return items

    def scan_with_in_filter(self, **kwargs) -> List[Dict]:
        # pylint: disable=unused-argument
        assert len(kwargs) > 0
        items = []
        for item in self.items.values():
            if all(item[key] in desired_value for key, desired_value in kwargs.items()):
                items.append(copy.deepcopy(item))
        return items

    def get_first(self, index=None, **kwargs) -> Optional[Dict]:
        result = self.query(index=index, **kwargs)
        if result:
            return result[0]
        return None


class MockDynamoDBModelTable(DynamoDBModelTable, Generic[T]):
    def __init__(self, name, model: Type, *keys):
        # pylint: disable=super-init-not-called
        self.table = MockDynamoDBTable(name, *keys)  # type: ignore
        self.model = model
