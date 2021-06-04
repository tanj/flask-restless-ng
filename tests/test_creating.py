# -*- encoding: utf-8 -*-
# test_creating.py - unit tests for creating resources
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
"""Unit tests for creating resources from endpoints generated by
Flask-Restless.

This module includes tests for additional functionality that is not
already tested by :mod:`test_jsonapi`, the package that guarantees
Flask-Restless meets the minimum requirements of the JSON API
specification.

"""
from __future__ import division

from datetime import datetime

import dateutil
from sqlalchemy import Column
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Interval
from sqlalchemy import Time
from sqlalchemy import Unicode
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from flask_restless import CONTENT_TYPE
from flask_restless import APIManager
from flask_restless import DeserializationException
from flask_restless import SerializationException

from .helpers import BetterJSONEncoder as JSONEncoder
from .helpers import FlaskSQLAlchemyTestBase
from .helpers import ManagerTestBase
from .helpers import check_sole_error
from .helpers import dumps
from .helpers import loads


def raise_s_exception(instance, *args, **kw):
    """Immediately raises a :exc:`SerializationException` with access to
    the provided `instance` of a SQLAlchemy model.

    This function is useful for use in tests for serialization
    exceptions.

    """
    raise SerializationException(instance)


def raise_d_exception(*args, **kw):
    """Immediately raises a :exc:`DeserializationException`.

    This function is useful for use in tests for deserialization
    exceptions.

    """
    raise DeserializationException()


