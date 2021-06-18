# test_fetching_data.py - tests fetching data according to JSON API
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
"""Unit tests for requests that fetch resources and relationships.

The tests in this module correspond to the `Fetching Data`_ section of
the JSON API specification.

.. _Fetching Data: http://jsonapi.org/format/#fetching

"""
from sqlalchemy import Column
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from ..helpers import ManagerTestBase
from ..helpers import validate_schema


class TestFetchingData(ManagerTestBase):
    """Tests corresponding to the `Fetching Data`_ section of the JSON API
    specification.

    .. _Fetching Data: http://jsonapi.org/format/#fetching

    """

    def setUp(self):
        """Creates the database, the :class:`~flask.Flask` object, the
        :class:`~flask_restless.manager.APIManager` for that application, and
        creates the ReSTful API endpoints for the :class:`TestSupport.Person`
        and :class:`TestSupport.Article` models.

        """
        super(TestFetchingData, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            title = Column(Unicode)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            article_id = Column(Integer, ForeignKey('article.id'))
            article = relationship(Article, backref=backref('comments'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            age = Column(Integer)
            other = Column(Float)
            articles = relationship('Article')

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Person)
        self.manager.create_api(Comment)

    def test_single_resource(self):
        """Tests for fetching a single resource.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        article = document['data']
        assert article['id'] == '1'
        assert article['type'] == 'article'

    def test_collection(self):
        """Tests for fetching a collection of resources.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        articles = document['data']
        assert ['1'] == sorted(article['id'] for article in articles)

    def test_related_resource(self):
        """Tests for fetching a to-one related resource.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        article = self.Article(id=1)
        person = self.Person(id=1)
        article.author = person
        self.session.add_all([article, person])
        self.session.commit()
        response = self.app.get('/api/article/1/author')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        author = document['data']
        assert author['type'] == 'person'
        assert author['id'] == '1'

    def test_empty_collection(self):
        """Tests for fetching an empty collection of resources.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        response = self.app.get('/api/person')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        people = document['data']
        assert people == []

    def test_to_many_related_resource_url(self):
        """Tests for fetching to-many related resources from a related
        resource URL.

        The response to a request to a to-many related resource URL should
        include an array of resource objects, *not* linkage objects.

        For more information, see the `Fetching Resources`_ section of JSON API
        specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        person = self.Person(id=1)
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        person.articles = [article1, article2]
        self.session.add_all([person, article1, article2])
        self.session.commit()
        response = self.app.get('/api/person/1/articles')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        articles = document['data']
        assert ['1', '2'] == sorted(article['id'] for article in articles)
        assert all(article['type'] == 'article' for article in articles)
        assert all('title' in article['attributes'] for article in articles)
        assert all('author' in article['relationships']
                   for article in articles)

    def test_to_one_related_resource_url(self):
        """Tests for fetching a to-one related resource from a related resource
        URL.

        The response to a request to a to-one related resource URL should
        include a resource object, *not* a linkage object.

        For more information, see the `Fetching Resources`_ section of JSON API
        specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()
        response = self.app.get('/api/article/1/author')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        author = document['data']
        assert author['id'] == '1'
        assert author['type'] == 'person'
        assert all(field in author['attributes']
                   for field in ('name', 'age', 'other'))

    def test_empty_to_many_related_resource_url(self):
        """Tests for fetching an empty to-many related resource from a related
        resource URL.

        For more information, see the `Fetching Resources`_ section of JSON API
        specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        person = self.Person(id=1)
        self.session.add(person)
        self.session.commit()
        response = self.app.get('/api/person/1/articles')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        articles = document['data']
        assert articles == []

    def test_empty_to_one_related_resource(self):
        """Tests for fetching an empty to-one related resource from a related
        resource URL.

        For more information, see the `Fetching Resources`_ section of JSON API
        specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1/author')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        author = document['data']
        assert author is None

    def test_nonexistent_resource(self):
        """Tests for fetching a nonexistent resource.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        response = self.app.get('/api/article/1')
        assert response.status_code == 404

    def test_nonexistent_collection(self):
        """Tests for fetching a nonexistent collection of resources.

        For more information, see the `Fetching Resources`_ section of
        JSON API specification.

        .. _Fetching Resources: http://jsonapi.org/format/#fetching-resources

        """
        response = self.app.get('/api/bogus')
        assert response.status_code == 404

    def test_to_many_relationship_url(self):
        """Test for fetching linkage objects from a to-many relationship
        URL.

        The response to a request to a to-many relationship URL should
        be a linkage object, *not* a resource object.

        For more information, see the `Fetching Relationships`_ section
        of JSON API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        article = self.Article(id=1)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        comment3 = self.Comment(id=3)
        article.comments = [comment1, comment2]
        self.session.add_all([article, comment1, comment2, comment3])
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/comments')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        comments = document['data']
        assert all(['id', 'type'] == sorted(comment) for comment in comments)
        assert ['1', '2'] == sorted(comment['id'] for comment in comments)
        assert all(comment['type'] == 'comment' for comment in comments)

    def test_empty_to_many_relationship_url(self):
        """Test for fetching from an empty to-many relationship URL.

        For more information, see the `Fetching Relationships`_ section of JSON
        API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/comments')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        comments = document['data']
        assert comments == []

    def test_to_one_relationship_url(self):
        """Test for fetching a resource from a to-one relationship URL.

        The response to a request to a to-many relationship URL should
        be a linkage object, *not* a resource object.

        For more information, see the `Fetching Relationships`_ section
        of JSON API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        article.author = person
        self.session.add_all([person, article])
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/author')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        person = document['data']
        assert ['id', 'type'] == sorted(person)
        assert person['id'] == '1'
        assert person['type'] == 'person'

    def test_empty_to_one_relationship_url(self):
        """Test for fetching from an empty to-one relationship URL.

        For more information, see the `Fetching Relationships`_ section of JSON
        API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/author')
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        person = document['data']
        assert person is None

    def test_relationship_links(self):
        """Tests for links included in relationship objects.

        For more information, see the `Fetching Relationships`_ section
        of JSON API specification.

        .. _Fetching Relationships: http://jsonapi.org/format/#fetching-relationships

        """
        article = self.Article(id=1)
        self.session.add(article)
        self.session.commit()
        response = self.app.get('/api/article/1/relationships/author')
        document = response.json
        validate_schema(document)
        links = document['links']
        assert links['self'].endswith('/article/1/relationships/author')
        assert links['related'].endswith('/article/1/author')
