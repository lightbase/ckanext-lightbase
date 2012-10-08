from setuptools import setup, find_packages

version = '0.3'

setup(
	name='ckanext-lightbase',
	version=version,
	description='Lightbase extension for customising CKAN',
	long_description='',
	classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
	keywords='',
	author='Eduardo Santos',
	author_email='eduardo.edusantos@lightbase.com.br',
	url='',
	license='CC-GPL v2.0 pt-br',
	packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
	namespace_packages=['ckanext', 'ckanext.lightbase'],
	include_package_data=True,
	zip_safe=False,
	install_requires=[],
    message_extractors = {
        'ckanext/lightbase': [
            ('**.py', 'python', None),
            ('theme/templates/**.html', 'genshi', None),
            ('theme/templates/**.txt', 'genshi', {
                'template_class': 'genshi.template:TextTemplate'
            }),
            ('theme/public/**', 'ignore', None),
        ]},
	entry_points=\
	"""
        [ckan.plugins]
	    lightbase=ckanext.lightbase.plugin:lightbasePlugin
	    lightbase_package_search=ckanext.lightbase.plugin:lightbasePackageSearch
        lightbase_datasetform=ckanext.lightbase.forms:lightbaseDatasetForm
        lightbase_groupform=ckanext.lightbase.forms:lightbaseGroupForm        

        [ckan.forms]
        lightbase_form = ckanext.lightbase.package_form:get_lightbase_fieldset

        [paste.paster_command]
        lightbase=ckanext.lightbase.commands:lightbaseCommand
	""",
)
