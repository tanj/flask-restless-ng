# manager.py - class that creates endpoints compliant JSON API
#
# Copyright 2011 Lincoln de Sousa <lincoln@comum.org>.
# Copyright 2012, 2013, 2014, 2015, 2016 Jeffrey Finkelstein
#           <jeffrey.finkelstein@gmail.com> and contributors.
#
# This file is part of Flask-Restless.
#
# Flask-Restless is distributed under both the GNU Affero General Public
# License version 3 and under the 3-clause BSD license. For more
# information, see LICENSE.AGPL and LICENSE.BSD.
"""Provides the main class with which users of Flask-Restless interact.

The :class:`APIManager` class allow users to create ReSTful APIs for
their SQLAlchemy models.

"""
import math
from collections import Iterable
from collections import defaultdict
from collections import namedtuple
from uuid import uuid1

from flask import Blueprint
from sqlalchemy.orm.exc import MultipleResultsFound
from sqlalchemy.orm.exc import NoResultFound

from .exceptions import BadRequest
from .exceptions import NotFound
from .helpers import collection_name
from .helpers import get_by
from .helpers import model_for
from .helpers import primary_key_for
from .helpers import primary_key_names
from .helpers import url_for
from .search import ComparisonToNull
from .search import UnknownField
from .search import search
from .serialization import DefaultDeserializer
from .serialization import FastSerializer
from .serialization import SerializationException
from .views import API
from .views import FunctionAPI
from .views import RelationshipAPI
from .views.base import JSONAPI_VERSION
from .views.base import MultipleExceptions
from .views.base import Paginated
from .views.base import resources_from_path
from .views.helpers import count

#: The names of HTTP methods that allow fetching information.
READONLY_METHODS = frozenset(('GET', ))

#: The names of HTTP methods that allow creating, updating, or deleting
#: information.
WRITEONLY_METHODS = frozenset(('PATCH', 'POST', 'DELETE'))

#: The set of all recognized HTTP methods.
ALL_METHODS = READONLY_METHODS | WRITEONLY_METHODS

#: The default URL prefix for APIs created by instance of :class:`APIManager`.
DEFAULT_URL_PREFIX = '/api'

STRING_TYPES = (str, )

#: A triple that stores the SQLAlchemy session and the universal pre- and post-
#: processors to be applied to any API created for a particular Flask
#: application.
#:
#: These tuples are used by :class:`APIManager` to store information about
#: Flask applications registered using :meth:`APIManager.init_app`.
# RestlessInfo = namedtuple('RestlessInfo', ['session',
#                                            'universal_preprocessors',
#                                            'universal_postprocessors'])

#: A tuple that stores information about a created API.
#:
#: The elements are, in order,
#:
#: - `collection_name`, the name by which a collection of instances of
#:   the model exposed by this API is known,
#: - `blueprint_name`, the name of the blueprint that contains this API,
#: - `serializer`, the subclass of :class:`Serializer` provided for the
#:   model exposed by this API.
#: - `primary_key`, the primary key used by the model
#: - `url_prefix`, the url prefix to use for the collection
#:
APIInfo = namedtuple('APIInfo', ['collection_name', 'blueprint_name', 'serializer',
                                 'primary_key', 'url_prefix'])


class IllegalArgumentError(Exception):
    """This exception is raised when a calling function has provided illegal
    arguments to a function or method.

    """
    pass


