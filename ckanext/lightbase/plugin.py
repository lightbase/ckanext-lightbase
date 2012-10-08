import os
from logging import getLogger

from pylons import request
from pylons import config
from genshi.input import HTML
from genshi.filters.transform import Transformer

from ckan.plugins import implements, SingletonPlugin
from ckan.plugins import IConfigurer
from ckan.plugins import IGenshiStreamFilter
from ckan.plugins import IRoutes
from ckan.plugins import IPackageController
from ckan.plugins import IGroupController

from ckan.logic import get_action

from datastore.client import *

log = getLogger(__name__)

# Import search controller
from ckan.lib.search import *

from ckan.logic import get_action
from datastore.client import *

from ckan.lib.base import c, model
from ckan.lib.base import _
from ckan.lib.dictization.model_dictize import package_dictize

# Import datamodel
import ckanext.lightbase.model
from ckanext.lightbase.model.reports import *
from ckanext.lightbase.model.reports import define_tables
from sqlalchemy import or_, and_, func, desc, case

define_tables()

class lightbasePlugin(SingletonPlugin):
    """This plugin demonstrates how a theme packaged as a CKAN
    extension might extend CKAN behaviour.

    In this case, we implement three extension interfaces:

      - ``IConfigurer`` allows us to override configuration normally
        found in the ``ini``-file.  Here we use it to specify the site
        title, and to tell CKAN to look in this package for templates
        and resources that customise the core look and feel.
        
      - ``IGenshiStreamFilter`` allows us to filter and transform the
        HTML stream just before it is rendered.  In this case we use
        it to rename "frob" to "foobar"
        
      - ``IRoutes`` allows us to add new URLs, or override existing
        URLs.  In this lightbase we use it to override the default
        ``/register`` behaviour with a custom controller
    """
    implements(IConfigurer, inherit=True)
    implements(IGenshiStreamFilter, inherit=True)
    implements(IRoutes, inherit=True)
    implements(IPackageController, inherit=True)

    def _load_elastic_config(self):
        """
        Load elastic search configuration
        """
        self.user = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        ckan_url = config.get('ckan.site_url').rstrip('/')
        self.url = '%s/api/data/' % (ckan_url)

        # FIXME: Parametrize this
        self.url = urlparse.urljoin(self.url, 'lbdf/')

    def update_config(self, config):
        """This IConfigurer implementation causes CKAN to look in the
        ```public``` and ```templates``` directories present in this
        package for any customisations.

        It also shows how to set the site title here (rather than in
        the main site .ini file), and causes CKAN to use the
        customised package form defined in ``package_form.py`` in this
        directory.
        """
        here = os.path.dirname(__file__)
        rootdir = os.path.dirname(os.path.dirname(here))
        our_public_dir = os.path.join(rootdir, 'ckanext',
                                      'lightbase', 'theme', 'public')
        template_dir = os.path.join(rootdir, 'ckanext',
                                    'lightbase', 'theme', 'templates')
        # set our local template and resource overrides
        config['extra_public_paths'] = ','.join([our_public_dir,
                config.get('extra_public_paths', '')])
        config['extra_template_paths'] = ','.join([template_dir,
                config.get('extra_template_paths', '')])
        # add in the extra.css
        config['ckan.template_head_end'] = config.get('ckan.template_head_end', '') +\
                                           '<link rel="stylesheet" href="/css/extra.css" type="text/css">'

    def filter(self, stream):
        """Conform to IGenshiStreamFilter interface.

        This filter renames 'frob' to 'foobar' (this string is
        found in the custom ``home/index.html`` template provided as
        part of the package).

        It also adds the chosen JQuery plugin to the page if viewing the
        dataset edit page (provides a better UX for working with tags with vocabularies)
        """
        # Add package list to menu
        self._load_elastic_config()
        client = DataStoreClient(self.url) 
        headers = dict()
        headers['Authorization'] = self.user.get('apikey')
        client._headers = headers

        # Organize the results per index
        response_indice = client.mapping()

        # FIXME: Get this from somewhere else
        response_map = response_indice.get('lbdf')

        # Create code to add to menu
        out = unicode()
        for package in response_map.keys():
            # Retrieve package info
            pkg_query = model.Session.query(model.PackageRevision)\
                .filter(model.PackageRevision.name == package)\
                .filter(and_(
                             model.PackageRevision.state == u'active',
                             model.PackageRevision.current == True
                ))
            pkg = pkg_query.first()

            ## if the index has got a package that is not in ckan then
            ## ignore it.
            if pkg:
                out = out + '\n<li><a href="/dataset/' + package + '" title="' + _('Pesquisar %s' % pkg.title)  + '">'+ pkg.title + '</a></li>'
            else:
                log.warning('package %s in index but not in database' % package)
                continue

        stream = stream | Transformer('//li[@id="package-list"]')\
                 .append(HTML(out))

        routes = request.environ.get('pylons.routes_dict')
        if routes.get('controller') == 'package' \
            and routes.get('action') == 'edit':
                stream = stream | Transformer('head').append(HTML(
                    '<link rel="stylesheet" href="/css/chosen.css" />'
                ))

        return stream


    def before_map(self, map):
        """This IRoutes implementation overrides the standard
        ``/user/register`` behaviour with a custom controller.  You
        might instead use it to provide a completely new page, for
        lightbase.

        Note that we have also provided a custom register form
        template at ``theme/templates/user/register.html``.
        """
        # Hook in our custom user controller at the points of creation
        # and edition.

		# Log page controller
        map.connect('log',
					'/ckan-admin/log',
                    controller='ckanext.lightbase.controllers.admin:lightbaseAdminController',
                    action='log'
                    )

        return map

    def after_map(self, map):
        """
        Add this after map
        """
        map.connect('read',
                    '/dataset/{id}',
                    controller='ckanext.lightbase.controllers:lightbasePackageController',
                    action='read'
                    )
        
        map.connect('read'
                    '/group/{id}',
                    controller='ckanext.lightbase.controllers:lightbaseGroupController',
                    action='read'
                    )

        map.connect('resource_read',
                    '/dataset/{id}/resource/{resource_id}',
                    controller='ckanext.lightbase.controllers:lightbasePackageController',
                    action='resource_read'
                    )

        # Controller to resource downloads
        map.connect('/dataset/{id}/resource/{resource_id}/download',
                    controller='ckanext.lightbase.controllers:lightbasePackageController',
                    action='resource_download'
                    )

        # Delete resource controller 
        map.connect('resource_delete',
                    '/dataset/{id}/resource/{resource_id}/delete',
                    controller='ckanext.lightbase.controllers:lightbasePackageController',
                    action='resource_delete'
                    )

		# Reports actions controller
        map.connect('report_action',
					'/dataset/{id}/reports/actions',
                    controller='ckanext.lightbase.controllers.reports:lightbaseReportsController',
                    action='report_action'
                    )

		# Reports actions controller
        map.connect('report_new',
					'/dataset/{id}/reports/new',
                    controller='ckanext.lightbase.controllers.reports:lightbaseReportsController',
                    action='report_new'
                    )

		# Reports actions controller
        map.connect('report_read',
					'/dataset/{id}/reports/{report_id}',
                    controller='ckanext.lightbase.controllers.reports:lightbaseReportsController',
                    action='report_read'
                    )

		# Reports actions controller
        map.connect('report_edit',
					'/dataset/{id}/reports/{report_id}/edit',
                    controller='ckanext.lightbase.controllers.reports:lightbaseReportsController',
                    action='report_edit'
                    )

		# Reports actions controller
        map.connect('report_delete',
					'/dataset/{id}/reports/{report_id}/delete',
                    controller='ckanext.lightbase.controllers.reports:lightbaseReportsController',
                    action='report_delete'
                    )

		# Reports actions controller
        map.connect('report_list',
					'/dataset/{id}/reports',
                    controller='ckanext.lightbase.controllers.reports:lightbaseReportsController',
                    action='report_list'
                    )


        return map

