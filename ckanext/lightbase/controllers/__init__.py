import sys
import os
from ckan.lib.base import request
from ckan.lib.base import c, g, h
from ckan.lib.base import model
from ckan.lib.base import render
from ckan.lib.base import _
from ckan.lib.base import BaseController

from ckan.lib.navl.validators import not_empty

from ckan.controllers.user import UserController

# Imports
from ckan.logic import get_action
from datastore.client import *
from ckan.controllers.group import GroupController
from ckan.controllers.package import PackageController
from ckan.controllers.home import HomeController
from ckan.controllers.admin import AdminController
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

from lxml.html import fromstring, tostring
from ckanext.lightbase.util.text_to_html import *
from urllib import urlencode

import i18n

# Import datamodel
import ckanext
import ckanext.lightbase
import ckanext.lightbase.model
from ckanext.lightbase.model.reports import *
from ckanext.lightbase.model.reports import setup as setup_model

setup_model()

log = logging.getLogger(__name__)


class CustomUserController(UserController):
    """This controller is an lightbase to show how you might extend or
    override core CKAN behaviour from an extension package.

    It overrides 2 method hooks which the base class uses to create the
    validation schema for the creation and editing of a user; to require
    that a fullname is given.
    """

    new_user_form = 'user/register.html'

    def _add_requires_full_name_to_schema(self, schema):
        """
        Helper function that modifies the fullname validation on an existing schema
        """
        schema['fullname'] = [not_empty, unicode]

    def _new_form_to_db_schema(self):
        """
        Defines a custom schema that requires a full name to be supplied

        This method is a hook that the base class calls for the validation
        schema to use when creating a new user.
        """
        schema = super(CustomUserController, self)._new_form_to_db_schema()
        self._add_requires_full_name_to_schema(schema)
        return schema

    def _edit_form_to_db_schema(self):
        """
        Defines a custom schema that requires a full name cannot be removed
        when editing the user.

        This method is a hook that the base class calls for the validation
        schema to use when editing an exiting user.
        """
        schema = super(CustomUserController, self)._edit_form_to_db_schema()
        self._add_requires_full_name_to_schema(schema)
        return schema
    