class APIManager(object):
    """Provides a method for creating a public ReSTful JSON API with respect
    to a given :class:`~flask.Flask` application object.

    The :class:`~flask.Flask` object can either be specified in the
    constructor, or after instantiation time by calling the
    :meth:`init_app` method.

    `app` is the :class:`~flask.Flask` object containing the user's
    Flask application.

    `session` is the :class:`~sqlalchemy.orm.session.Session` object in
    which changes to the database will be made.

    `flask_sqlalchemy_db` is the :class:`~flask.ext.sqlalchemy.SQLAlchemy`
    object with which `app` has been registered and which contains the
    database models for which API endpoints will be created.

    If `flask_sqlalchemy_db` is not ``None``, `session` will be ignored.

    For example, to use this class with models defined in pure SQLAlchemy::

        from flask import Flask
        from flask.ext.restless import APIManager
        from sqlalchemy import create_engine
        from sqlalchemy.orm.session import sessionmaker

        engine = create_engine('sqlite:////tmp/mydb.sqlite')
        Session = sessionmaker(bind=engine)
        mysession = Session()
        app = Flask(__name__)
        apimanager = APIManager(app, session=mysession)

    and with models defined with Flask-SQLAlchemy::

        from flask import Flask
        from flask.ext.restless import APIManager
        from flask.ext.sqlalchemy import SQLAlchemy

        app = Flask(__name__)
        db = SQLALchemy(app)
        apimanager = APIManager(app, flask_sqlalchemy_db=db)

    `url_prefix` is the URL prefix at which each API created by this
    instance will be accessible. For example, if this is set to
    ``'foo'``, then this method creates endpoints of the form
    ``/foo/<collection_name>`` when :meth:`create_api` is called. If the
    `url_prefix` is set in the :meth:`create_api`, the URL prefix set in
    the constructor will be ignored for that endpoint.

    `postprocessors` and `preprocessors` must be dictionaries as
    described in the section :ref:`processors`. These preprocessors and
    postprocessors will be applied to all requests to and responses from
    APIs created using this APIManager object. The preprocessors and
    postprocessors given in these keyword arguments will be prepended to
    the list of processors given for each individual model when using
    the :meth:`create_api_blueprint` method (more specifically, the
    functions listed here will be executed before any functions
    specified in the :meth:`create_api_blueprint` method). For more
    information on using preprocessors and postprocessors, see
    :ref:`processors`.

    """

    #: The format of the name of the API view for a given model.
    #:
    #: This format string expects the name of a model to be provided when
    #: formatting.
    APINAME_FORMAT = '{0}api'

    def __init__(self, app=None, session=None, flask_sqlalchemy_db=None,
                 preprocessors=None, postprocessors=None, url_prefix=None):
        if session is None and flask_sqlalchemy_db is None:
            msg = 'must specify either `flask_sqlalchemy_db` or `session`'
            raise ValueError(msg)

        self.app = app

        # Stash this instance so that it can be examined later by the global
        # `url_for`, `model_for`, and `collection_name` functions.
        #
        # TODO This is a bit of poor code style because it requires the
        # APIManager to know about these global functions that use it.
        url_for.register(self)
        model_for.register(self)
        collection_name.register(self)
        primary_key_for.register(self)

        #: A mapping whose keys are models for which this object has
        #: created an API via the :meth:`create_api_blueprint` method
        #: and whose values are the corresponding collection names for
        #: those models.
        self.created_apis_for = {}

        #: List of blueprints created by :meth:`create_api` to be registered
        #: to the app when calling :meth:`init_app`.
        self.blueprints = []

        # If a Flask-SQLAlchemy object is provided, prefer the session
        # from that object.
        if flask_sqlalchemy_db is not None:
            session = flask_sqlalchemy_db.session

        # pre = preprocessors or {}
        # post = postprocessors or {}
        # self.restless_info = RestlessInfo(session, pre, post)
        self.pre = preprocessors or {}
        self.post = postprocessors or {}
        self.session = session

        #: The default URL prefix for APIs created by this manager.
        #:
        #: This can be overriden by the `url_prefix` keyword argument in the
        #: :meth:`create_api` method.
        self.url_prefix = url_prefix

        # if self.app is not None:
        #     self.init_app(self.app)

    @staticmethod
    def api_name(collection_name):
        """Returns the name of the :class:`API` instance exposing models of the
        specified type of collection.

        `collection_name` must be a string.

        """
        return APIManager.APINAME_FORMAT.format(collection_name)

    def model_for(self, collection_name):
        """Returns the SQLAlchemy model class whose type is given by the
        specified collection name.

        `collection_name` is a string containing the collection name as
        provided to the ``collection_name`` keyword argument to
        :meth:`create_api_blueprint`.

        The collection name should correspond to a model on which
        :meth:`create_api_blueprint` has been invoked previously. If it doesn't
        this method raises :exc:`ValueError`.

        This method is the inverse of :meth:`collection_name`::

            >>> from mymodels import Person
            >>> manager.create_api(Person, collection_name='people')
            >>> manager.collection_name(manager.model_for('people'))
            'people'
            >>> manager.model_for(manager.collection_name(Person))
            <class 'mymodels.Person'>

        """
        # Reverse the dictionary.
        models = {info.collection_name: model for model, info in self.created_apis_for.items()}
        try:
            return models[collection_name]
        except KeyError:
            raise ValueError('Collection name {0} unknown. Be sure to set the'
                             ' `collection_name` keyword argument when calling'
                             ' `create_api()`.'.format(collection_name))

    def url_for(self, model, **kw) -> str:
        """Returns the URL for the specified model, similar to
        :func:`flask.url_for`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        """
        try:
            url_prefix = self.url_prefix_for(model) or ''
        except KeyError:
            raise ValueError('Model is not registered')
        url_for_collection = f'{url_prefix}/{self.collection_name(model)}'

        resource_id = kw.get('resource_id')

        if not resource_id:
            return url_for_collection

        relation_name = kw.get('relation_name')
        if not relation_name:
            return f'{url_for_collection}/{resource_id}'

        related_resource_id = kw.get('related_resource_id')
        if related_resource_id:
            return f'{url_for_collection}/{resource_id}/{relation_name}/{related_resource_id}'

        relationship = kw.get('relationship')
        if relationship:
            return f'{url_for_collection}/{resource_id}/relationships/{relation_name}'
        return f'{url_for_collection}/{resource_id}/{relation_name}'

    def collection_name(self, model):
        """Returns the collection name for the specified model, as specified by
        the ``collection_name`` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        """
        return self.created_apis_for[model].collection_name

    def serializer_for(self, model):
        """Returns the serializer for the specified model, as specified
        by the `serializer` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        This method only returns URLs for endpoints created by this
        :class:`APIManager`.

        """
        return self.created_apis_for[model].serializer

    def primary_key_for(self, model):
        """Returns the primary key for the specified model, as specified
        by the `primary_key` keyword argument to
        :meth:`create_api_blueprint`.

        `model` is a SQLAlchemy model class. This must be a model on
        which :meth:`create_api_blueprint` has been invoked previously,
        otherwise a :exc:`KeyError` is raised.

        """
        return self.created_apis_for[model].primary_key

    def url_prefix_for(self, model):
        """Returns url_prefix for the specified model, as specified
        by the `url_prefix` keyword argument to
        :meth:`create_api_blueprint`."""
        return self.created_apis_for[model].url_prefix

    def init_app(self, app):

        """Registers any created APIs on the given Flask application.

        This function should only be called if no Flask application was
        provided in the `app` keyword argument to the constructor of
        this class.

        When this function is invoked, any blueprint created by a
        previous invocation of :meth:`create_api` will be registered on
        `app` by calling the :meth:`~flask.Flask.register_blueprint`
        method.

        To use this method with pure SQLAlchemy, for example::

            from flask import Flask
            from flask.ext.restless import APIManager
            from sqlalchemy import create_engine
            from sqlalchemy.orm.session import sessionmaker

            engine = create_engine('sqlite:////tmp/mydb.sqlite')
            Session = sessionmaker(bind=engine)
            mysession = Session()

            # Here create model classes, for example User, Comment, etc.
            ...

            # Create the API manager and create the APIs.
            apimanager = APIManager(session=mysession)
            apimanager.create_api(User)
            apimanager.create_api(Comment)

            # Later, call `init_app` to register the blueprints for the
            # APIs created earlier.
            app = Flask(__name__)
            apimanager.init_app(app)

        and with models defined with Flask-SQLAlchemy::

            from flask import Flask
            from flask.ext.restless import APIManager
            from flask.ext.sqlalchemy import SQLAlchemy

            db = SQLALchemy(app)

            # Here create model classes, for example User, Comment, etc.
            ...

            # Create the API manager and create the APIs.
            apimanager = APIManager(flask_sqlalchemy_db=db)
            apimanager.create_api(User)
            apimanager.create_api(Comment)

            # Later, call `init_app` to register the blueprints for the
            # APIs created earlier.
            app = Flask(__name__)
            apimanager.init_app(app)

        """
        # Register any queued blueprints on the given application.
        for blueprint in self.blueprints:
            app.register_blueprint(blueprint)

    def create_api_blueprint(self, name, model, methods=READONLY_METHODS,
                             url_prefix=None, collection_name=None,
                             allow_functions=False, only=None, exclude=None,
                             additional_attributes=None,
                             validation_exceptions=None, page_size=10,
                             max_page_size=100, preprocessors=None,
                             postprocessors=None, primary_key=None,
                             serializer=None, deserializer=None,
                             includes=None, allow_to_many_replacement=False,
                             allow_delete_from_to_many_relationships=False,
                             allow_client_generated_ids=False):
        """Creates and returns a ReSTful API interface as a blueprint, but does
        not register it on any :class:`flask.Flask` application.

        The endpoints for the API for ``model`` will be available at
        ``<url_prefix>/<collection_name>``. If `collection_name` is
        ``None``, the lowercase name of the provided model class will be
        used instead, as accessed by ``model.__table__.name``. (If any
        black magic was performed on ``model.__table__``, this will be
        reflected in the endpoint URL.) For more information, see
        :ref:`collectionname`.

        This function must be called at most once for each model for which you
        wish to create a ReSTful API. Its behavior (for now) is undefined if
        called more than once.

        This function returns the :class:`flask.Blueprint` object that handles
        the endpoints for the model. The returned :class:`~flask.Blueprint` has
        *not* been registered with the :class:`~flask.Flask` application
        object specified in the constructor of this class, so you will need
        to register it yourself to make it available on the application. If you
        don't need access to the :class:`~flask.Blueprint` object, use
        :meth:`create_api_blueprint` instead, which handles registration
        automatically.

        `name` is the name of the blueprint that will be created.

        `model` is the SQLAlchemy model class for which a ReSTful interface
        will be created.

        `app` is the :class:`Flask` object on which we expect the blueprint
        created in this method to be eventually registered. If not specified,
        the Flask application specified in the constructor of this class is
        used.

        `methods` is a list of strings specifying the HTTP methods that
        will be made available on the ReSTful API for the specified
        model.

        * If ``'GET'`` is in the list, :http:method:`get` requests will
          be allowed at endpoints for collections of resources,
          resources, to-many and to-one relations of resources, and
          particular members of a to-many relation. Furthermore,
          relationship information will be accessible. For more
          information, see :ref:`fetching`.
        * If ``'POST'`` is in the list, :http:method:`post` requests
          will be allowed at endpoints for collections of resources. For
          more information, see :ref:`creating`.
        * If ``'DELETE'`` is in the list, :http:method:`delete` requests
          will be allowed at endpoints for individual resources. For
          more information, see :ref:`deleting`.
        * If ``'PATCH'`` is in the list, :http:method:`patch` requests
          will be allowed at endpoints for individual
          resources. Replacing a to-many relationship when issuing a
          request to update a resource can be enabled by setting
          ``allow_to_many_replacement`` to ``True``.

          Furthermore, to-one relationships can be updated at
          the relationship endpoints under an individual resource via
          :http:method:`patch` requests. This also allows you to add to
          a to-many relationship via the :http:method:`post` method,
          delete from a to-many relationship via the
          :http:method:`delete` method (if
          ``allow_delete_from_to_many_relationships`` is set to
          ``True``), and replace a to-many relationship via the
          :http:method:`patch` method (if ``allow_to_many_replacement``
          is set to ``True``). For more information, see :ref:`updating`
          and :ref:`updatingrelationships`.

        The default set of methods provides a read-only interface (that is,
        only :http:method:`get` requests are allowed).

        `url_prefix` is the URL prefix at which this API will be
        accessible. For example, if this is set to ``'/foo'``, then this
        method creates endpoints of the form
        ``/foo/<collection_name>``. If not set, the default URL prefix
        specified in the constructor of this class will be used. If that
        was not set either, the default ``'/api'`` will be used.

        `collection_name` is the name of the collection specified by the
        given model class to be used in the URL for the ReSTful API
        created. If this is not specified, the lowercase name of the
        model will be used. For example, if this is set to ``'foo'``,
        then this method creates endpoints of the form ``/api/foo``,
        ``/api/foo/<id>``, etc.

        If `allow_functions` is ``True``, then :http:method:`get`
        requests to ``/api/eval/<collection_name>`` will return the
        result of evaluating SQL functions specified in the body of the
        request. For information on the request format, see
        :ref:`functionevaluation`. This is ``False`` by default.

        .. warning::

           If ``allow_functions`` is ``True``, you must not create an
           API for a model whose name is ``'eval'``.

        If `only` is not ``None``, it must be a list of columns and/or
        relationships of the specified `model`, given either as strings or as
        the attributes themselves. If it is a list, only these fields will
        appear in the resource object representation of an instance of `model`.
        In other words, `only` is a whitelist of fields. The ``id`` and
        ``type`` elements of the resource object will always be present
        regardless of the value of this argument. If `only` contains a string
        that does not name a column in `model`, it will be ignored.

        If `additional_attributes` is a list of strings, these
        attributes of the model will appear in the JSON representation
        of an instance of the model. This is useful if your model has an
        attribute that is not a SQLAlchemy column but you want it to be
        exposed. If any of the attributes does not exist on the model, a
        :exc:`AttributeError` is raised.

        If `exclude` is not ``None``, it must be a list of columns and/or
        relationships of the specified `model`, given either as strings or as
        the attributes themselves. If it is a list, all fields **except** these
        will appear in the resource object representation of an instance of
        `model`. In other words, `exclude` is a blacklist of fields. The ``id``
        and ``type`` elements of the resource object will always be present
        regardless of the value of this argument. If `exclude` contains a
        string that does not name a column in `model`, it will be ignored.

        If either `only` or `exclude` is not ``None``, exactly one of them must
        be specified; if both are not ``None``, then this function will raise a
        :exc:`IllegalArgumentError`.

        See :ref:`sparse` for more information on specifying which fields will
        be included in the resource object representation.

        `validation_exceptions` is the tuple of possible exceptions raised by
        validation of your database models. If this is specified, validation
        errors will be captured and forwarded to the client in the format
        described by the JSON API specification. For more information on how to
        use validation, see :ref:`validation`.

        `page_size` must be a positive integer that represents the default page
        size for responses that consist of a collection of resources. Requests
        made by clients may override this default by specifying ``page_size``
        as a query parameter. `max_page_size` must be a positive integer that
        represents the maximum page size that a client can request. Even if a
        client specifies that greater than `max_page_size` should be returned,
        at most `max_page_size` results will be returned. For more information,
        see :ref:`pagination`.

        `serializer` and `deserializer` are custom serialization
        functions. The former function must take a single positional
        argument representing the instance of the model to serialize and
        an additional keyword argument ``only`` representing the fields
        to include in the serialized representation of the instance, and
        must return a dictionary representation of that instance. The
        latter function must take a single argument representing the
        dictionary representation of an instance of the model and must
        return an instance of `model` that has those attributes. For
        more information, see :ref:`serialization`.

        `preprocessors` is a dictionary mapping strings to lists of
        functions. Each key represents a type of endpoint (for example,
        ``'GET_RESOURCE'`` or ``'GET_COLLECTION'``). Each value is a list of
        functions, each of which will be called before any other code is
        executed when this API receives the corresponding HTTP request. The
        functions will be called in the order given here. The `postprocessors`
        keyword argument is essentially the same, except the given functions
        are called after all other code. For more information on preprocessors
        and postprocessors, see :ref:`processors`.

        `primary_key` is a string specifying the name of the column of `model`
        to use as the primary key for the purposes of creating URLs. If the
        `model` has exactly one primary key, there is no need to provide a
        value for this. If `model` has two or more primary keys, you must
        specify which one to use. For more information, see :ref:`primarykey`.

        `includes` must be a list of strings specifying which related resources
        will be included in a compound document by default when fetching a
        resource object representation of an instance of `model`. Each element
        of `includes` is the name of a field of `model` (that is, either an
        attribute or a relationship). For more information, see
        :ref:`includes`.

        If `allow_to_many_replacement` is ``True`` and this API allows
        :http:method:`patch` requests, the server will allow two types
        of requests.  First, it allows the client to replace the entire
        collection of resources in a to-many relationship when updating
        an individual instance of the model. Second, it allows the
        client to replace the entire to-many relationship when making a
        :http:method:`patch` request to a to-many relationship endpoint.
        This is ``False`` by default. For more information, see
        :ref:`updating` and :ref:`updatingrelationships`.

        If `allow_delete_from_to_many_relationships` is ``True`` and
        this API allows :http:method:`patch` requests, the server will
        allow the client to delete resources from any to-many
        relationship of the model. This is ``False`` by default. For
        more information, see :ref:`updatingrelationships`.

        If `allow_client_generated_ids` is ``True`` and this API allows
        :http:method:`post` requests, the server will allow the client to
        specify the ID for the resource to create. JSON API recommends that
        this be a UUID. This is ``False`` by default. For more information, see
        :ref:`creating`.

        """
        # Perform some sanity checks on the provided keyword arguments.
        if only is not None and exclude is not None:
            msg = 'Cannot simultaneously specify both `only` and `exclude`'
            raise IllegalArgumentError(msg)
        if not hasattr(model, 'id'):
            msg = 'Provided model must have an `id` attribute'
            raise IllegalArgumentError(msg)
        if collection_name == '':
            msg = 'Collection name must be nonempty'
            raise IllegalArgumentError(msg)
        if collection_name is None:
            collection_name = model.__table__.name

        if primary_key is None:
            pk_names = primary_key_names(model)
            primary_key = 'id' if 'id' in pk_names else pk_names[0]

        # convert all method names to upper case
        methods = frozenset((m.upper() for m in methods))
        # the name of the API, for use in creating the view and the blueprint
        apiname = APIManager.api_name(collection_name)
        # Prepend the universal preprocessors and postprocessors specified in
        # the constructor of this class.
        preprocessors_ = defaultdict(list)
        postprocessors_ = defaultdict(list)
        preprocessors_.update(preprocessors or {})
        postprocessors_.update(postprocessors or {})
        # for key, value in self.restless_info.universal_preprocessors.items():
        for key, value in self.pre.items():
            preprocessors_[key] = value + preprocessors_[key]
        # for key, value in self.restless_info.universal_postprocessors.items():
        for key, value in self.post.items():
            postprocessors_[key] = value + postprocessors_[key]
        # Validate that all the additional attributes exist on the model.
        if additional_attributes is not None:
            for attr in additional_attributes:
                if isinstance(attr, STRING_TYPES) and not hasattr(model, attr):
                    msg = 'no attribute "{0}" on model {1}'.format(attr, model)
                    raise AttributeError(msg)
        # Create a default serializer and deserializer if none have been
        # provided.
        if serializer is None:
            serializer = FastSerializer(model, collection_name, primary_key=primary_key,
                                        only=only, exclude=exclude, additional_attributes=additional_attributes)

        if deserializer is None:
            deserializer = DefaultDeserializer(self.session, model,
                                               allow_client_generated_ids)
        # Create the view function for the API for this model.
        #
        # Rename some variables with long names for the sake of brevity.
        atmr = allow_to_many_replacement
        api_view = API.as_view(apiname, self, model,
                               # Keyword arguments for APIBase.__init__()
                               preprocessors=preprocessors_,
                               postprocessors=postprocessors_,
                               primary_key=primary_key,
                               validation_exceptions=validation_exceptions,
                               allow_to_many_replacement=atmr,
                               # Keyword arguments for API.__init__()
                               page_size=page_size,
                               max_page_size=max_page_size,
                               serializer=serializer,
                               deserializer=deserializer,
                               includes=includes)

        # add the URL rules to the blueprint: the first is for methods on the
        # collection only, the second is for methods which may or may not
        # specify an instance, the third is for methods which must specify an
        # instance
        # TODO what should the second argument here be?
        # TODO should the url_prefix be specified here or in register_blueprint
        if url_prefix is not None:
            prefix = url_prefix
        elif self.url_prefix is not None:
            prefix = self.url_prefix
        else:
            prefix = DEFAULT_URL_PREFIX
        blueprint = Blueprint(name, __name__, url_prefix=prefix)
        add_rule = blueprint.add_url_rule

        # The URLs that will be routed below.
        collection_url = f'/{collection_name}'
        resource_url = f'{collection_url}/<resource_id>'
        related_resource_url = f'{resource_url}/<relation_name>'
        to_many_resource_url = f'{related_resource_url}/<related_resource_id>'
        relationship_url = f'{resource_url}/relationships/<relation_name>'

        # Create relationship URL endpoints.
        #
        # Due to a limitation in Flask's routing (which is actually
        # Werkzeug's routing), this needs to be declared *before* the
        # rest of the API views. Otherwise, requests like
        # :http:get:`/api/articles/1/relationships/author` interpret the
        # word `relationships` as the name of a relation of an article
        # object.
        adftmr = allow_delete_from_to_many_relationships
        relationship_api_view = RelationshipAPI.as_view(
            f'{apiname}_relationships',
            api=self,
            model=model,
            # Keyword arguments for APIBase.__init__()
            preprocessors=preprocessors_,
            postprocessors=postprocessors_,
            primary_key=primary_key,
            validation_exceptions=validation_exceptions,
            allow_to_many_replacement=allow_to_many_replacement,
            # Keyword arguments RelationshipAPI.__init__()
            allow_delete_from_to_many_relationships=adftmr)
        # When PATCH is allowed, certain non-PATCH requests are allowed
        # on relationship URLs.
        relationship_methods = READONLY_METHODS & methods
        if 'PATCH' in methods:
            relationship_methods |= WRITEONLY_METHODS
        add_rule(relationship_url, methods=relationship_methods,
                 view_func=relationship_api_view)

        # The URL for accessing the entire collection. (POST is special because
        # the :meth:`API.post` method doesn't have any arguments.)
        #
        # For example, /api/people.
        collection_methods = frozenset(('POST', )) & methods
        add_rule(collection_url, view_func=api_view,
                 methods=collection_methods)
        collection_methods = frozenset(('GET', )) & methods
        collection_defaults = dict(resource_id=None, relation_name=None,
                                   related_resource_id=None)
        add_rule(collection_url, view_func=api_view,
                 methods=collection_methods, defaults=collection_defaults)

        # The URL for accessing a single resource. (DELETE and PATCH are
        # special because the :meth:`API.delete` and :meth:`API.patch` methods
        # don't have the `relationname` and `relationinstid` arguments.)
        #
        # For example, /api/people/1.
        resource_methods = frozenset(('DELETE', 'PATCH')) & methods
        add_rule(resource_url, view_func=api_view, methods=resource_methods)
        resource_methods = READONLY_METHODS & methods
        resource_defaults = dict(relation_name=None, related_resource_id=None)
        add_rule(resource_url, view_func=api_view, methods=resource_methods,
                 defaults=resource_defaults)

        # The URL for accessing a related resource, which may be a to-many or a
        # to-one relationship.
        #
        # For example, /api/people/1/articles.
        related_resource_methods = READONLY_METHODS & methods
        related_resource_defaults = dict(related_resource_id=None)
        add_rule(related_resource_url, view_func=api_view,
                 methods=related_resource_methods,
                 defaults=related_resource_defaults)

        # The URL for accessing a to-many related resource.
        #
        # For example, /api/people/1/articles/1.
        to_many_resource_methods = READONLY_METHODS & methods
        add_rule(to_many_resource_url, view_func=api_view,
                 methods=to_many_resource_methods)

        # if function evaluation is allowed, add an endpoint at /api/eval/...
        # which responds only to GET requests and responds with the result of
        # evaluating functions on all instances of the specified model
        if allow_functions:
            eval_api_name = f'{apiname}_eval'
            eval_api_view = FunctionAPI.as_view(eval_api_name, self, model)
            eval_endpoint = '/eval{0}'.format(collection_url)
            eval_methods = ['GET']
            blueprint.add_url_rule(eval_endpoint, methods=eval_methods,
                                   view_func=eval_api_view)

        # Finally, record that this APIManager instance has created an API for
        # the specified model.
        self.created_apis_for[model] = APIInfo(collection_name, blueprint.name,
                                               serializer, primary_key, prefix)
        return blueprint

    def create_api(self, *args, **kw):
        """Creates and possibly registers a ReSTful API blueprint for
        the given SQLAlchemy model.

        If a Flask application was provided in the constructor of this
        class, the created blueprint is immediately registered on that
        application. Otherwise, the blueprint is stored for later
        registration when the :meth:`init_app` method is invoked. In
        that case, the blueprint will be registered each time the
        :meth:`init_app` method is invoked.

        The keyword arguments for this method are exactly the same as
        those for :meth:`create_api_blueprint`, and are passed directly
        to that method. However, unlike that method, this method accepts
        only a single positional argument, `model`, the SQLAlchemy model
        for which to create the API. A UUID will be automatically
        generated for the blueprint name.

        For example, if you only wish to create APIs on a single Flask
        application::

            app = Flask(__name__)
            session = ...  # create the SQLAlchemy session
            manager = APIManager(app=app, session=session)
            manager.create_api(User)

        If you want to create APIs before having access to a Flask
        application, you can call this method before calling
        :meth:`init_app`::

            session = ...  # create the SQLAlchemy session
            manager = APIManager(session=session)
            manager.create_api(User)

            # later...
            app = Flask(__name__)
            manager.init_app(app)

        If you want to create an API and register it on multiple Flask
        applications, you can call this method once and :meth:`init_app`
        multiple times with different `app` arguments::

            session = ...  # create the SQLAlchemy session
            manager = APIManager(session=session)
            manager.create_api(User)

            # later...
            app1 = Flask('application1')
            app2 = Flask('application2')
            manager.init_app(app1)
            manager.init_app(app2)

        """
        blueprint_name = str(uuid1())
        blueprint = self.create_api_blueprint(blueprint_name, *args, **kw)
        # Store the created blueprint
        self.blueprints.append(blueprint)
        # If a Flask application was provided in the constructor of this
        # API manager, then immediately register the blueprint on that
        # application.
        if self.app is not None:
            self.app.register_blueprint(blueprint)

    # Helpers
    # =======

    def serialize(self, instance, sparse_fields=None):
        model = type(instance)
        serialize = self.serializer_for(model)
        # This may raise ValueError
        _type = collection_name(model)
        only = sparse_fields.get(_type) if sparse_fields else None
        return serialize(instance, only=only)

    def serialize_one(self, instance, sparse_fields=None):
        try:
            result = self.serialize(instance, sparse_fields=sparse_fields)
        except SerializationException as e:
            raise MultipleExceptions([e])
        return result

    def serialize_many(self, instances, sparse_fields=None):
        # TODO: minor performance gain if we do not look-up serializer for each instance separately?
        errors = []
        result = []
        for instance in instances:
            try:
                result.append(self.serialize(instance, sparse_fields=sparse_fields))
            except SerializationException as e:
                errors.append(e)
        if errors:
            raise MultipleExceptions(errors)

        return result

    def get_all_inclusions(self, instance_or_instances, include, sparse_fields=None):
        # TODO: refactor
        # If `instance_or_instances` is actually just a single instance
        # of a SQLAlchemy model, get the resources to include for that
        # one instance. Otherwise, collect the resources to include for
        # each instance in `instances`.
        to_include = set()
        if isinstance(instance_or_instances, Iterable):
            for instance in instance_or_instances:
                for path in include:
                    to_include |= set(resources_from_path(instance, path))
        else:
            for path in include:
                to_include |= set(resources_from_path(instance_or_instances, path))

        # TODO: only?
        return self.serialize_many(to_include, sparse_fields=sparse_fields)

    def paginate(self, query, query_parameters):

        page_size = query_parameters.page_size
        page_number = query_parameters.page_number

        # If the page size is 0, just return everything.
        if page_size == 0:
            items = query.all()
            num_results = len(items)
            return Paginated(items, page_size=page_size, num_results=num_results)

        offset = (page_number - 1) * page_size
        items = query.limit(page_size).offset(offset).all()
        if page_number == 1 and len(items) < page_size:
            num_results = len(items)
        else:
            num_results = count(self.session, query)  # query.order_by(None).count() ?
        first = 1
        # Handle a special case for an empty collection of items.
        #
        # There will be no division-by-zero error here because we
        # have already checked that page size is not equal to zero
        # above.
        if num_results == 0:
            last = 1
        else:
            last = int(math.ceil(num_results / page_size))
        prev = page_number - 1 if page_number > 1 else None
        next_ = page_number + 1 if page_number < last else None
        return Paginated(items, num_results=num_results, first=first,
                         last=last, next_=next_, prev=prev,
                         page_size=page_size, filters=query_parameters.filters, sort=query_parameters.sort,
                         group_by=query_parameters.group_by)


    # View functions
    # ==============

    def get_resource(self, model, resource_id, include=None, sparse_fields=None):
        primary_key = primary_key_for(model)
        resource = get_by(self.session, model, resource_id, primary_key)
        if resource is None:
            raise NotFound(f'No resource with ID {resource_id}')

        data = self.serialize_one(resource, sparse_fields=sparse_fields)

        # Prepare the dictionary that will contain the JSON API response.
        result = {'jsonapi': {'version': JSONAPI_VERSION}, 'meta': {},
                  'links': {}, 'data': data}
        # Determine the top-level links.

        result['links']['self'] = self.url_for(model)

        # Include any requested resources in a compound document.
        included = self.get_all_inclusions(resource, include=include, sparse_fields=sparse_fields)
        if included:
            result['included'] = included

        return result

    def get_collection(self, model, query_parameters):
        # Compute the result of the search on the model.
        try:
            query = search(self.session, model, filters=query_parameters.filters, sort=query_parameters.sort, group_by=query_parameters.group_by)
        except ComparisonToNull as exception:
            raise BadRequest(str(exception))
        except UnknownField as exception:
            raise BadRequest(f'Invalid filter object: No such field "{exception.field}"')
        except Exception as exception:
            raise BadRequest('Unable to construct query')

        # Prepare the dictionary that will contain the JSON API response.
        result = {'links': {'self': self.url_for(model)},
                  'jsonapi': {'version': JSONAPI_VERSION},
                  'meta': {}}

        # Add the primary data (and any necessary links) to the JSON API
        # response object.
        #
        # If the result of the search is a SQLAlchemy query object, we need to
        # return a collection.
        if not query_parameters.single:
            paginated = self.paginate(query, query_parameters)
            # Wrap the resulting object or list of objects under a `data` key.
            result['data'] = self.serialize_many(paginated.items, sparse_fields=query_parameters.sparse_fields)
            # Provide top-level links.
            result['links'].update(paginated.pagination_links)
            link_header = ','.join(paginated.header_links)
            headers = dict(Link=link_header)
            num_results = paginated.num_results
            included = self.get_all_inclusions(paginated.items, include=query_parameters.include, sparse_fields=query_parameters.sparse_fields)
        # Otherwise, the result of the search should be a single resource.
        else:
            try:
                instance = query.one()
            except NoResultFound:
                raise NotFound('No result found')
            except MultipleResultsFound:
                raise NotFound('Multiple results found')
            result['data'] = self.serialize_one(instance, sparse_fields=query_parameters.sparse_fields)
            primary_key = self.primary_key_for(type(instance))
            pk_value = result['data'][primary_key]
            # The URL at which a client can access the instance matching this search query.
            headers = dict(Location=f'{query_parameters.base_url}/{pk_value}')
            num_results = 1
            included = self.get_all_inclusions(instance, include=query_parameters.include, sparse_fields=query_parameters.sparse_fields)

        if included:
            result['included'] = included

        result['meta']['__restless_headers'] = headers
        result['meta']['total'] = num_results

        return result
