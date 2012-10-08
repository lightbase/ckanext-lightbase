# -*- coding: utf-8 -*-
import sys
import os
from ckan.lib.base import request
from ckan.lib.base import c, g, h
from ckan.lib.base import model
from ckan.lib.base import render
from ckan.lib.base import _
from ckan.lib.base import BaseController

from ckan.lib.navl.validators import not_empty

#from ckan.controllers.user import UserController

# Imports
from ckan.logic import get_action, check_access
from datastore.client import *
#from ckan.controllers.group import GroupController
from ckan.controllers.package import PackageController
#from ckan.controllers.home import HomeController
#from ckan.controllers.admin import AdminController
from ckan.lib.base import response, redirect, gettext, abort
import ckan.logic.action.get
from pylons import config
from pylons.i18n import _
from ckan.lib.i18n import get_lang
import logging
from ckan.lib.package_saver import PackageSaver, ValidationException
from ckan.logic import NotFound, NotAuthorized, ValidationError
from ckan.lib.search import SearchError
from ckan.authz import Authorizer
import ckanclient
from ckan.logic import tuplize_dict, clean_dict, parse_params, flatten_to_string_key
from ckan.lib.navl.dictization_functions import DataError, unflatten, validate
from ckan.controllers.home import CACHE_PARAMETER

from lxml.html import fromstring, tostring
from ckanext.lightbase.util.text_to_html import *
from urllib import urlencode

import i18n
import urlparse

# Import model tools
from ckan.lib.base import config
from ckan import model
#from ckan.model import Session
#from ckan.model.meta import *

# Package model
from ckanext.lightbase.model.reports import *
from ckanext.lightbase.model.reports import setup as setup_model

setup_model()

log = logging.getLogger(__name__)