class lightbasePackageSearch(SingletonPlugin):
    """
    Change Package search results
    """
    implements(IPackageController, inherit=True)

    def _load_elastic_config(self):
        """
        Load elastic search configuration
        """
        self.user = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        ckan_url = config.get('ckan.site_url').rstrip('/')
        self.url = '%s/api/data/' % (ckan_url)

        # FIXME: Parametrize this
        self.url = urlparse.urljoin(self.url, 'lbdf/')

    def before_search(self, search_params):
        '''
            Extensions will receive the search results, as well as the search
            parameters, and should return a modified (or not) object with the
            same structure:

                {'count': '', 'results': '', 'facets': ''}

            Note that count and facets may need to be adjusted if the extension
            changed the results for some reason.

            search_params will include an `extras` dictionary with all values
            from fields starting with `ext_`, so extensions can receive user
            input from specific fields.
            
            The extension will just send the same parameters to elastic search
            and it will organize the results in packages.
        '''
        import urlparse

        # Remember to abort search
        search_results = dict()
        search_results['abort_search'] = True

        q = search_params['q'] # unicode format (decoded from utf8)

        # If we don't have these parameters supply default values
        if search_params.get('rows') is None or search_params.get('rows') == 0:
            search_params['rows'] = 20

        if search_params.get('start') is None:
            search_params['start'] = 0

        # format q to send to elastic search
        if q is u'' or q is '*:*':
            query = {
                     "sort": {
                        "data" : {"order" : "desc"},
                      },
                     "query": {
                               "match_all":{}
                               },
                     "size" : search_params['rows'],
                     "from" : search_params['start']
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
                     "size" : search_params['rows'],
                     "from" : search_params['start']
            }


        context = {'model': model, 'session': model.Session,
                       'user': c.user or c.author}

        session = model.Session

        self._load_elastic_config()
        client = DataStoreClient(self.url)
        headers = dict()
        headers['Authorization'] = self.user.get('apikey')
        client._headers = headers

        # Now run search

        # do not fail on search errors
        try:
            response = client.query(query)
        except:
            # There's an error in search params

            import traceback
            response = dict()
            errmsg = 'Error searching query string \n %s \n Message\n%s' % (query,traceback.format_exc())
            log.error(errmsg)

            raise SearchError(errmsg)

        # Organize the results per index
        response_dict = client.mapping()

        # FIXME: Get this as a parameters
        response_map = response_dict.get('lbdf')

        results = list()
        package_list = list()
        count = 0
        result_dict = dict()
        result_pkg = dict()

        # Now we have to parse the result back to package dict
        hits = response.get('hits')
        if hits is not None:
            for res in hits.get('hits'):
                # get DB information for the found package
                #package = res['_index']

                # Now we use type
                package = res['_type']

                # I have to organize results per dataset
                if package in package_list:
                    # This case this package was already retrieved. Just add
                    # resources to the list
                    #resources.append(res['_source'])
                    #result_dict['elastic_resources'] = resources
                    result_pkg[package]['elastic_resources'].append(res['_source'])
                else:
                    #  Add to results this package information if we are not starting
                    #if count > 0:
                        #results.append(result_dict)

                    # I don't have package. Retrieve package info
                    # and create resources list
                    pkg_query = session.query(model.PackageRevision)\
                        .filter(model.PackageRevision.name == package)\
                        .filter(and_(
                                     model.PackageRevision.state == u'active',
                                     model.PackageRevision.current == True
                        ))
                    pkg = pkg_query.first()

                    ## if the index has got a package that is not in ckan then
                    ## ignore it.
                    if not pkg:
                        log.warning('package %s in index but not in database' % package)
                        continue

                    result_dict = package_dictize(pkg,context)

                    # Add resource information
                    resources = list()
                    resources.append(res['_source'])
                    result_dict['elastic_resources'] = resources
                    # FIXME: it doesn't work. Have to find a better alogorithm to count the hits
                    result_dict['elastic_hits'] = len(response_map[package])
                    count += 1

                    # TODO: Parametrize this
                    action_name = 'package_search'

                    # Get fields list for this action
                    report = session.query(lightbaseDatasetReports).\
                      filter(lightbaseDatasetReports.dataset_action_id == lightbaseDatasetActions.dataset_action_id).\
                      filter(lightbaseDatasetReports.dataset_id == pkg.id).\
                      filter(lightbaseDatasetActions.action_name == action_name).all()

                    # Add fields to dict
                    report_dict = dict()
                    if len(report) > 0:
                        report_dict = report[0].fields_list

                    # This is not used
                    report_dict.pop('content')

                    # Add it to page
                    identifier = report_dict.pop('identifier')
                    result_dict['report_dict'] = report_dict
                    result_dict['identifier'] = identifier

                    result_pkg[package] = result_dict

                    # The count is about datasets on this part
                    package_list.append(package)

        else:
            hits = dict()
            hits['total'] = 0

        # Always add manually the last package
        #results.append(result_dict)

        # if we don't have one result in packages list, add it without results
        results = list()
        for package_elm in response_map.keys():
            # Check if this element is on package list
            if package_elm not in package_list:
                # I don't have package. Retrieve package info
                # and create resources list
                pkg_query = session.query(model.PackageRevision)\
                    .filter(model.PackageRevision.name == package_elm)\
                    .filter(and_(
                                 model.PackageRevision.state == u'active',
                                 model.PackageRevision.current == True
                    ))
                pkg = pkg_query.first()

                ## if the index has got a package that is not in ckan then
                ## ignore it.
                if not pkg:
                    log.warning('package %s in index but not in database' % package_elm)
                    continue

                result_dict = package_dictize(pkg,context)

                # Add resource information
                resources = list()
                result_dict['elastic_resources'] = resources
                result_dict['elastic_hits'] = len(response_map[package_elm])

                # TODO: Parametrize this
                action_name = 'package_search'

                # Get fields list for this action
                report = session.query(lightbaseDatasetReports).\
                  filter(lightbaseDatasetReports.dataset_action_id == lightbaseDatasetActions.dataset_action_id).\
                  filter(lightbaseDatasetReports.dataset_id == pkg.id).\
                  filter(lightbaseDatasetActions.action_name == action_name).all()

                # Add fields to dict
                report_dict = dict()
                if len(report) > 0:
                    report_dict = report[0].fields_list

                # This is not used
                report_dict.pop('content')

                # Add it to page
                identifier = report_dict.pop('identifier')
                result_dict['report_dict'] = report_dict
                result_dict['identifier'] = identifier

                # Add it to results list
                results.append(result_dict)
            else:
                results.append(result_pkg[package_elm])

        # Adjust parameters to return to the page
        search_results['count'] = hits.get('total')
        search_results['results'] = results

        # TODO: Implement facets on elastic search as this links in the docs:
        #  http://www.elasticsearch.org/guide/reference/api/search/facets/
        search_results['facets'] = []

        return search_results