class lightbasePackageController(PackageController):
    """This controller will change datasets"""
    def read(self, id):
        package_type = self._get_package_type(id.split('@')[0])
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author, 'extras_as_string': True,
                   'schema': self._form_to_db_schema(package_type=package_type)}
        data_dict = {'id': id}

        # interpret @<revision_id> or @<date> suffix
        split = id.split('@')
        if len(split) == 2:
            data_dict['id'], revision_ref = split
            if model.is_id(revision_ref):
                context['revision_id'] = revision_ref
            else:
                try:
                    date = date_str_to_datetime(revision_ref)
                    context['revision_date'] = date
                except TypeError, e:
                    abort(400, _('Invalid revision format: %r') % e.args)
                except ValueError, e:
                    abort(400, _('Invalid revision format: %r') % e.args)
        elif len(split) > 2:
            abort(400, _('Invalid revision format: %r') % 'Too many "@" symbols')
            
        #check if package exists
        try:
            c.pkg_dict = get_action('package_show')(context, data_dict)
            c.pkg = context['package']
            c.pkg_json = json.dumps(c.pkg_dict)
        except NotFound:
            abort(404, _('Dataset not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read package %s') % id)
        
        #set a cookie so we know whether to display the welcome message
        c.hide_welcome_message = bool(request.cookies.get('hide_welcome_message', False))
        response.set_cookie('hide_welcome_message', '1', max_age=3600) #(make cross-site?)

        # used by disqus plugin
        c.current_package_id = c.pkg.id

        # Add the package's activity stream (already rendered to HTML) to the
        # template context for the package/read.html template to retrieve
        # later.
        c.package_activity_stream = \
                ckan.logic.action.get.package_activity_list_html(context,
                    {'id': c.current_package_id})

        if config.get('rdf_packages'):
            accept_header = request.headers.get('Accept', '*/*')
            for content_type, exts in negotiate(autoneg_cfg, accept_header):
                if "html" not in exts: 
                    rdf_url = '%s%s.%s' % (config['rdf_packages'], c.pkg.id, exts[0])
                    redirect(rdf_url, code=303)
                break

        # Adding pagination
        q = c.q = request.params.get('q', u'') # unicode format (decoded from utf8)
        try:
            page = int(request.params.get('page', 1))
        except ValueError, e:
            abort(400, ('"page" parameter must be an integer'))
        limit = 20

        # most search operations should reset the page counter:
        params_nopage = [(k, v) for k,v in request.params.items() if k != 'page']

        def search_url(params):
            url = '/dataset/' + c.pkg_dict.get('name')
            params = [(k, v.encode('utf-8') if isinstance(v, basestring) else str(v)) \
                            for k, v in params]
            return url + u'?' + urlencode(params)

        
        def drill_down_url(**by):
            params = list(params_nopage)
            params.extend(by.items())
            return search_url(set(params))
        
        c.drill_down_url = drill_down_url 
        
        def remove_field(key, value):
            params = list(params_nopage)
            params.remove((key, value))
            return search_url(params)

        c.remove_field = remove_field
        
        def pager_url(q=None, page=None):
            params = list(params_nopage)
            params.append(('page', page))
            return search_url(params)

        c.query_error = False

        try:
            # Change returned package dict
            c.pkg_dict = self.before_view(c.pkg_dict)

            c.page = h.Page(
                collection=c.pkg_dict.get('elastic_resources'),
                page=page,
                url=pager_url,
                item_count=c.pkg_dict.get('elastic_hits'),
                items_per_page=limit
            )

        except SearchError, se:
            log.error('Dataset search error: %r', se.args)
            c.query_error = True
            c.facets = {}
            c.page = h.Page(collection=[])

        # TODO: Find another way to get this action
        action_name = 'read'

        # Get fields list for this action
        report = model.Session.query(lightbaseDatasetReports).\
          filter(lightbaseDatasetReports.dataset_action_id == lightbaseDatasetActions.dataset_action_id).\
          filter(lightbaseDatasetReports.dataset_id == c.pkg_dict.get('id')).\
          filter(lightbaseDatasetActions.action_name == action_name).all()

        # Add fields to dict
        report_dict = dict()
        if len(report) > 0:
            report_dict = report[0].fields_list

        # These are not necessary for now
        report_dict.pop('content')
        report_dict.pop('description')

        # Add it to page
        identifier = report_dict.pop('identifier')
        vars = {'report_dict': report_dict, 'identifier': identifier}

        PackageSaver().render_package(c.pkg_dict, context)
        return render('package/read.html', extra_vars=vars)

    def resource_read(self, id, resource_id):
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}

        try:
            c.resource = get_action('resource_show')(context, {'id': resource_id})
            c.package = get_action('package_show')(context, {'id': id})
            # required for nav menu
            c.pkg = context['package']
            c.resource_json = json.dumps(c.resource)
            c.pkg_dict = c.package
        except NotFound:
            abort(404, _('Resource not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read resource %s') % id)
        # get package license info
        license_id = c.package.get('license_id')
        try:
            c.package['isopen'] = model.Package.get_license_register()[license_id].isopen()
        except KeyError:
            c.package['isopen'] = False

        # TODO: Find another way to get this action
        action_name = 'resource_read'

        # Get fields list for this action
        report = model.Session.query(lightbaseDatasetReports).\
          filter(lightbaseDatasetReports.dataset_action_id == lightbaseDatasetActions.dataset_action_id).\
          filter(lightbaseDatasetReports.dataset_id == c.pkg_dict.get('id')).\
          filter(lightbaseDatasetActions.action_name == action_name).all()

        # Add fields to dict
        report_dict = dict()
        if len(report) > 0:
            report_dict = report[0].fields_list

        # Add it to page
        identifier = report_dict.pop('identifier')
        vars = {'report_dict': report_dict, 'identifier': identifier}

        # Add results from elastic search
        c.resource['elastic_search'] = self.before_view_resource(c.pkg_dict['name'], c.resource['name'])

        # Get item name from description item
        c.resource['description'] = c.resource['elastic_search'].get(report_dict.pop('description'))

        # Get content from content item in dict
    	conteudo = plaintext2html(c.resource['elastic_search'].get(report_dict.pop('content')))

    	# Check if conteudo is nil
    	if not conteudo:
    		c.resource['conteudo'] = unicode('Nao disponivel')
    	else:
    		conteudo_html = fromstring(conteudo)
    		conteudo = tostring(conteudo_html)
    		c.resource['conteudo'] = unicode(conteudo)

        return render('package/resource_read.html', extra_vars=vars)

    def resource_download(self, id, resource_id):
        """
        Download file
        """
        from paste.fileapp import FileApp
        from paste.fileapp import DataApp
        import urllib
        
	    # TODO: Remove this from here
        fpath = '/srv/ckan-data/files'
        
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}

        try:
            c.resource = get_action('resource_show')(context, {'id': resource_id})
            c.package = get_action('package_show')(context, {'id': id})
            # required for nav menu
            c.pkg = context['package']
            c.resource_json = json.dumps(c.resource)
            c.pkg_dict = c.package
        except NotFound:
            abort(404, _('Resource not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read resource %s') % id)

        elastic_search = self.before_view_resource(c.pkg_dict['name'], c.resource['name'])

        if 'arquivo' not in elastic_search:
            # Not found. Return an error message
            abort(404, _('Resource not found'))

        filename = '%s/%s' % (fpath, elastic_search['arquivo'])
        file_size = os.path.getsize(filename)

        headers = [(str('Content-Disposition'), str('attachment; filename=\"' + elastic_search['arq_original'] + '\"')),
                   (str('Content-Type'), str('text/plain')),
                   (str('Content-Length'), str(file_size))]

        '''fapp = FileApp(filename, headers=headers)
        return fapp(request.environ, self.start_response)'''

        url = 'http://www.aquabarra.com.br/artigos/treinamento/Antropometria.pdf'
        filename,headers2=urllib.urlretrieve(url)
        fapp = FileApp(filename, headers)
        return fapp(request.environ, self.start_response)

    def resource_delete(self, id, resource_id):
        """
        Delete resource
        """
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}

        # FIXME: Add this as a standard permission control.
        # For now just check if user is admin
        c.is_sysadmin = Authorizer().is_sysadmin(c.user)

        if not c.is_sysadmin:
            # Return not Authorized
            abort(401, _('Unauthorized to delete resource %s') % resource_id)

        try:
            c.resource = get_action('resource_show')(context, {'id': resource_id})
            c.package = get_action('package_show')(context, {'id': id})
            # required for nav menu
            c.pkg = context['package']
            c.resource_json = json.dumps(c.resource)
            c.pkg_dict = c.package
        except NotFound:
            abort(404, _('Resource not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read resource %s') % id)

        # Remove resource from package dict
        api_url = urlparse.urljoin(config.get('ckan.site_url'), 'api')
        user = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        ckan = ckanclient.CkanClient(
                                     base_location=api_url,
                                     api_key=user.get('apikey'),
                                     is_verbose=True,
                                    )

        package_entity = ckan.package_entity_get(id)

        # FIXME: The only way is to loop through resources list
        # It's incredibly slow. Have to fix it
        resources_list = list()
        for resource in package_entity['resources']:
            if resource['name'] != resource_id:
                # On this case add this resource to the list
                resources_list.append(resource)

        # Add resource as an element for package. It's the only way to save
        package_entity['resources'] = resources_list
        
        # This will update the package in package_entity
        ckan.package_entity_put(package_entity)

        # Remove resource from Elastic Search
        ckan_url = config.get('ckan.site_url').rstrip('/')
        webstore_request_url = '%s/api/data/%s/%s' % (ckan_url, id, resource_id)
        client = DataStoreClient(webstore_request_url)
        out = client.delete()

        # Remove resource on Ckan
        session = model.Session
        
        # First remove revisions
        revision_query = session.query(model.ResourceRevision)\
            .filter(model.ResourceRevision.name == resource_id).all()

        for revision_obj in revision_query:
            #session.delete(revision_obj)
            model.repo.purge_revision(revision_obj, leave_record=False)

        session.commit()

        # Now remove resources
        resource_query = session.query(model.Resource)\
            .filter(model.Resource.name == resource_id)

        resource_obj = resource_query.first()
        session.delete(resource_obj)

        session.commit()

        # Redirect after removal
        h.redirect_to(controller="ckanext.lightbase.controllers:lightbasePackageController", action="read", id=id, q="id: "+resource_id)

    def _load_elastic_config(self):
        """
        Load elastic search configuration
        """
        self.user = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        ckan_url = config.get('ckan.site_url').rstrip('/')
        self.url = '%s/api/data/' % (ckan_url)

        # FIXME: Parametrize this
        self.url = urlparse.urljoin(self.url, 'lbdf/')

    def before_view(self,pkg_dict):
        """
        Extend the group controller to show resource information
        The resource information will come from elastic search
        """
        # use r as query string
        q = c.q = request.params.get('q', default=None) # unicode format (decoded from utf8)
        page = c.page =  request.params.get('page', default=None)

        # TODO: put this as a parameter
        rows = 20

        if page is None:
            start = 0
        else:
            # Start with the first element in this page
            start = ((int(page) * rows) - rows)

        # format q to send to elastic search
        if q is None or q is '*:*':
            query = {
                     "sort": {
                        "data" : {"order" : "desc"},
                      },
                     "query": {
                               "match_all":{}
                               },
                     "size" : rows,
                     "from" : start
            }
        else:
            query = {
                     "sort": {
                        "data" : {"order" : "desc"},
                      },
                     "query": {
                                "query_string": {
                                                 "query": q,
                                                 "default_operator": "AND"
                                                 }
                               },
                     "size" : rows,
                     "from" : start
            }

        # Now send query to elastic search
        self._load_elastic_config()
        client = DataStoreClient(urlparse.urljoin(self.url, pkg_dict['name']))
        headers = dict()
        headers['Authorization'] = self.user.get('apikey')
        #req = urllib2.Request(webstore_request_url, post_data, headers)
        client._headers = headers

        # do not fail on search errors
        try:
            response = client.query(query)
        except:
            # there's an error in search params
            import traceback
            response = dict()
            errmsg = 'Error searching query string \n %s \n Message\n%s' % (query,traceback.format_exc())
            log.error(errmsg)

            raise SearchError(errmsg)
        
        
        # Now we have to parse the result back to package dict
        hits = response.get('hits')
        resources = list()
        if hits is not None:
            for res in hits['hits']:
                # Store it in extras
                resources.append(res['_source'])
        
            # Add a new field on pkg_dict
            pkg_dict['elastic_resources'] = resources
            pkg_dict['elastic_hits'] = hits.get('total')

        else:
            # Add a new field on pkg_dict
            pkg_dict['elastic_resources'] = dict()
            pkg_dict['elastic_hits'] = 0

        return pkg_dict
    
    def before_view_resource(self,pkg_name,resource_id):
        """
        Extend the group controller to show resource information
        The resource information will come from elastic search
        """
        query = {
                "query": {
                          "query_string": {
                           "default_field":  "id",
                           "query": resource_id
                           }
                },
                "size":"1"
        }
        
        # Now send query to elastic search
        self._load_elastic_config()
        self.url = urlparse.urljoin(self.url, pkg_name)
        client = DataStoreClient(self.url)
        headers = dict()
        headers['Authorization'] = self.user.get('apikey')
        #req = urllib2.Request(webstore_request_url, post_data, headers)
        client._headers = headers
        response = client.query(query)
        
        # Now we have to parse the result back to package dict
        hits = response.get('hits')
        resources = dict()
        for res in hits['hits']:
            # Store it in extras
            resources = res['_source']
            # Return only first item
            break

        # Check not found
        if not resources:
            abort(404, _('Resource not found'))
        else:
            return resources
    
