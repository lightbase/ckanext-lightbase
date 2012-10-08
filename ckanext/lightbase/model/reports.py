# -*- coding: UTF-8 -*-
from logging import getLogger

from sqlalchemy import event
from sqlalchemy import distinct
from sqlalchemy import Table
from sqlalchemy import Column
#from sqlalchemy import ForeignKey
#from sqlalchemy import types
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.orm import backref, relation

# Import model tools
from ckan.lib.base import config
from ckan import model
from ckan.model import Session
from ckan.model.meta import *
from ckan.model.domain_object import DomainObject
from ckan.model.types import make_uuid

log = getLogger(__name__)

__all__ = [
    'lightbaseDatasetReports', 'lb_dataset_reports',
    'lightbaseDatasetActions', 'lb_dataset_actions'
  ]


lb_dataset_reports = None
lb_dataset_actions = None

import collections
from sqlalchemy.ext.mutable import Mutable
from sqlalchemy.types import TypeDecorator, VARCHAR
import json

#Base = declarative_base()

class JSONEncodedDict(TypeDecorator):
    "Represents an immutable structure as a json-encoded string."
    impl = VARCHAR

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value


class MutationDict(Mutable, dict):
    """
    this class allows to store python dicts in database
    """
    @classmethod
    def coerce(cls, key, value):
        "Convert plain dictionaries to MutationDict."

        if not isinstance(value, MutationDict):
            if isinstance(value, dict):
                return MutationDict(value)

            # this call will raise ValueError
            return Mutable.coerce(key, value)
        else:
            return value

    def __setitem__(self, key, value):
        "Detect dictionary set events and emit change events."

        dict.__setitem__(self, key, value)
        self.changed()

    def __delitem__(self, key):
        "Detect dictionary del events and emit change events."

        dict.__delitem__(self, key)
        self.changed()

MutationDict.associate_with(JSONEncodedDict)

def setup():

    if lb_dataset_reports is None or lb_dataset_actions is None:
        define_tables()
        log.debug('Lightbase report tables defined in memory')

    if model.repo.are_tables_created():

        if not lb_dataset_actions.exists():
            try:
                lb_dataset_actions.create()
            except Exception,e:
                # Make sure the table does not remain incorrectly created
                # (eg without geom column or constraints)
                if lb_dataset_actions.exists():
                    Session.execute('DROP TABLE lb_dataset_actions')
                    Session.commit()

                raise e

            log.debug('Dataset actions tables created')
        else:
            log.debug('Dataset actions tables already exist')
            # Future migrations go here

        if not lb_dataset_reports.exists():
            try:
                lb_dataset_reports.create()
            except Exception,e:
                # Make sure the table does not remain incorrectly created
                # (eg without geom column or constraints)
                if lb_dataset_reports.exists():
                    Session.execute('DROP TABLE lb_dataset_reports')
                    Session.commit()

                raise e

            log.debug('Lightbase report tables created')
        else:
            log.debug('Lightbase report tables already exist')
            # Future migrations go here

    else:
        log.debug('Lightbase report tables creation deferred')

class lightbaseDatasetActions(DomainObject):
    """
    Register possible actions to datasets
    """
    __tablename__ = 'lb_dataset_actions'

    lb_dataset_actions_id = Column(UnicodeText, primary_key=True, default=make_uuid)
    action_name = Column(UnicodeText, nullable=False)

    #def __init__(self, lb_dataset_actions_id, action_name):
    def __init__(self, action_name):
        #self.lb_dataset_actions_id = lb_dataset_actions_id
        self.action_name = action_name

    def __repr__(self):
        #return "<lightbaseDatasetActions('%s', '%s')>" % (self.lb_dataset_actions_id, self.action_name)
        return "<lightbaseDatasetActions('%s')>" % (self.action_name)


class lightbaseDatasetReports(DomainObject):
    """
    The repository will hold information about every uploaded files
    """
    __tablename__ = 'lb_dataset_reports'
    
    report_id = Column(UnicodeText, primary_key=True, default=make_uuid)
    dataset_id = Column(UnicodeText,ForeignKey('package.id'),nullable=False)
    dataset_action_id = Column(UnicodeText,ForeignKey('lb_dataset_actions.lb_dataset_actions_id'),nullable=False)
    fields_list = Column(MutationDict.as_mutable(JSONEncodedDict))
    source = Column(UnicodeText)

    
    #def __init__(self, report_id, dataset_id, dataset_action_id, fields_list, report):
    def __init__(self, dataset_id, dataset_action_id, fields_list, source):
        #self.report_id = report_id
        self.dataset_id = dataset_id
        self.dataset_action_id = dataset_action_id
        self.fields_list = fields_list
        self.source = source
        
    def __repr__(self):
        #return "<lightbaseDatasetReports('%s','%s', '%s', '%s', '%s')>" % (self.report_id, self.dataset_id, self.dataset_action_id, self.fields_list, self.source)
        return "<lightbaseDatasetReports('%s', '%s', '%s', '%s')>" % (self.dataset_id, self.dataset_action_id, self.fields_list, self.source)


def define_tables():

    global lb_dataset_actions
    global lb_dataset_reports

    lb_dataset_reports = Table('lb_dataset_reports', metadata,
                             Column('report_id',UnicodeText, primary_key=True, default=make_uuid),
                             Column('dataset_id',UnicodeText,ForeignKey('package.id'),nullable=False),
                             Column('dataset_action_id',UnicodeText,ForeignKey('lb_dataset_actions.dataset_action_id'),nullable=False),
                             Column('fields_list',MutationDict.as_mutable(JSONEncodedDict)),
                             Column('source',UnicodeText)
                             )

    mapper(lightbaseDatasetReports, lb_dataset_reports)

    lb_dataset_actions = Table('lb_dataset_actions', metadata,
                            Column('dataset_action_id', UnicodeText, primary_key=True, default=make_uuid),
                            Column('action_name', UnicodeText, nullable=False),
                            )

    mapper(lightbaseDatasetActions, lb_dataset_actions)