class lightbaseReportsController(PackageController):
    """
    Add controller to Reports
    """
    def _load_elastic_config(self):
        """
        Load elastic search configuration
        """
        self.user = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        ckan_url = config.get('ckan.site_url').rstrip('/')
        self.url = '%s/api/data/' % (ckan_url)
        # FIXME: Parametrize this
        self.url = urlparse.urljoin(self.url, 'lbdf/')


    def report_action(self, id, data=None, errors=None, error_summary=None):
        """
        Reports action page
        """
        # Setup dataset information
        package_type = self._get_package_type(id.split('@')[0])
        #context = {'model': model, 'session': model.Session,
        #           'user': c.user or c.author, 'extras_as_string': True,
        #           'schema': self._form_to_db_schema(package_type=package_type)}
        context = {'model': model, 'session': model.Session,
                   'save': 'save' in request.params,
                   'user': c.user or c.author, 'extras_as_string': True}
        data_dict = {'id': id}

        #check if package exists
        try:
            c.pkg_dict = get_action('package_update')(context, data_dict)
            c.pkg = context['package']
            c.pkg_json = json.dumps(c.pkg_dict)
        except NotFound:
            abort(404, _('Dataset not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to edit package %s') % id)

        data = data or clean_dict(unflatten(tuplize_dict(parse_params(
            request.params, ignore_keys=[CACHE_PARAMETER]))))

        errors = errors or {}
        error_summary = error_summary or {}
        vars = {'data': data, 'errors': errors, 'error_summary': error_summary}

        # Save data if requested
        if context.get('save') and data:
            result = self._save_report_action_new(data)
            # Return error message
            if not result:
                errors['name'] = 'Insertion error'
                error_summary[_(u'Ação')] = _(u'Erro inserindo elemento na base de dados')

        # Add actual reports actions information
        data['actions'] = model.Session.query(lightbaseDatasetActions).all()

        self._setup_template_variables(context, {'id': id})
        c.form = render('package/reports/actions_new_form.html', extra_vars=vars)

        return render('package/reports/actions_new.html')
       
    def _save_report_action_new(self, data):
        """
        Save report action data
        """
        # Save everything or fail everything
        try:

            # First save clean element
            action_elm = data.pop('name', None)
            if action_elm:
                data_elm = lightbaseDatasetActions(action_name = action_elm)
                model.Session.add(data_elm)
                log.warning('Adding element %s' % data_elm)

            # Get elements to be updated
            for key in data.keys():
                # find items to update
                field, separator, identifier = key.partition(':')
                if field == 'name' and separator == ':':
                    data_elm = model.Session.query(lightbaseDatasetActions).\
                      filter_by(dataset_action_id=identifier).all()[0]

                    # Assing new value to this object
                    if data_elm:
                        data_elm.action_name = data.get(key)

            # Now find elements to be deleted
            if isinstance(data.get('deleted'), (list, tuple)):
                # Use it to iterate throught the objects
                for elm in data.get('deleted'):
                    data_elm = model.Session.query(lightbaseDatasetActions).\
                      filter_by(dataset_action_id=elm).all()

                    report_elm = model.Session.query(lightbaseDatasetReports).\
                      filter_by(dataset_action_id=elm).all()

                    # Remove it from reports first
                    for report in report_elm:
                        log.warning('Removing report %s' % report)
                        model.Session.delete(report)

                    model.Session.commit()

                    if len(data_elm) > 0:
                        data_elm = data_elm[0]

                    log.warning('Removing element %s' % elm)

                    # As it's not in the list anymore, remove it
                    model.Session.delete(data_elm)
            elif data.get('deleted'):
                elm = data.get('deleted')

                data_elm = model.Session.query(lightbaseDatasetActions).\
                  filter_by(dataset_action_id=elm).all()

                report_elm = model.Session.query(lightbaseDatasetReports).\
                  filter_by(dataset_action_id=elm).all()

                # Remove it from reports first
                for report in report_elm:
                    log.warning('Removing report %s' % report)
                    model.Session.delete(report)

                model.Session.commit()

                if len(data_elm) > 0:
                    data_elm = data_elm[0]

                log.warning('Removing element %s' % elm)

                # As it's not in the list anymore, remove it
                model.Session.delete(data_elm)

            # Commit changes
            model.Session.commit()

            return True
        except:
            import traceback
            # For now just fail in any error
            log.error('Error adding value.\n%s' % traceback.format_exc())
            return False

    def report_new(self, id, data=None, errors=None, error_summary=None):
        """
        Controller to add a new report
        """
        # Setup dataset information
        package_type = self._get_package_type(id.split('@')[0])
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author, 'extras_as_string': True,
                   'schema': self._form_to_db_schema(package_type=package_type),
                   'save': 'save' in request.params}
        data_dict = {'id': id}

        #check if package exists
        try:
            c.pkg_dict = get_action('package_show')(context, data_dict)
            c.pkg = context['package']
            c.pkg_json = json.dumps(c.pkg_dict)
        except NotFound:
            abort(404, _('Dataset not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read package %s') % id)

        # Only package admins can see this page
        try:
            check_access('package_update',context)
        except NotAuthorized, e:
            abort(401, _('User %r not authorized to edit %s') % (c.user, id))

        # Load Elastic Search parameters and configuration
        self._load_elastic_config()
        self.url = self.url + c.pkg_dict.get('name')
        client = DataStoreClient(self.url)
        headers = dict()
        headers['Authorization'] = self.user.get('apikey')
        client._headers = headers

        # Now return mapping info
        try:
            response = client.mapping()
        except:
           # Error retrieving information from elastic search
            abort(404, _('Index not found on Elastic Search'))

        # In this list every resource has an specific set of items
        pkg_resources = response.get(c.pkg_dict.get('name'))

        if pkg_resources is None:
            # Dataset not found on elastic search. Abort
            abort(404, _('Dataset not found'))

        key_dict = dict()
        # We loop throught every key on every resource
        for key in pkg_resources.get('properties').keys():
            if key not in key_dict:
                # Add i18n translation of field to the dict
                key_aux = {
                  'i18n' : _(key)
                  }
                key_dict[key] = key_aux

        # Get mapping from reports
        session = model.Session()

        results = session.query(lightbaseDatasetReports,lightbaseDatasetActions.action_name).\
          filter(lightbaseDatasetReports.dataset_action_id == lightbaseDatasetActions.dataset_action_id).\
          filter(lightbaseDatasetReports.dataset_id == c.pkg_dict.get('id')).all()

        # This dict will contain all reports and mapped fields
        report_dict = dict()
        for report in results:
            # Store the action and fields necessary for this dataset
            if report[0].source:
                source = report[0].source
            else:
                source = None
            report_dict[report[0].dataset_id] = {
              report[1] : {
               'fields_list' : report[0].fields_list,
               'source' : source
              }
            }

        # Map actions options
        report_actions = session.query(lightbaseDatasetActions).all()

        # This is required to save data
        data = data or clean_dict(unflatten(tuplize_dict(parse_params(
            request.params, ignore_keys=[CACHE_PARAMETER]))))

        vars = {'data': data, 'errors': errors, 'error_summary': error_summary, 'report': report_dict, 'keys': key_dict, 'report_actions': report_actions}

        # Save data if requested
        if context.get('save') and data:
            result = self._save_report_new(data, key_dict)
            # Return error message
            if result:
                # Redirect
                h.redirect_to(controller='ckanext.lightbase.controllers.reports:lightbaseReportsController', action='report_read', id=id, report_id=self.report_id)
            else:
                # Show error message
                errors['name'] = 'Insertion error'
                error_summary[_(u'Ação')] = _(u'Erro inserindo elemento na base de dados')

        errors = errors or {}
        error_summary = error_summary or {}


        c.form = render('package/reports/new_form.html', extra_vars=vars)

        return render('package/reports/new.html')

    def _save_report_new(self, data, key_dict):
        """
        Save the new report
        """

        try:

            if not self.validate_data(data):
                raise ValidationError
            else:
                errors = ''
                error_summary = ''

            # Now get key dict to store
            key_out = dict()
            # Make sure we are parsing a list
            if type(data.get('field')) is list:
                for key in data.get('field'):
                    key_out[key] = key_dict[key]
            else:
                key_out[data.get('field')] = key_dict[data.get('field')]

            # Add fields for description and content
            key_out['content'] = data.get('content')
            key_out['description'] = data.get('description')

            # Add identifier and i18n
            key_out['identifier'] = {
              'name': data.get('identifier'),
              'i18n': data.get('identifier_i18n')
              }

            # Add field and actions to the DB
            report = lightbaseDatasetReports(
                dataset_id = data.get('dataset_id'),
                dataset_action_id = data.get('action'),
                fields_list = key_out,
                source = data.get('display')
              )

            session = model.Session
            session.add(report)
            session.commit()

            self.report_id = report.report_id

            return 1

        except ValidationError, e:
            # Add error messages to page
            errors = e.error_dict
            error_summary = e.error_summary

            return 0

        return 1

    def validate_data(self, data_dict):
        """
        Validate submitted data
        """
        return 1

    def report_read(self, id, report_id):
        # Setup dataset information
        package_type = self._get_package_type(id.split('@')[0])
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author, 'extras_as_string': True,
                   'schema': self._form_to_db_schema(package_type=package_type)}

        data_dict = {'id': id, 'report_id': report_id}

        #check if package exists
        try:
            c.pkg_dict = get_action('package_show')(context, data_dict)
            c.pkg = context['package']
            c.pkg_json = json.dumps(c.pkg_dict)
        except NotFound:
            abort(404, _('Dataset not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read package %s') % id)

        # Only package admins can see this page
        try:
            check_access('package_update',context)
        except NotAuthorized, e:
            abort(401, _('User %r not authorized to edit %s') % (c.user, id))

        # Check if report exists
        session = model.Session()

        report = session.query(lightbaseDatasetReports,lightbaseDatasetActions.action_name).\
          filter(lightbaseDatasetReports.dataset_action_id == lightbaseDatasetActions.dataset_action_id).\
          filter(lightbaseDatasetReports.report_id == report_id).all()

        if len(report) <= 0:
            abort(404, _('Report not found'))

        vars = {'report': report[0]}

        return render('package/reports/read.html', extra_vars=vars)

    def report_delete(self, id, report_id, data=None, errors=None, error_summary=None):
        """
        Controller to delete a report
        """
        # Setup dataset information
        package_type = self._get_package_type(id.split('@')[0])
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author, 'extras_as_string': True,
                   'schema': self._form_to_db_schema(package_type=package_type),
                   'save': 'save' in request.params}

        data_dict = {'id': id, 'report_id': report_id}

        #check if package exists
        try:
            c.pkg_dict = get_action('package_show')(context, data_dict)
            c.pkg = context['package']
            c.pkg_json = json.dumps(c.pkg_dict)
        except NotFound:
            abort(404, _('Dataset not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read package %s') % id)

        # Only package admins can see this page
        try:
            check_access('package_update',context)
        except NotAuthorized, e:
            abort(401, _('User %r not authorized to edit %s') % (c.user, id))

        # Check if report exists
        session = model.Session()

        report = session.query(lightbaseDatasetReports,lightbaseDatasetActions.action_name).\
          filter(lightbaseDatasetReports.dataset_action_id == lightbaseDatasetActions.dataset_action_id).\
          filter(lightbaseDatasetReports.report_id == report_id).all()

        if len(report) <= 0:
            abort(404, _('Report not found'))

        # This is required to delete data
        data = data or clean_dict(unflatten(tuplize_dict(parse_params(
            request.params, ignore_keys=[CACHE_PARAMETER]))))

        vars = {'data': data, 'errors': errors, 'error_summary': error_summary, 'report': report}

        # Save data if requested
        if context.get('save') and data:
            result = self._save_report_delete(data)
            # Return error message
            if result:
                # Redirect
                h.redirect_to(controller='ckanext.lightbase.controllers.reports:lightbaseReportsController', action='report_list', id=id)
            else:
                # Show error message
                errors['name'] = 'Insertion error'
                error_summary[_(u'Ação')] = _(u'Erro removendo elemento da base de dados')

        errors = errors or {}
        error_summary = error_summary or {}


        c.form = render('package/reports/delete_form.html', extra_vars=vars)

        return render('package/reports/delete.html', extra_vars=vars)

    def _save_report_delete(self, data):
        """
        Remove this report
        """
        try:

            if not self.validate_data(data):
                raise ValidationError
            else:
                errors = ''
                error_summary = ''

            report = model.Session.query(lightbaseDatasetReports).\
              filter(lightbaseDatasetReports.report_id == data.get('report_id')).all()

            # Remove this report
            if len(report) > 0:
                report = report[0]
                model.Session.delete(report)
                model.Session.commit()
            else:
                # Not found
                return 0

        except ValidationError, e:
            # Add error messages to page
            errors = e.error_dict
            error_summary = e.error_summary

            return 0

        return 1

    def report_list(self, id):
        # Setup dataset information
        package_type = self._get_package_type(id.split('@')[0])
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author, 'extras_as_string': True,
                   'schema': self._form_to_db_schema(package_type=package_type)}

        data_dict = {'id': id}

        #check if package exists
        try:
            c.pkg_dict = get_action('package_show')(context, data_dict)
            c.pkg = context['package']
            c.pkg_json = json.dumps(c.pkg_dict)
        except NotFound:
            abort(404, _('Dataset not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read package %s') % id)

        # Only package admins can see this page
        try:
            check_access('package_update',context)
        except NotAuthorized, e:
            abort(401, _('User %r not authorized to edit %s') % (c.user, id))

        # Check if report exists
        session = model.Session()

        report = session.query(lightbaseDatasetReports,lightbaseDatasetActions.action_name).\
          filter(lightbaseDatasetReports.dataset_action_id == lightbaseDatasetActions.dataset_action_id).\
          filter(lightbaseDatasetReports.dataset_id == c.pkg_dict.get('id')).all()

        vars = {'report_list': report}

        return render('package/reports/list.html', extra_vars=vars)
