from distutils.core import setup
from distutils.command.install import install as dist_install

name = 'alfred'
version = '0.2b5' #major.minor[.patch[sub] e.g. 0.1.0 first experimental version, 1.0.1b2 second beta release of the first patch of 1.0
desc = 'alfred : a library for rapid experiment development'
author = 'Christian Treffenstaedt, Paul Wiemann'
author_email = 'treffenstaedt@psych.uni-goettingen.de'
license = 'MIT'
url = 'http://www.the-experimenter.com/alfred'
package_dir = {'':'src'}
packages = ['alfred', 'alfred.helpmates', 'alfred.questionnaires']
package_data = {'alfred' : ['files/*', 'static/css/*', 'static/img/*', 'static/js/*', 'templates/*']}
requires = ['jinja2 (>= 2.6)', 'PySide',  'PyMongo', 'CouchDB', 'Flask', 'xmltodict']


class install(dist_install):
    user_options = dist_install.user_options + [('without-pyside', None, 'kommentiert alle pyside anweisungen aus')]

    def initialize_options(self):
        dist_install.initialize_options(self)
        self.without_pyside = 0

    def run(self):
        if self.without_pyside:
            self.debug_print("without-pyside flag gesetzt")
            self.escape_pyside()

        dist_install.run(self)

    def escape_pyside(self):
        import os.path, re
        filelist = []

        for root, subFolders, files in os.walk(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'src', 'alfred')):
            for file in files:
                filelist.append(os.path.join(root, file))

        for filename in filelist:
            with open(filename, 'r+') as f:
                lines = f.readlines()
                f.seek(0)
                f.truncate()

                for i in range(len(lines)):
                    line = lines[i]
                    if re.match("^\s*((import|from)\s+PySide|@.*Slot)", line):
                        self.debug_print("In \"%s\" wird Zeile %s \"%s\" auskommentiert" % (filename, i, line[:-1]))
                        lines[i] = '#' + line

                f.writelines(lines)


setup(  name = name,
        version = version,
        description = desc,
        author = author,
        author_email = author_email,
        license = license,
        url = url,
        packages = packages,
        package_dir=package_dir,
        package_data = package_data,
        requires = requires,
        cmdclass=dict(install=install)
    )