class TestCreating(ManagerTestBase):
    """Tests for creating resources."""

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super().setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            date_created = Column(Date)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            age = Column(Integer)
            name = Column(Unicode, unique=True)
            birth_datetime = Column(DateTime, nullable=True)
            bedtime = Column(Time)
            hangtime = Column(Interval)
            articles = relationship('Article')

            @hybrid_property
            def is_minor(self):
                if hasattr(self, 'age'):
                    if self.age is None:
                        return None
                    return self.age < 18
                return None

        class Tag(self.Base):
            __tablename__ = 'tag'
            name = Column(Unicode, primary_key=True)
            # TODO this dummy column is required to create an API for this
            # object.
            id = Column(Integer)

        self.Article = Article
        self.Person = Person
        self.Tag = Tag
        self.Base.metadata.create_all()
        self.manager.create_api(Person, methods=['POST'])
        self.manager.create_api(Article, methods=['POST'])
        self.manager.create_api(Tag, methods=['POST'])

    def test_wrong_content_type(self):
        """Tests that if a client specifies only
        :http:header:`Content-Type` headers with non-JSON API media
        types, then the server responds with a :http:status:`415`.

        """
        headers = {'Content-Type': 'application/json'}
        data = {
            'data': {
                'type': 'person'
            }
        }
        response = self.app.post('/api/person', data=dumps(data),
                                 headers=headers)
        assert response.status_code == 415
        assert self.session.query(self.Person).count() == 0

    def test_wrong_accept_header(self):
        """Tests that if a client specifies only :http:header:`Accept`
        headers with non-JSON API media types, then the server responds
        with a :http:status:`406`.

        """
        headers = {'Accept': 'application/json'}
        data = {
            'data': {
                'type': 'person'
            }
        }
        response = self.app.post('/api/person', data=dumps(data),
                                 headers=headers)
        assert response.status_code == 406
        assert self.session.query(self.Person).count() == 0

    def test_related_resource_url_forbidden(self):
        """Tests that :http:method:`post` requests to a related resource URL
        are forbidden.

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        self.session.add_all([person, article])
        self.session.commit()
        data = dict(data=dict(type='article', id=1))
        response = self.app.post('/api/person/1/articles', data=dumps(data))
        assert response.status_code == 405
        # TODO check error message here
        assert person.articles == []

    def test_deserializing_time(self):
        """Test for deserializing a JSON representation of a time field."""
        bedtime = datetime.now().time()
        data = dict(data=dict(type='person', attributes=dict(bedtime=bedtime)))
        data = dumps(data, cls=JSONEncoder)
        response = self.app.post('/api/person', data=data)
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['bedtime'] == bedtime.isoformat()

    def test_deserializing_date(self):
        """Test for deserializing a JSON representation of a date field."""
        date_created = datetime.now().date()
        data = dict(data=dict(type='article',
                              attributes=dict(date_created=date_created)))
        data = dumps(data, cls=JSONEncoder)
        response = self.app.post('/api/article', data=data)
        assert response.status_code == 201
        document = loads(response.data)
        article = document['data']
        received_date = article['attributes']['date_created']
        assert received_date == date_created.isoformat()

    def test_deserializing_datetime(self):
        """Test for deserializing a JSON representation of a date field."""
        birth_datetime = datetime.now()
        data = dict(data=dict(type='person',
                              attributes=dict(birth_datetime=birth_datetime)))
        data = dumps(data, cls=JSONEncoder)
        response = self.app.post('/api/person', data=data)
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        received_time = person['attributes']['birth_datetime']
        assert received_time == birth_datetime.isoformat()

    def test_correct_content_type(self):
        """Tests that the server responds with :http:status:`201` if the
        request has the correct JSON API content type.

        """
        data = dict(data=dict(type='person'))
        response = self.app.post('/api/person', data=dumps(data),
                                 content_type=CONTENT_TYPE)
        assert response.status_code == 201
        assert response.headers['Content-Type'] == CONTENT_TYPE

    def test_no_content_type(self):
        """Tests that the server responds with :http:status:`415` if the
        request has no content type.

        """
        data = dict(data=dict(type='person'))
        response = self.app.post('/api/person', data=dumps(data),
                                 content_type=None)
        assert response.status_code == 415
        assert response.headers['Content-Type'] == CONTENT_TYPE

    def test_no_data(self):
        """Tests that a request with no data yields an error response."""
        response = self.app.post('/api/person')
        assert response.status_code == 400
        # TODO check the error message here

    def test_invalid_json(self):
        """Tests that a request with an invalid JSON causes an error response.

        """
        response = self.app.post('/api/person', data='Invalid JSON string')
        assert response.status_code == 400
        # TODO check the error message here

    def test_conflicting_attributes(self):
        """Tests that an attempt to create a resource with a non-unique
        attribute value where uniqueness is required causes a
        :http:status:`409` response.

        """
        person = self.Person(name=u'foo')
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(type='person', attributes=dict(name=u'foo')))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 409  # Conflict
        # TODO check error message here

    def test_rollback_on_integrity_error(self):
        """Tests that an integrity error in the database causes a session
        rollback, and that the server can still process requests correctly
        after this rollback.

        """
        person = self.Person(name=u'foo')
        self.session.add(person)
        self.session.commit()
        data = dict(data=dict(type='person', attributes=dict(name=u'foo')))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 409  # Conflict
        assert self.session.is_active, 'Session is in `partial rollback` state'
        person = dict(data=dict(type='person', attributes=dict(name=u'bar')))
        response = self.app.post('/api/person', data=dumps(person))
        assert response.status_code == 201

    def test_nonexistent_attribute(self):
        """Tests that the server rejects an attempt to create a resource with
        an attribute that does not exist in the resource.

        """
        data = dict(data=dict(type='person', attributes=dict(bogus=0)))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        # TODO check error message here

    def test_nonexistent_relationship(self):
        """Tests that the server rejects an attempt to create a resource
        with a relationship that does not exist in the resource.

        """
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'bogus': {
                        'data': None
                    }
                }
            }
        }
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        # TODO check error message here

    def test_invalid_relationship(self):
        """Tests that the server rejects an attempt to create a resource
        with an invalid relationship linnkage object.

        """
        # In this request, the `articles` linkage object is missing the
        # `data` element.
        data = {
            'data': {
                'type': 'person',
                'relationships':
                {
                    'articles': {}
                }
            }
        }
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        keywords = ['deserialize', 'missing', '"data"', 'element',
                    'linkage object', 'relationship', '"articles"']
        check_sole_error(response, 400, keywords)

    def test_hybrid_property(self):
        """Tests that an attempt to set a read-only hybrid property causes an
        error.

        See issue #171.

        """
        data = dict(data=dict(type='person', attributes=dict(is_minor=True)))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        # TODO check error message here

    def test_nullable_datetime(self):
        """Tests for creating a model with a nullable datetime field.

        For more information, see issue #91.

        """
        data = dict(data=dict(type='person',
                              attributes=dict(birth_datetime=None)))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['birth_datetime'] is None

    def test_empty_date(self):
        """Tests that attempting to assign an empty date string to a date field
        actually assigns a value of ``None``.

        For more information, see issue #91.

        """
        data = dict(data=dict(type='person',
                              attributes=dict(birth_datetime='')))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['birth_datetime'] is None

    def test_current_timestamp(self):
        """Tests that the string ``'CURRENT_TIMESTAMP'`` gets converted into a
        datetime object when making a request to set a date or time field.

        """
        CURRENT = 'CURRENT_TIMESTAMP'
        data = dict(data=dict(type='person',
                              attributes=dict(birth_datetime=CURRENT)))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        birth_datetime = person['attributes']['birth_datetime']
        assert birth_datetime is not None
        birth_datetime = dateutil.parser.parse(birth_datetime)
        diff = datetime.utcnow() - birth_datetime
        # Check that the total number of seconds from the server creating the
        # Person object to (about) now is not more than about a minute.
        assert diff.days == 0
        assert (diff.seconds + diff.microseconds / 1000000) < 3600

    def test_timedelta(self):
        """Tests for creating an object with a timedelta attribute."""
        data = dict(data=dict(type='person', attributes=dict(hangtime=300)))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['hangtime'] == 300

    def test_to_many(self):
        """Tests the creation of a model with a to-many relation."""
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        self.session.add_all([article1, article2])
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'articles': {
                        'data': [
                            {'type': 'article', 'id': '1'},
                            {'type': 'article', 'id': '2'}
                        ]
                    }
                }
            }
        }
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        articles = person['relationships']['articles']['data']
        assert ['1', '2'] == sorted(article['id'] for article in articles)
        assert all(article['type'] == 'article' for article in articles)

    def test_to_one(self):
        """Tests the creation of a model with a to-one relation."""
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'author': {
                        'data': {'type': 'person', 'id': '1'}
                    }
                }
            }
        }
        response = self.app.post('/api/article', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        article = document['data']
        person = article['relationships']['author']['data']
        assert person['type'] == 'person'
        assert person['id'] == '1'

    def test_unicode_primary_key(self):
        """Test for creating a resource with a unicode primary key."""
        data = dict(data=dict(type='tag', attributes=dict(name=u'Юникод')))
        response = self.app.post('/api/tag', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        tag = document['data']
        assert tag['attributes']['name'] == u'Юникод'

    def test_primary_key_as_id(self):
        """Tests the even if a primary key is not named ``id``, it still
        appears in an ``id`` key in the response.

        """
        data = dict(data=dict(type='tag', attributes=dict(name=u'foo')))
        response = self.app.post('/api/tag', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        tag = document['data']
        assert tag['id'] == u'foo'

    # TODO Not supported right now.
    #
    # def test_treat_as_id(self):
    #     """Tests for specifying one attribute in a compound primary key by
    #     which to create a resource.

    #     """
    #     manager = APIManager(self.flaskapp, session=self.session)
    #     manager.create_api(self.User, primary_key='email')
    #     data = dict(data=dict(type='user', id=1))
    #     response = self.app.post('/api/user', data=dumps(data))
    #     document = loads(response.data)
    #     user = document['data']
    #     assert user['id'] == '1'
    #     assert user['type'] == 'user'
    #     assert user['email'] == 'foo'

    def test_collection_name(self):
        """Tests for creating a resource with an alternate collection name."""
        self.manager.create_api(self.Person, methods=['POST'],
                                collection_name='people')
        data = dict(data=dict(type='people'))
        response = self.app.post('/api/people', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['type'] == 'people'

    def test_custom_serialization(self):
        """Tests for custom deserialization."""
        temp = []

        # TODO: revisit
        def serializer(instance, *args, **kw):
            result = {'attributes': {'foo': 'bar'}}
            result['attributes']['foo'] = temp.pop()
            return result

        def deserializer(document, *args, **kw):
            # Move the attributes up to the top-level object.
            data = document['data']['attributes']
            temp.append(data.pop('foo'))
            instance = self.Person(**data)
            return instance

        # POST will deserialize once and serialize once
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/api2',
                                serializer=serializer,
                                deserializer=deserializer)
        data = dict(data=dict(type='person', attributes=dict(foo='bar')))
        response = self.app.post('/api2/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['foo'] == 'bar'

    def test_serialization_exception_included(self):
        """Tests that exceptions are caught when trying to serialize
        included resources.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        self.manager.create_api(self.Article, methods=['POST'],
                                url_prefix='/api2')
        self.manager.create_api(self.Person, serializer=raise_s_exception)
        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'author': {
                        'data': {
                            'type': 'person',
                            'id': 1
                        }
                    }
                }
            }
        }
        query_string = {'include': 'author'}
        response = self.app.post('/api/article', data=dumps(data),
                                 query_string=query_string)
        check_sole_error(response, 500, ['Failed to serialize',
                                         'included resource', 'type', 'person',
                                         'ID', '1'])

    def test_deserialization_exception(self):
        """Tests that exceptions are caught when a custom deserialization
        method raises an exception.

        """
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/api2',
                                deserializer=raise_d_exception)
        data = dict(data=dict(type='person'))
        response = self.app.post('/api2/person', data=dumps(data))
        assert response.status_code == 400
        # TODO check error message here

    def test_serialization_exception(self):
        """Tests that exceptions are caught when a custom serialization method
        raises an exception.

        """
        self.manager.create_api(self.Person, methods=['POST'],
                                url_prefix='/api2',
                                serializer=raise_s_exception)
        data = dict(data=dict(type='person'))
        response = self.app.post('/api2/person', data=dumps(data))
        assert response.status_code == 400
        # TODO check error message here

    def test_to_one_related_resource_url(self):
        """Tests that attempting to add to a to-one related resource URL
        (instead of a relationship URL) yields an error response.

        """
        article = self.Article(id=1)
        person = self.Person(id=1)
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=dict(id=1, type='person'))
        response = self.app.post('/api/article/1/author', data=dumps(data))
        assert response.status_code == 405
        # TODO check error message here

    def test_to_many_related_resource_url(self):
        """Tests that attempting to add to a to-many related resource URL
        (instead of a relationship URL) yields an error response.

        """
        article = self.Article(id=1)
        person = self.Person(id=1)
        self.session.add_all([article, person])
        self.session.commit()
        data = dict(data=[dict(id=1, type='article')])
        response = self.app.post('/api/person/1/articles', data=dumps(data))
        assert response.status_code == 405
        # TODO check error message here

    def test_missing_data(self):
        """Tests that an attempt to update a resource without providing a
        "data" element yields an error.

        """
        data = dict(type='person')
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 400
        keywords = ['deserialize', 'missing', '"data"', 'element']
        check_sole_error(response, 400, keywords)

    def test_to_one_relationship_missing_id(self):
        """Tests that the server rejects a request to create a resource
        with a to-one relationship when the relationship linkage object
        is missing an ``id`` element.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'author': {
                        'data': {
                            'type': 'person'
                        }
                    }
                }
            }
        }
        response = self.app.post('/api/article', data=dumps(data))
        keywords = ['deserialize', 'missing', '"id"', 'element',
                    'linkage object', 'relationship', '"author"']
        check_sole_error(response, 400, keywords)

    def test_to_one_relationship_missing_type(self):
        """Tests that the server rejects a request to create a resource
        with a to-one relationship when the relationship linkage object
        is missing a ``type`` element.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'author': {
                        'data': {
                            'id': '1'
                        }
                    }
                }
            }
        }
        response = self.app.post('/api/article', data=dumps(data))
        keywords = ['deserialize', 'missing', '"type"', 'element',
                    'linkage object', 'relationship', '"author"']
        check_sole_error(response, 400, keywords)

    def test_to_one_relationship_conflicting_type(self):
        """Tests that the server rejects a request to create a resource
        with a to-one relationship when the relationship linkage object
        has a ``type`` element that conflicts with the actual type of
        the related resource.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'author': {
                        'data': {
                            'id': '1',
                            'type': 'article'
                        }
                    }
                }
            }
        }
        response = self.app.post('/api/article', data=dumps(data))
        keywords = ['deserialize', 'expected', 'type', '"person"', '"article"',
                    'linkage object', 'relationship', '"author"']
        check_sole_error(response, 409, keywords)

    def test_to_many_relationship_missing_id(self):
        """Tests that the server rejects a request to create a resource
        with a to-many relationship when any of the relationship linkage
        objects is missing an ``id`` element.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'articles': {
                        'data': [
                            {'type': 'article'}
                        ]
                    }
                }
            }
        }
        response = self.app.post('/api/person', data=dumps(data))
        keywords = ['deserialize', 'missing', '"id"', 'element',
                    'linkage object', 'relationship', '"articles"']
        check_sole_error(response, 400, keywords)

    def test_to_many_relationship_missing_type(self):
        """Tests that the server rejects a request to create a resource
        with a to-many relationship when any of the relationship linkage
        objects is missing a ``type`` element.

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'articles': {
                        'data': [
                            {'id': '1'}
                        ]
                    }
                }
            }
        }
        response = self.app.post('/api/person', data=dumps(data))
        keywords = ['deserialize', 'missing', '"type"', 'element',
                    'linkage object', 'relationship', '"articles"']
        check_sole_error(response, 400, keywords)

    def test_to_many_relationship_conflicting_type(self):
        """Tests that the server rejects a request to create a resource
        with a to-many relationship when any of the relationship linkage
        objects has a ``type`` element that conflicts with the actual
        type of the related resource.

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        data = {
            'data': {
                'type': 'person',
                'relationships': {
                    'articles': {
                        'data': [
                            {
                                'id': '1',
                                'type': 'person'
                            }
                        ]
                    }
                }
            }
        }
        response = self.app.post('/api/person', data=dumps(data))
        keywords = ['deserialize', 'expected', 'type', '"article"', '"person"',
                    'linkage object', 'relationship', '"articles"']
        check_sole_error(response, 409, keywords)


class TestProcessors(ManagerTestBase):
    """Tests for pre- and postprocessors."""

    def setUp(self):
        super(TestProcessors, self).setUp()

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        self.Person = Person
        self.Base.metadata.create_all()

    def test_preprocessor(self):
        """Tests :http:method:`post` requests with a preprocessor function."""

        def set_name(data=None, **kw):
            """Sets the name attribute of the incoming data object, regardless
            of the value requested by the client.

            """
            if data is not None:
                data['data']['attributes']['name'] = u'bar'

        preprocessors = dict(POST_RESOURCE=[set_name])
        self.manager.create_api(self.Person, methods=['POST'],
                                preprocessors=preprocessors)
        data = dict(data=dict(type='person', attributes=dict(name=u'foo')))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        assert person['attributes']['name'] == 'bar'

    def test_postprocessor(self):
        """Tests that a postprocessor is invoked when creating a resource."""

        def modify_result(result=None, **kw):
            result['foo'] = 'bar'

        postprocessors = dict(POST_RESOURCE=[modify_result])
        self.manager.create_api(self.Person, methods=['POST'],
                                postprocessors=postprocessors)
        data = dict(data=dict(type='person'))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        assert document['foo'] == 'bar'


class TestAssociationProxy(ManagerTestBase):
    """Tests for creating an object with a relationship using an association
    proxy.

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application,
        and creates the ReSTful API endpoints for the models used in the test
        methods.

        """
        super().setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            tags = association_proxy('articletags', 'tag',
                                     creator=lambda tag: ArticleTag(tag=tag))

        class ArticleTag(self.Base):
            __tablename__ = 'articletag'
            article_id = Column(Integer, ForeignKey('article.id'),
                                primary_key=True)
            article = relationship(Article, backref=backref('articletags'))
            tag_id = Column(Integer, ForeignKey('tag.id'), primary_key=True)
            tag = relationship('Tag')
            # TODO this dummy column is required to create an API for this
            # object.
            id = Column(Integer)

        class Tag(self.Base):
            __tablename__ = 'tag'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)

        self.Tag = Tag
        self.Base.metadata.create_all()
        self.manager.create_api(Article, methods=['POST'])
        # HACK Need to create APIs for these other models because otherwise
        # we're not able to create the link URLs to them.
        #
        # TODO Fix this by simply not creating links to related models for
        # which no API has been made.
        self.manager.create_api(Tag)
        self.manager.create_api(ArticleTag)

    def test_create(self):
        """Test for creating a new instance of the database model that has a
        many-to-many relation that uses an association object to allow extra
        information to be stored on the association table.

        """
        tag1 = self.Tag(id=1)
        tag2 = self.Tag(id=2)
        self.session.add_all([tag1, tag2])
        self.session.commit()
        data = {
            'data': {
                'type': 'article',
                'relationships': {
                    'tags': {
                        'data': [
                            {'type': 'tag', 'id': '1'},
                            {'type': 'tag', 'id': '2'}
                        ]
                    }
                }
            }
        }
        response = self.app.post('/api/article', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        article = document['data']
        tags = article['relationships']['tags']['data']
        assert ['1', '2'] == sorted(tag['id'] for tag in tags)


class TestFlaskSQLAlchemy(FlaskSQLAlchemyTestBase):
    """Tests for creating resources defined as Flask-SQLAlchemy models instead
    of pure SQLAlchemy models.

    """

    def setUp(self):
        """Creates the Flask-SQLAlchemy database and models."""
        super(TestFlaskSQLAlchemy, self).setUp()

        class Person(self.db.Model):
            id = self.db.Column(self.db.Integer, primary_key=True)

        self.Person = Person
        self.db.create_all()
        self.manager = APIManager(self.flaskapp, flask_sqlalchemy_db=self.db)
        self.manager.create_api(self.Person, methods=['POST'])

    def test_create(self):
        """Tests for creating a resource."""
        data = dict(data=dict(type='person'))
        response = self.app.post('/api/person', data=dumps(data))
        assert response.status_code == 201
        document = loads(response.data)
        person = document['data']
        # TODO To make this test more robust, should query for person objects.
        assert person['id'] == '1'
        assert person['type'] == 'person'
