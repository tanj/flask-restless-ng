from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Unicode
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from ..helpers import ManagerTestBase
from ..helpers import validate_schema


class TestInclusion(ManagerTestBase):
    """Tests corresponding to the `Inclusion of Related Resources`_
    section of the JSON API specification.

    .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

    """

    def setUp(self):
        super(TestInclusion, self).setUp()

        class Article(self.Base):
            __tablename__ = 'article'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person')

        class Comment(self.Base):
            __tablename__ = 'comment'
            id = Column(Integer, primary_key=True)
            author_id = Column(Integer, ForeignKey('person.id'))
            author = relationship('Person', backref=backref('comments'))
            article_id = Column(Integer, ForeignKey('article.id'))
            article = relationship(Article, backref=backref('comments'))

        class Person(self.Base):
            __tablename__ = 'person'
            id = Column(Integer, primary_key=True)
            name = Column(Unicode)
            articles = relationship('Article')

        self.Article = Article
        self.Comment = Comment
        self.Person = Person
        self.Base.metadata.create_all()
        self.manager.create_api(Article)
        self.manager.create_api(Comment)
        self.manager.create_api(Person)

    def test_default_inclusion(self):
        """Tests that by default, Flask-Restless includes no information
        in compound documents.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        person.articles = [article]
        self.session.add_all([person, article])
        self.session.commit()
        # By default, no links will be included at the top level of the
        # document.
        response = self.app.get('/api/person/1')
        document = response.json
        validate_schema(document)
        person = document['data']
        articles = person['relationships']['articles']['data']
        assert ['1'] == sorted(article['id'] for article in articles)
        assert 'included' not in document

    def test_set_default_inclusion(self):
        """Tests that the user can specify default compound document
        inclusions when creating an API.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1)
        article = self.Article(id=1)
        person.articles = [article]
        self.session.add_all([person, article])
        self.session.commit()
        self.manager.create_api(self.Person, includes=['articles'],
                                url_prefix='/api2')
        # In the alternate API, articles are included by default in compound
        # documents.
        response = self.app.get('/api2/person/1')
        document = response.json
        validate_schema(document)
        person = document['data']
        linked = document['included']
        articles = person['relationships']['articles']['data']
        assert ['1'] == sorted(article['id'] for article in articles)
        assert linked[0]['type'] == 'article'
        assert linked[0]['id'] == '1'

    def test_include(self):
        """Tests that the client can specify which linked relations to
        include in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1, name=u'foo')
        article1 = self.Article(id=1)
        article2 = self.Article(id=2)
        comment = self.Comment()
        person.articles = [article1, article2]
        person.comments = [comment]
        self.session.add_all([person, comment, article1, article2])
        self.session.commit()
        query_string = dict(include='articles')
        response = self.app.get('/api/person/1', query_string=query_string)
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        linked = document['included']
        # If a client supplied an include request parameter, no other types of
        # objects should be included.
        assert all(c['type'] == 'article' for c in linked)
        assert ['1', '2'] == sorted(c['id'] for c in linked)

    def test_include_for_collection(self):
        self.session.add_all([self.Person(id=1, name=u'foo'), self.Person(id=2, name=u'bar'), self.Person(id=3, name=u'baz')])
        self.session.add_all([self.Article(id=1, author_id=1), self.Article(id=2, author_id=2), self.Article(id=3, author_id=3)])
        self.session.add_all([self.Comment(id=1, author_id=1, article_id=1)])
        self.session.commit()
        query_string = dict(include='articles,articles.comments')
        response = self.app.get('/api/person', query_string=query_string)
        assert response.status_code == 200
        included = response.json['included']
        assert len(included) == 4

    def test_include_multiple(self):
        """Tests that the client can specify multiple linked relations
        to include in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1, name=u'foo')
        article = self.Article(id=2)
        comment = self.Comment(id=3)
        person.articles = [article]
        person.comments = [comment]
        self.session.add_all([person, comment, article])
        self.session.commit()
        query_string = dict(include='articles,comments')
        response = self.app.get('/api/person/1', query_string=query_string)
        assert response.status_code == 200
        document = response.json
        validate_schema(document)
        # Sort the linked objects by type; 'article' comes before 'comment'
        # lexicographically.
        linked = sorted(document['included'], key=lambda x: x['type'])
        linked_article, linked_comment = linked
        assert linked_article['type'] == 'article'
        assert linked_article['id'] == '2'
        assert linked_comment['type'] == 'comment'
        assert linked_comment['id'] == '3'

    def test_include_dot_separated(self):
        """Tests that the client can specify resources linked to other
        resources to include in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        article = self.Article(id=1)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        comment1.article = article
        comment2.article = article
        comment1.author = person1
        comment2.author = person2
        self.session.add_all([article, comment1, comment2, person1, person2])
        self.session.commit()
        query_string = dict(include='comments.author')
        response = self.app.get('/api/article/1', query_string=query_string)
        document = response.json
        validate_schema(document)
        authors = [resource for resource in document['included']
                   if resource['type'] == 'person']
        assert ['1', '2'] == sorted(author['id'] for author in authors)

    def test_include_does_not_try_to_serialize_none(self):
        article = self.Article(id=1)
        comment = self.Comment(id=1)
        comment.article = article
        self.session.add_all([article, comment])
        self.session.commit()
        response = self.app.get('/api/article/1', query_string=dict(include='comments.author'))
        document = response.json
        validate_schema(document)
        assert len(document['included']) == 1

    def test_include_relationship_of_none(self):
        """If in a chain of relationships A -> B -> C,  B is Null/None, include=b.c should not cause an error"""
        self.session.add(self.Article(id=1))
        self.session.commit()
        response = self.app.get('/api/article/1', query_string=dict(include='author.comments'))
        assert response.status_code == 200

    def test_include_intermediate_resources(self):
        """Tests that intermediate resources from a multi-part
        relationship path are included in a compound document.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article = self.Article(id=1)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        article.comments = [comment1, comment2]
        comment1.author = person1
        comment2.author = person2
        self.session.add_all([article, comment1, comment2, person1, person2])
        self.session.commit()
        query_string = dict(include='comments.author')
        response = self.app.get('/api/article/1', query_string=query_string)
        document = response.json
        validate_schema(document)
        linked = document['included']
        # The included resources should be the two comments and the two
        # authors of those comments.
        assert len(linked) == 4
        authors = [r for r in linked if r['type'] == 'person']
        comments = [r for r in linked if r['type'] == 'comment']
        assert ['1', '2'] == sorted(author['id'] for author in authors)
        assert ['1', '2'] == sorted(comment['id'] for comment in comments)

    def test_include_relationship(self):
        """Tests for including related resources from a relationship endpoint.

        For more information, see the `Inclusion of Related Resources`_
        section of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person1 = self.Person(id=1)
        person2 = self.Person(id=2)
        article = self.Article(id=1)
        comment1 = self.Comment(id=1)
        comment2 = self.Comment(id=2)
        article.comments = [comment1, comment2]
        comment1.author = person1
        comment2.author = person2
        self.session.add_all([article, comment1, comment2, person1, person2])
        self.session.commit()
        query_string = dict(include='comments.author')
        response = self.app.get('/api/article/1/relationships/comments',
                                query_string=query_string)
        # In this case, the primary data is a collection of resource
        # identifier objects that represent linkage to comments for an
        # article, while the full comments and comment authors would be
        # returned as included data.
        #
        # This differs from the previous test because the primary data
        # is a collection of relationship objects instead of a
        # collection of resource objects.
        document = response.json
        validate_schema(document)
        links = document['data']
        assert all(sorted(link) == ['id', 'type'] for link in links)
        included = document['included']
        # The included resources should be the two comments and the two
        # authors of those comments.
        assert len(included) == 4
        authors = [r for r in included if r['type'] == 'person']
        comments = [r for r in included if r['type'] == 'comment']
        assert ['1', '2'] == sorted(author['id'] for author in authors)
        assert ['1', '2'] == sorted(comment['id'] for comment in comments)

    def test_client_overrides_server_includes(self):
        """Tests that if a client supplies an include query parameter, the
        server does not include any other resource objects in the included
        section of the compound document.

        For more information, see the `Inclusion of Related Resources`_ section
        of the JSON API specification.

        .. _Inclusion of Related Resources: http://jsonapi.org/format/#fetching-includes

        """
        person = self.Person(id=1)
        article = self.Article(id=2)
        comment = self.Comment(id=3)
        article.author = person
        comment.author = person
        self.session.add_all([person, article, comment])
        self.session.commit()
        # The server will, by default, include articles. The client will
        # override this and request only comments.
        self.manager.create_api(self.Person, url_prefix='/api2',
                                includes=['articles'])
        query_string = dict(include='comments')
        response = self.app.get('/api2/person/1', query_string=query_string)
        document = response.json
        validate_schema(document)
        included = document['included']
        assert ['3'] == sorted(obj['id'] for obj in included)
        assert ['comment'] == sorted(obj['type'] for obj in included)