class lightbaseGroupController(GroupController):
    """
    Create an specific controller to show groups
    """

    def read(self, id):
        group_type = self._get_group_type(id.split('@')[0])
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author,
                   'schema': self._form_to_db_schema(group_type=type)}
        data_dict = {'id': id}
        q = c.q = request.params.get('q', '') # unicode format (decoded from utf8)

        try:
            c.group_dict = get_action('group_show')(context, data_dict)
            c.group = context['group']
        except NotFound:
            abort(404, _('Group not found'))
        except NotAuthorized:
            abort(401, _('Unauthorized to read group %s') % id)

        # Search within group
        q += ' groups: "%s"' % c.group_dict.get('name')

        try:
            description_formatted = ckan.misc.MarkdownFormat().to_html(c.group_dict.get('description',''))
            c.description_formatted = genshi.HTML(description_formatted)
        except Exception, e:
            error_msg = "<span class='inline-warning'>%s</span>" % _("Cannot render description")
            c.description_formatted = genshi.HTML(error_msg)
        
        c.group_admins = self.authorizer.get_admins(c.group)

        context['return_query'] = True

        limit = 20
        try:
            page = int(request.params.get('page', 1))
        except ValueError, e:
            abort(400, ('"page" parameter must be an integer'))
            
        # most search operations should reset the page counter:
        params_nopage = [(k, v) for k,v in request.params.items() if k != 'page']

        def search_url(params):
            url = h.url_for(controller='group', action='read', id=c.group_dict.get('name'))
            params = [(k, v.encode('utf-8') if isinstance(v, basestring) else str(v)) \
                            for k, v in params]
            return url + u'?' + urlencode(params)

        def drill_down_url(**by):
            params = list(params_nopage)
            params.extend(by.items())
            return search_url(set(params))
        
        c.drill_down_url = drill_down_url 
        
        def remove_field(key, value):
            params = list(params_nopage)
            params.remove((key, value))
            return search_url(params)

        c.remove_field = remove_field

        def pager_url(q=None, page=None):
            params = list(params_nopage)
            params.append(('page', page))
            return search_url(params)

        try:
            c.fields = []
            search_extras = {}
            for (param, value) in request.params.items():
                if not param in ['q', 'page'] \
                        and len(value) and not param.startswith('_'):
                    if not param.startswith('ext_'):
                        c.fields.append((param, value))
                        q += ' %s: "%s"' % (param, value)
                    else:
                        search_extras[param] = value

            data_dict = {
                'q':q,
                'facet.field':g.facets,
                'rows':limit,
                'start':(page-1)*limit,
                'extras':search_extras
            }

            query = get_action('package_search')(context,data_dict)

            c.page = h.Page(
                collection=query['results'],
                page=page,
                url=pager_url,
                item_count=query['count'],
                items_per_page=limit
            )
            c.facets = query['facets']
            c.page.items = query['results']
        except SearchError, se:
            log.error('Group search error: %r', se.args)
            c.query_error = True
            c.facets = {}
            c.page = h.Page(collection=[])

        # Add the group's activity stream (already rendered to HTML) to the
        # template context for the group/read.html template to retrieve later.
        c.group_activity_stream = \
                ckan.logic.action.get.group_activity_list_html(context,
                    {'id': c.group_dict['id']})

        # Change returned dict
        c.page.items = self.before_view(c.page.items)

        return render('group/read.html')

    def _load_elastic_config(self):
        """
        Load elastic search configuration
        """
        self.user = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        ckan_url = config.get('ckan.site_url').rstrip('/')
        self.url = '%s/api/data' % (ckan_url)

        # FIXME: Parametrize this
        self.url = urlparse.urljoin(self.url, 'lbdf/')


    def before_view(self,pkg_dict):
        """
        Extend the group controller to show resource information
        The resource information will come from elastic search
        """
        # use r as query string
        r = c.r = request.params.get('r', default=None) # unicode format (decoded from utf8)
        
        # format r to send to elastic search
        if r is None:
            query = {
                     "sort": {
                        "data" : {"order" : "desc"},
                      },
                     "query": {
                               "match_all":{}
                               }
            }
        else:
            query = {
                     "sort": {
                        "data" : {"order" : "desc"},
                      },
                     "query":{r}
                     }
        
        # Now send query to elastic search
        self._load_elastic_config()
        client = DataStoreClient(urlparse.urljoin(self.url, pkg_dict['name'])) 
        headers = dict()
        headers['Authorization'] = self.user.get('apikey')
        #req = urllib2.Request(webstore_request_url, post_data, headers)
        client._headers = headers
        response = client.query(query)
        
        # Now we have to parse the result back to package dict
        hits = response.get('hits')
        resources = list()
        for res in hits['hits']:
            # Store it in extras
            resources.append(res['_source'])
        
        # Add a new field on pkg_dict
        pkg_dict['elastic_resources'] = resources
        
        return pkg_dict

