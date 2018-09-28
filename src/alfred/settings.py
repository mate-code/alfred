# -*- coding: utf-8 -*-

"""
Modul enthält alle allgemeinen Einstellungen (für die gesamte 
alfred Instanz, also nicht experimentspezifisch) sowie die Möglichkeit
experimentspezifische Einstellungen vorzunehmen, die dann unter 
Experiment.settings abgefragt werden können.
"""

import sys
import os
import ConfigParser
import codecs
import io

def _package_path():
    root = __file__
    if os.path.islink(root):
        root = os.path.realpath(root)
    return os.path.dirname(os.path.abspath(root))

#: package_path is the absolute filepath where alfred package is installed
package_path = _package_path()

class _DictObj(dict):
    """
    This class allows dot notation to access dict elements

    Example:
    d = _DictObj()
    d.hello = "Hello World"
    print d.hello # Hello World
    """

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

##########################################################################
# Global Settings
##########################################################################

# define settings files
config_files =  [ # most importent file last
        os.path.join(package_path, 'files/global.conf'),
    ]
if os.environ.get('ALFRED_CONFIG_FILE'):
    config_files += [os.environ.get('ALFRED_CONFIG_FILE')]
else: 
    config_files += ['/etc/alfred' if sys.platform.startswith('linux') else None,
        os.path.join(sys.prefix, 'etc/alfred'),
    ]
config_files += [os.path.join(os.getcwd(), 'config.conf')]

config_files = filter(lambda x: x != None, config_files)

# create config parser
_config_parser = ConfigParser.ConfigParser()

# read _config_files
for configFile in config_files:
    if os.path.exists(configFile):
        _config_parser.readfp(codecs.open(configFile, "r", "utf8"))

# transform data from config_files to actual python objects

#general
general = _DictObj()
general.debug = _config_parser.getboolean('general', 'debug')
debugmode = general.debug
general.external_files_dir = _config_parser.get('general', 'external_files_dir')
if not os.path.isabs(general.external_files_dir):
    general.external_files_dir = os.path.join(os.getcwd(), general.external_files_dir)

# experiment
experiment = _DictObj()
experiment.type = _config_parser.get('experiment', 'type')
if not (experiment.type == 'qt' or experiment.type == 'web' or experiment.type == 'qt-wk'):
    raise ValueError("experiment.type must be qt, qt-wk or web")
experiment.qtFullScreen = _config_parser.getboolean('experiment', 'qt_fullscreen')

# logging
log = _DictObj()
log.syslog = _config_parser.getboolean('log', 'syslog')
log.stderrlog = _config_parser.getboolean('log', 'stderrlog')
log.path = _config_parser.get('log', 'path')
log.level = _config_parser.get('log', 'level')

# failure saving agent
failure_local_saving_agent = _DictObj()
failure_local_saving_agent.level = _config_parser.getint('failure_local_saving_agent', 'level')
failure_local_saving_agent.path = _config_parser.get('failure_local_saving_agent', 'path')
failure_local_saving_agent.name = _config_parser.get('failure_local_saving_agent', 'name')

# webserver
webserver = _DictObj()
webserver.basepath = str(_config_parser.get('webserver', 'basepath'))
webserver.use_local_script = _config_parser.getboolean('webserver', 'use_local_script')
webserver.local_script = os.path.abspath(_config_parser.get('webserver', 'local_script'))
webserver.sql_alchemy_engine = _config_parser.get('webserver', 'sql_alchemy_engine')

# debug default values
debug = _DictObj()
debug.defaultValues = _config_parser.getboolean('debug','set_default_values')
debug.disableMinimumDisplayTime = _config_parser.getboolean('debug','disable_minimumDisplayTime')
debug.reduceCountdown = _config_parser.getboolean('debug','reduce_countdown')
debug.reducedCountdownTime = _config_parser.get('debug','reduced_countdown_time')
debug.logLevelOverride = _config_parser.getboolean('debug','logLevel_override')
debug.logLevel = _config_parser.get('debug','logLevel')
debug.disable_saving = _config_parser.getboolean('debug','disable_saving')

debug.InputElement = _config_parser.get('debug','InputElement_default')
debug.TextEntryElement = unicode(_config_parser.get('debug','TextEntryElement_default')) 
debug.RegEntryElement = unicode(_config_parser.get('debug','RegEntryElement_default'))
debug.PasswordElement = unicode(_config_parser.get('debug', 'PasswordElement_default'))
debug.NumberEntryElement = _config_parser.get('debug','NumberEntryElement_default')
debug.TextAreaElement = unicode(_config_parser.get('debug','TextAreaElement_default'))
debug.SingleChoiceElement = _config_parser.get('debug','SingleChoiceElement_default')
debug.MultipleChoiceElement = _config_parser.getboolean('debug','MultipleChoiceElement_default')
debug.SingleChoiceElement = _config_parser.get('debug','SingleChoiceElement_default')
debug.LikertElement = _config_parser.get('debug','LikertElement_default')
debug.LikertListElement = _config_parser.get('debug','LikertListElement_default')
debug.LikertMatrix = _config_parser.get('debug','LikertMatrix_default')
debug.WebLikertImageElement = _config_parser.get('debug','WebLikertImageElement_default')
debug.WebLikertListElement = _config_parser.get('debug','WebLikertListElement_default')

