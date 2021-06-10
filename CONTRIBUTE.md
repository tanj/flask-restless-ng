## Contributing ##

Please report any issues on the [GitHub Issue Tracker][14].

To suggest a change to the code or documentation, please create a new pull
request on GitHub. Contributed code must come with an appropriate unit
test. Please ensure that your code follows [PEP8][15], by running, for example,
[flake8][16] before submitting a pull request. Also, please squash multiple
commits into a single commit in your pull request by [rebasing][17] onto the
master branch.

By contributing to this project, you are agreeing to license your code
contributions under both the GNU Affero General Public License, either version
3 or any later version, and the 3-clause BSD License, and your documentation
contributions under the Creative Commons Attribution-ShareAlike License version
4.0, as described in the copyright license section above.

[14]: http://github.com/mrevutskyi/flask-restless-ng/issues
[15]: https://www.python.org/dev/peps/pep-0008/
[16]: http://flake8.readthedocs.org/en/latest/
[17]: https://help.github.com/articles/about-git-rebase/

## Testing ##

Using `pip` is probably the easiest way to install this:

    pip install -r requirements/test.txt

To run the tests:

    python -m unittest


## Building distribution package

    python3 setup.py sdist bdist_wheel

## Building documentation ##

Flask-Restless requires the following program and supporting library to build
the documentation:

* [Sphinx][11]
* [sphinxcontrib-httpdomain][12], version 1.1.7 or greater

These requirements are also listed in the `requirements-doc.txt` file. Using
`pip` is probably the easiest way to install these:

    pip install -r requirements/doc.txt

The documentation is written for Sphinx in [reStructuredText][13] files in the
`docs/` directory. Documentation for each class and function is provided in the
docstring in the code.

The documentation uses the Flask Sphinx theme. It is included as a git
submodule of this project, rooted at `docs/_themes`. To get the themes, do

    git submodule update --init

Now to build the documentation, run the command

    python setup.py build_sphinx

in the top-level directory. The output can be viewed in a web browser by
opening `build/sphinx/html/index.html`.

[11]: http://sphinx.pocoo.org/
[12]: https://packages.python.org/sphinxcontrib-httpdomain/
[13]: https://docutils.sourceforge.net/rst.html

