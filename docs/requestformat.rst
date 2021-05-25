.. currentmodule:: flask_restless

.. _requestformat:

Requests and responses
======================

Requests and responses are all in the JSON API format, so each request must
include an :http:header:`Accept` header whose value is
:mimetype:`application/vnd.api+json` and any request that contains content must
include a :http:header:`Content-Type` header whose value is
:mimetype:`application/vnd.api+json`. If they do not, the client will receive
an error response.

This section of the documentation assumes some familiarity with the JSON API
specification.

.. toctree::
   :maxdepth: 2

   fetching
   creating
   deleting
   updating
   updatingrelationships

.. _idstring:

Resource ID must be a string
----------------------------

As required by the JSON API, the ID (and type) of a resource must be a string
in request and response documents. This does *not* mean that the primary key in
the database must be a string, only that it will appear as a string in
communications between the client and the server. For more information, see the
`Identification`_ section of the JSON API specification.

.. _Identification: http://jsonapi.org/format/#document-resource-object-identification

.. _slashes:

Trailing slashes in URLs
------------------------

API endpoints do not have trailing slashes. A :http:method:`get` request to,
for example, ``/api/person/`` will result in a :http:statuscode:`404` response.

.. _dateandtime:

Date and time fields
--------------------

Flask-Restless will automatically parse and convert date and time strings into
the corresponding Python objects. Flask-Restless also understands intervals
(also known as *durations*), if you specify the interval as an integer
representing the number of units that the interval spans.

If you want the server to set the value of a date or time field of a model as
the current time (as measured at the server), use one of the special strings
``"CURRENT_TIMESTAMP"``, ``"CURRENT_DATE"``, or ``"LOCALTIMESTAMP"``. When the
server receives one of these strings in a request, it will use the
corresponding SQL function to set the date or time of the field in the model.

.. _errors:

Errors and error messages
-------------------------

Flask-Restless returns the error responses required by the JSON API
specification, and most other server errors yield a
:http:statuscode:`400`. Errors are included in the ``errors`` element in the
top-level JSON document in the response body.

If a request triggers certain types of errors, the SQLAlchemy session will be
rolled back. Currently these errors are

* :exc:`~sqlalchemy.exc.DataError`,
* :exc:`~sqlalchemy.exc.IntegrityError`,
* :exc:`~sqlalchemy.exc.ProgrammingError`,
* :exc:`~sqlalchemy.orm.exc.FlushError`.


Cross-Origin Resource Sharing (CORS)
------------------------------------

`Cross-Origin Resource Sharing (CORS)`_ is a protocol that allows JavaScript
HTTP clients to make HTTP requests across Internet domain boundaries while
still protecting against cross-site scripting (XSS) attacks. If you have access
to the HTTP server that serves your Flask application, I recommend configuring
CORS there, since such concerns are beyond the scope of Flask-Restless.
However, in case you need to support CORS at the application level, you should
create a function that adds the necessary HTTP headers after the request has
been processed by Flask-Restless (that is, just before the HTTP response is
sent from the server to the client) using the
:meth:`flask.Blueprint.after_request` method::

    from flask import Flask
    from flask_restless import APIManager

    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = 'example.com'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        # Set whatever other headers you like...
        return response

    app = Flask(__name__)
    manager = APIManager(app)
    blueprint = manager.create_api_blueprint('mypersonapi', Person)
    blueprint.after_request(add_cors_headers)
    app.register_blueprint(blueprint)

.. _Cross-Origin Resource Sharing (CORS): http://enable-cors.org
