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

log = logging.getLogger(__name__)


class lightbaseAdminController(AdminController):
    """
    Add controller to log page
    """
    def log(self):
    
        import sqlalchemy
        from ckan import plugins,model
        from ckanext.datadaemon.model import setup as setup_model
        from ckanext.datadaemon.model import ErrorRepository

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
            url = '/ckan-admin/log'
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

        params=request.params
        setup_model()
        session = ckan.model.Session

        # Variáveis de entrada:
        # data: Postagem. Valores: 24, 168, 720
        # data_inicio
        # data_final
        # tipo: Tipo de Error. Valores: None, ParsingError, FileRetrievalError, FileCollectionError

        # Construir uma consulta com base nas variáveis de entrada

        # 1 - Criar consulta que traz todos os valores
        query = "SELECT e.* FROM dt_errors e WHERE 1 = 1"


        # 2 - Filtrar pela variável data. Ou eu filtro pelo período ou por data de início
        # e data de fim
        value_inicio=""
        value_final=""
        if params.get('data'):
            query = query + "AND creation_date >= (now() - interval '%s hours')" % params.get('data')
        else:
            if params.get('data_inicio'):
                query = query + "AND creation_date >= '%s'" % params.get('data_inicio')
                value_inicio = params.get('data_inicio')
            if params.get('data_final'):
                query = query + "AND creation_date <= '%s'" % params.get('data_final')
                value_final = params.get('data_final')

        # 3 - Filtrar por tipo de erro
        if params.get('tipo') == 'None':
                query = query + "AND error_type is NULL "
        elif params.get('tipo'):
            query = query + "AND error_type = '%s'" % params.get('tipo')
        # 4 - Adicionar paginação à consulta
        query_pagination = query + "ORDER BY creation_date DESC LIMIT %s OFFSET %s"  % (limit*page,(limit*page)-limit)

        error_list = session.query(ErrorRepository).from_statement(query_pagination).all()
        error_list2 = session.query(ErrorRepository).from_statement(query).all()
        error_list3 = session.query(ErrorRepository.original_file).from_statement(query_pagination).all()
        from os.path import basename
        retorno = list()
        for lista in error_list:
            lista.original_file = basename(lista.original_file)
            retorno.append(lista)

        tipos_de_erros = session.query(ErrorRepository.error_type).distinct().all()
        data = params.get('data')
        tipo = params.get('tipo')
        x = {'valor':retorno,'valor2':tipos_de_erros,'valor3':value_inicio,
        'valor4':value_final,'valor5':data,'valor6':tipo}

        c.page = h.Page(
            collection=error_list2,
            page=page,
            url=pager_url,
            item_count=len(error_list2),
            items_per_page=limit
        )
        #--------------Download do arquivo-------------
        from paste.fileapp import FileApp
        import mimetypes
        if params.get('arquivo'):
            filepath = session.query(ErrorRepository.original_file).filter(ErrorRepository.hash==params.get('arquivo')).all()
            content_type = mimetypes.guess_type(str(filepath[0][0]))
            if content_type:
                headers = [('Content-Disposition', 'attachment; filename=\"' + str(filepath[0][0]) + '\"'),
                        ('Content-Type','\'' + str(content_type[0]) + '\'')]
            else:
                headers = [('Content-Disposition', 'attachment; filename=\"' + str(filepath[0][0]) + '\"'),
                        ('Content-Type','aplication/octet-stream')]

            fapp = FileApp(str(filepath[0][0]), headers)
            return fapp(request.environ, self.start_response)
        else:
            return render('admin/log.html',extra_vars = x)