class ExperimentSpecificSettings(object):
    ''' This class contains experiment specific settings '''
    def __init__(self, config_string=''):
        config_parser = ConfigParser.SafeConfigParser()
        config_files = filter(lambda x: x != None, 
            [ # most importent file last
                os.path.join(package_path, 'files/default.conf'),
                os.environ.get('ALFRED_CONFIG_FILE'),
                os.path.join(os.getcwd(), 'config.conf'),
            ]
        )

        for configFile in config_files:
            if os.path.exists(configFile):
                config_parser.readfp(codecs.open(configFile, "r", "utf8"))
        if config_string:
            config_parser.readfp(io.StringIO(config_string))

        # handle section by hand
        sections_by_hand = ['mongo_saving_agent', 'couchdb_saving_agent',
            'local_saving_agent','fallback_mongo_saving_agent', 'fallback_couchdb_saving_agent',
            'fallback_local_saving_agent','level2_fallback_local_saving_agent']

        self.local_saving_agent = _DictObj()
        self.local_saving_agent.use = config_parser.getboolean('local_saving_agent', 'use')
        self.local_saving_agent.assure_initialization = config_parser.getboolean('local_saving_agent', 'assure_initialization')
        self.local_saving_agent.level = config_parser.getint('local_saving_agent', 'level')
        self.local_saving_agent.path = config_parser.get('local_saving_agent', 'path')
        self.local_saving_agent.name = config_parser.get('local_saving_agent', 'name')

        self.couchdb_saving_agent = _DictObj()
        self.couchdb_saving_agent.use = config_parser.getboolean('couchdb_saving_agent', 'use')
        self.couchdb_saving_agent.assure_initialization = config_parser.getboolean('couchdb_saving_agent', 'assure_initialization')
        self.couchdb_saving_agent.level = config_parser.getint('couchdb_saving_agent', 'level')
        self.couchdb_saving_agent.url = config_parser.get('couchdb_saving_agent', 'url')
        self.couchdb_saving_agent.database = config_parser.get('couchdb_saving_agent', 'database')

        self.mongo_saving_agent = _DictObj()
        self.mongo_saving_agent.use = config_parser.getboolean('mongo_saving_agent', 'use')
        self.mongo_saving_agent.assure_initialization = config_parser.getboolean('mongo_saving_agent', 'assure_initialization')
        self.mongo_saving_agent.level = config_parser.getint('mongo_saving_agent', 'level')
        self.mongo_saving_agent.host = config_parser.get('mongo_saving_agent', 'host')
        self.mongo_saving_agent.database = config_parser.get('mongo_saving_agent', 'database')
        self.mongo_saving_agent.collection = config_parser.get('mongo_saving_agent', 'collection')
        self.mongo_saving_agent.user = config_parser.get('mongo_saving_agent', 'user')
        self.mongo_saving_agent.password = config_parser.get('mongo_saving_agent', 'password')
        
        self.fallback_local_saving_agent = _DictObj()
        self.fallback_local_saving_agent.use = config_parser.getboolean('fallback_local_saving_agent', 'use')
        self.fallback_local_saving_agent.assure_initialization = config_parser.getboolean('fallback_local_saving_agent', 'assure_initialization')
        self.fallback_local_saving_agent.level = config_parser.getint('fallback_local_saving_agent', 'level')
        self.fallback_local_saving_agent.path = config_parser.get('fallback_local_saving_agent', 'path')
        self.fallback_local_saving_agent.name = config_parser.get('fallback_local_saving_agent', 'name')

        self.fallback_couchdb_saving_agent = _DictObj()
        self.fallback_couchdb_saving_agent.use = config_parser.getboolean('fallback_couchdb_saving_agent', 'use')
        self.fallback_couchdb_saving_agent.assure_initialization = config_parser.getboolean('fallback_couchdb_saving_agent', 'assure_initialization')
        self.fallback_couchdb_saving_agent.level = config_parser.getint('fallback_couchdb_saving_agent', 'level')
        self.fallback_couchdb_saving_agent.url = config_parser.get('fallback_couchdb_saving_agent', 'url')
        self.fallback_couchdb_saving_agent.database = config_parser.get('fallback_couchdb_saving_agent', 'database')

        self.fallback_mongo_saving_agent = _DictObj()
        self.fallback_mongo_saving_agent.use = config_parser.getboolean('fallback_mongo_saving_agent', 'use')
        self.fallback_mongo_saving_agent.assure_initialization = config_parser.getboolean('fallback_mongo_saving_agent', 'assure_initialization')
        self.fallback_mongo_saving_agent.level = config_parser.getint('fallback_mongo_saving_agent', 'level')
        self.fallback_mongo_saving_agent.host = config_parser.get('fallback_mongo_saving_agent', 'host')
        self.fallback_mongo_saving_agent.database = config_parser.get('fallback_mongo_saving_agent', 'database')
        self.fallback_mongo_saving_agent.collection = config_parser.get('fallback_mongo_saving_agent', 'collection')
        self.fallback_mongo_saving_agent.user = config_parser.get('fallback_mongo_saving_agent', 'user')
        self.fallback_mongo_saving_agent.password = config_parser.get('fallback_mongo_saving_agent', 'password')
        
        self.level2_fallback_local_saving_agent = _DictObj()
        self.level2_fallback_local_saving_agent.use = config_parser.getboolean('level2_fallback_local_saving_agent', 'use')
        self.level2_fallback_local_saving_agent.assure_initialization = config_parser.getboolean('level2_fallback_local_saving_agent', 'assure_initialization')
        self.level2_fallback_local_saving_agent.level = config_parser.getint('level2_fallback_local_saving_agent', 'level')
        self.level2_fallback_local_saving_agent.path = config_parser.get('level2_fallback_local_saving_agent', 'path')
        self.level2_fallback_local_saving_agent.name = config_parser.get('level2_fallback_local_saving_agent', 'name')

        for section in config_parser.sections():
            if section in sections_by_hand:
                continue
            setattr(self, section, _DictObj())
            for option in config_parser.options(section):
                # WARNING: Automatic section variables are always transformed into lowercase!
                getattr(self, section)[option] = unicode(config_parser.get(section, option))


