import re

from pylons import config
import formalchemy
from formalchemy import helpers as h
from sqlalchemy.util import OrderedDict
from pylons.i18n import _, ungettext, N_, gettext

#from common import ResourcesField, TagField, ExtrasField, GroupSelectField, package_name_validator
from builder import FormBuilder
import ckan.model as model
import ckan.lib.helpers
from ckan.lib.helpers import literal

# Import package models
from ckanext.lightbase.model.reports import lightbaseDatasetActions

__all__ = ['prettify', 'build_action_form', 'get_standard_fieldset']

def prettify(field_name):
    field_name = re.sub('(?<!\w)[Uu]rl(?!\w)', 'URL', field_name.replace('_', ' ').capitalize())
    return _(field_name.replace('_', ' '))

def build_action_form(is_admin=False, user_editable_groups=None, **params):
    builder = FormBuilder(lightbaseDatasetActions)

    # Labels and instructions
    builder.set_field_text(
        'action_name',
        instructions=_('Short name for the action'),
        further_instructions=_('this is the action that will be called for rendering the data.'),
    )

    # Options/settings
    builder.set_field_option('action_name', 'validate', action_name_validator)

    # Layout
    field_groups = OrderedDict([
        (_('Basic information'), ['name']),
        ])

    builder.set_displayed_fields(field_groups)
    builder.set_label_prettifier(prettify)

    return builder

def get_standard_fieldset(is_admin=False, user_editable_groups=None, **kwargs):
    '''Returns the action fieldset (optionally with admin fields)'''

    return build_action_form(is_admin=is_admin, user_editable_groups=user_editable_groups).get_fieldset()

def action_name_validator(val, field=None):
    name_validator(val, field)

    # we disable autoflush here since may get used in dataset preview
    pkgs = model.Session.query(lightbaseDatasetActions).autoflush(False).filter_by(action_name=val)
    for pkg in pkgs:
        if pkg != field.parent.model:
            raise formalchemy.ValidationError(_('Action name already exists in database'))
