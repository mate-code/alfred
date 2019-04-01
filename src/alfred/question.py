# -*- coding:utf-8 -*-

'''
.. moduleauthor:: Paul Wiemann <paulwiemann@gmail.com>
'''
from __future__ import absolute_import

from builtins import str
from builtins import object
from abc import ABCMeta, abstractproperty
import time

from ._core import PageCore
from .exceptions import AlfredError
from . import element
from .element import Element, WebElementInterface, TextElement, ExperimenterMessages
import alfred.settings as settings

from future.utils import with_metaclass
from functools import reduce


class Page(PageCore):
    def __init__(self, minimumDisplayTime=0, minimumDisplayTimeMsg=None, **kwargs):
        self._minimumDisplayTime = minimumDisplayTime
        if settings.debugmode and settings.debug.disableMinimumDisplayTime:
            self._minimumDisplayTime = 0
        self._minimumDisplayTimeMsg = minimumDisplayTimeMsg

        self._data = {}
        self._isClosed = False
        self._showCorrectiveHints = False

        super(Page, self).__init__(**kwargs)

    def added_to_experiment(self, experiment):
        if not isinstance(self, WebPageInterface):
            raise TypeError('%s must be an instance of %s' % (self.__class__.__name__, WebPageInterface.__name__))

        super(Page, self).added_to_experiment(experiment)

    @property
    def show_thumbnail(self):
        return True

    @property
    def show_corrective_hints(self):
        return self._showCorrectiveHints

    @show_corrective_hints.setter
    def show_corrective_hints(self, b):
        self._showCorrectiveHints = bool(b)

    @property
    def is_closed(self):
        return self._isClosed

    @property
    def data(self):
        data = super(Page, self).data
        data.update(self._data)
        return data

    def _on_showing_widget(self):
        '''
        Method for internal processes on showing Widget
        '''

        if not self._hasBeenShown:
            self._data['firstShowTime'] = time.time()

        self.on_showing_widget()

        self._hasBeenShown = True

    def on_showing_widget(self):
        pass

    def _on_hiding_widget(self):
        '''
        Method for internal processes on hiding Widget
        '''
        self.on_hiding_widget()

        self._hasBeenHidden = True

        # TODO: Sollten nicht onHiding closingtime und duration errechnet werden? Passiert momentan onClosing und funktioniert daher nicht in allen question groups!

    def on_hiding_widget(self):
        pass

    def closeQuestion(self):
        if not self.allow_closing:
            raise AlfredError()

        if 'closingTime' not in self._data:
            self._data['closingTime'] = time.time()
        if 'duration' not in self._data \
                and 'firstShowTime' in self._data \
                and 'closingTime' in self._data:
            self._data['duration'] = self._data['closingTime'] - self._data['firstShowTime']

        self._isClosed = True

    def allow_closing(self):
        return True

    def can_display_corrective_hints_in_line(self):
        return False

    def corrective_hints(self):
        '''
        returns a list of corrective hints

        :rtype: list of unicode strings
        '''
        return []

    def allow_leaving(self, direction):
        if 'firstShowTime' in self._data and \
            time.time() - self._data['firstShowTime'] \
                < self._minimumDisplayTime:
            try:
                msg = self._minimumDisplayTimeMsg if self._minimumDisplayTimeMsg else self._experiment.settings.messages.minimum_display_time
            except Exception:
                msg = "Can't access minimum display time message"
            self._experiment.message_manager.post_message(msg.replace('${mdt}', str(self._minimumDisplayTime)))
            return False
        return True


class WebPageInterface(with_metaclass(ABCMeta, object)):
    def prepare_web_widget(self):
        '''Wird aufgerufen bevor das die Frage angezeigt wird, wobei jedoch noch
        Nutzereingaben zwischen aufruf dieser funktion und dem anzeigen der
        Frage kmmen koennen. Hier sollte die Frage, von
        noch nicht gemachten user Eingaben unabhaengige und rechenintensive
        verbereitungen fuer das anzeigen des widgets aufrufen. z.B. generieren
        von grafiken'''
        pass

    @abstractproperty
    def web_widget(self):
        pass

    @property
    def web_thumbnail(self):
        return None

    @property
    def css_code(self):
        return []

    @property
    def css_urls(self):
        return []

    @property
    def js_code(self):
        return []

    @property
    def js_urls(self):
        return []

    def set_data(self, dictionary):
        pass


class CoreCompositePage(Page):
    def __init__(self, elements=None, **kwargs):
        super(CoreCompositePage, self).__init__(**kwargs)

        self._elementList = []
        self._elementNameCounter = 1
        self._thumbnail_element = None
        if elements is not None:
            if not isinstance(elements, list):
                raise TypeError
            for elmnt in elements:
                self.add_element(elmnt)

    def add_element(self, element):
        if not isinstance(element, Element):
            raise TypeError

        expType = settings.experiment.type  # 'web' or 'qt-wk'

        if expType == 'web' and not isinstance(element, WebElementInterface):
            raise TypeError("%s is not an instance of WebElementInterface" % type(element).__name__)

        if isinstance(self, WebPageInterface) and not isinstance(element, WebElementInterface):
            raise TypeError("%s is not an instance of WebElementInterface" % type(element).__name__)

        if element.name is None:
            element.name = ("%02d" % self._elementNameCounter) + '_' + element.__class__.__name__
            self._elementNameCounter = self._elementNameCounter + 1

        self._elementList.append(element)
        element.added_to_page(self)

    def add_elements(self, *elements):
        for elmnt in elements:
            self.add_element(elmnt)

    @property
    def allow_closing(self):
        return reduce(lambda b, element: element.validate_data() and b, self._elementList, True)

    def closeQuestion(self):
        super(CoreCompositePage, self).closeQuestion()

        for elmnt in self._elementList:
            elmnt.enabled = False

    @property
    def data(self):
        data = super(CoreCompositePage, self).data
        for elmnt in self._elementList:
            data.update(elmnt.data)

        return data

    @property
    def can_display_corrective_hints_in_line(self):
        return reduce(lambda b, element: b and element.can_display_corrective_hints_in_line, self._elementList, True)

    @property
    def show_corrective_hints(self):
        return self._showCorrectiveHints

    @show_corrective_hints.setter
    def show_corrective_hints(self, b):
        b = bool(b)
        self._showCorrectiveHints = b
        for elmnt in self._elementList:
            elmnt.show_corrective_hints = b

    @property
    def corrective_hints(self):
        # only display hints if property is True
        if not self.show_corrective_hints:
            return []

        # get corrective hints for each element
        list_of_lists = []

        for elmnt in self._elementList:
            if not elmnt.can_display_corrective_hints_in_line and elmnt.corrective_hints:
                list_of_lists.append(elmnt.corrective_hints)

        # flatten list
        return [item for sublist in list_of_lists for item in sublist]

    def set_data(self, dictionary):
        for elmnt in self._elementList:
            elmnt.set_data(dictionary)


class WebCompositePage(CoreCompositePage, WebPageInterface):
    def prepare_web_widget(self):
        for elmnt in self._elementList:
            elmnt.prepare_web_widget()

    @property
    def web_widget(self):
        html = ''

        for elmnt in self._elementList:
            if elmnt.web_widget != '' and elmnt.should_be_shown:
                html = html + ('<div class="row with-margin"><div id="elid-%s" class="element">' % elmnt.name) + elmnt.web_widget + '</div></div>'

        return html

    @property
    def web_thumbnail(self):
        '''
        gibt das thumbnail von self._thumbnail_element oder falls self._thumbnail_element nicht gesetzt, das erste thumbnail eines elements aus self._elementList zurueck.

        .. todo:: was ist im fall, wenn thumbnail element nicht gestzt ist? anders verhalten als jetzt???

        '''
        if not self.show_thumbnail:
            return None

        if self._thumbnail_element:
            return self._thumbnail_element.web_thumbnail
        else:
            for elmnt in self._elementList:
                if elmnt.web_thumbnail and elmnt.should_be_shown:
                    return elmnt.web_thumbnail
            return None

    @property
    def css_code(self):
        return reduce(lambda l, element: l + element.css_code, self._elementList, [])

    @property
    def css_urls(self):
        return reduce(lambda l, element: l + element.css_urls, self._elementList, [])

    @property
    def js_code(self):
        return reduce(lambda l, element: l + element.js_code, self._elementList, [])

    @property
    def js_urls(self):
        return reduce(lambda l, element: l + element.js_urls, self._elementList, [])


class CompositePage(WebCompositePage):
    pass


class PagePlaceholder(Page, WebPageInterface):
    def __init__(self, extData={}, **kwargs):
        super(PagePlaceholder, self).__init__(**kwargs)

        self._extData = extData

    @property
    def web_widget(self):
        return ''

    @property
    def data(self):
        data = super(Page, self).data
        data.update(self._extData)
        return data

    @property
    def should_be_shown(self):
        return False

    @should_be_shown.setter
    def should_be_shown(self, b):
        pass

    @property
    def is_jumpable(self):
        return False

    @is_jumpable.setter
    def is_jumpable(self, is_jumpable):
        pass


class DemographicPage(CompositePage):
    def __init__(self, instruction=None, age=True, sex=True, courseOfStudies=True, semester=True, **kwargs):
        super(DemographicPage, self).__init__(**kwargs)

        if instruction:
            self.add_element(element.TextElement(instruction))
        self.add_element(element.TextElement(u"Bitte gib deine persönlichen Datein ein."))
        if age:
            self.add_element(element.TextEntryElement(u"Dein Alter: ", name="age"))

        if sex:
            self.add_element(element.TextEntryElement(u"Dein Geschlecht: ", name="sex"))

        if courseOfStudies:
            self.add_element(element.TextEntryElement(instruction=u"Dein Studiengang: ", name='courseOfStudies'))

        if semester:
            self.add_element(element.TextEntryElement(instruction=u"Dein Fachsemester ", name='semester'))


class AutoHidePage(CompositePage):
    def __init__(self, onHiding=False, onClosing=True, **kwargs):
        super(AutoHidePage, self).__init__(**kwargs)

        self._onClosing = onClosing
        self._onHiding = onHiding

    def on_hiding_widget(self):
        if self._onHiding:
            self.should_be_shown = False

    def closeQuestion(self):
        super(AutoHidePage, self).closeQuestion()
        if self._onClosing:
            self.should_be_shown = False


class ExperimentFinishPage(CompositePage):
    def on_showing_widget(self):
        if 'firstShowTime' not in self._data:
            exp_title = TextElement('Informationen zur Session:', font='big')

            exp_infos = '<table style="border-style: none"><tr><td width="200">Experimentname:</td><td>' + self._experiment.name + '</td></tr>'
            exp_infos = exp_infos + '<tr><td>Experimenttyp:</td><td>' + self._experiment.type + '</td></tr>'
            exp_infos = exp_infos + '<tr><td>Experimentversion:</td><td>' + self._experiment.version + '</td></tr>'
            exp_infos = exp_infos + '<tr><td>Session-ID:</td><td>' + self._experiment.uuid + '</td></tr>'
            exp_infos = exp_infos + '<tr><td>Log-ID:</td><td>' + self._experiment.uuid[:6] + '</td></tr>'
            exp_infos = exp_infos + '</table>'

            exp_info_element = TextElement(exp_infos)

            self.add_elements(exp_title, exp_info_element, ExperimenterMessages())

        super(ExperimentFinishPage, self).on_showing_widget()


class HeadOpenSectionCantClose(CompositePage):
    def __init__(self, **kwargs):
        super(HeadOpenSectionCantClose, self).__init__(**kwargs)

        self.add_element(element.TextElement("Nicht alle Fragen konnten Geschlossen werden. Bitte korrigieren!!!<br /> Das hier wird noch besser implementiert"))


class MongoSaveCompositePage(CompositePage):
    def __init__(self, host, database, collection, user, password, error='ignore', hideData=True, *args, **kwargs):
        super(MongoSaveCompositePage, self).__init__(*args, **kwargs)
        self._host = host
        self._database = database
        self._collection = collection
        self._user = user
        self._password = password
        self._error = error
        self._hide_data = hideData
        self._saved = False

    @property
    def data(self):
        if self._hide_data:
            # this is needed for some other functions to work properly
            data = {'tag': self.tag,
                    'uid': self.uid}
            return data
        else:
            return super(MongoSaveCompositePage, self).data

    def closeQuestion(self):
        rv = super(MongoSaveCompositePage, self).closeQuestion()
        if self._saved:
            return rv
        from pymongo import MongoClient
        try:
            client = MongoClient(self._host)
            db = client[self._database]
            db.authenticate(self._user, self._password)
            col = db[self._collection]
            data = super(MongoSaveCompositePage, self).data
            data.pop('firstShowTime', None)
            data.pop('closingTime', None)
            col.insert(data)
            self._saved = True
        except Exception as e:
            if self._error != 'ignore':
                raise e
        return rv


####################
# Page Mixins
####################

class WebTimeoutMixin(object):

    def __init__(self, timeout, **kwargs):
        super(WebTimeoutMixin, self).__init__(**kwargs)

        self._end_link = 'unset'
        self._run_timeout = True
        self._timeout = timeout
        if settings.debugmode and settings.debug.reduceCountdown:
            self._timeout = int(settings.debug.reducedCountdownTime)

    def added_to_experiment(self, experiment):
        super(WebTimeoutMixin, self).added_to_experiment(experiment)
        self._end_link = self._experiment.user_interface_controller.add_callable(self.callback)

    def callback(self, *args, **kwargs):
        self._run_timeout = False
        self._experiment.user_interface_controller.update_with_user_input(kwargs)
        return self.on_timeout(*args, **kwargs)

    def on_hiding_widget(self):
        self._run_timeout = False
        super(WebTimeoutMixin, self).on_hiding_widget()

    def on_timeout(self, *args, **kwargs):
        pass

    @property
    def js_code(self):
        code = (5, '''
            $(document).ready(function(){
                var start_time = new Date();
                var timeout = %s;
                var action_url = '%s';

                var update_counter = function() {
                    var now = new Date();
                    var time_left = timeout - Math.floor((now - start_time) / 1000);
                    if (time_left < 0) {
                        time_left = 0;
                    }
                    $(".timeout-label").html(time_left);
                    if (time_left > 0) {
                        setTimeout(update_counter, 200);
                    }
                };
                update_counter();

                var timeout_function = function() {
                    $("#form").attr("action", action_url);
                    $("#form").submit();
                };
                setTimeout(timeout_function, timeout*1000);
            });
        ''' % (self._timeout, self._end_link))
        js_code = super(WebTimeoutMixin, self).js_code
        if self._run_timeout:
            js_code.append(code)
        else:
            js_code.append((5, '''$(document).ready(function(){$(".timeout-label").html(0);});'''))
        return js_code


class WebTimeoutForwardMixin(WebTimeoutMixin):
    def on_timeout(self, *args, **kwargs):
        self._experiment.user_interface_controller.move_forward()


class WebTimeoutCloseMixin(WebTimeoutMixin):
    def on_timeout(self, *args, **kwargs):
        self.closeQuestion()


class HideButtonsMixin(object):
    def _on_showing_widget(self):
        self._experiment.user_interface_controller.layout.forward_enabled = False
        self._experiment.user_interface_controller.layout.backward_enabled = False
        self._experiment.user_interface_controller.layout.jump_list_enabled = False
        self._experiment.user_interface_controller.layout.finish_disabled = True

        super(HideButtonsMixin, self)._on_showing_widget()

    def _on_hiding_widget(self):
        self._experiment.user_interface_controller.layout.forward_enabled = True
        self._experiment.user_interface_controller.layout.backward_enabled = True
        self._experiment.user_interface_controller.layout.jump_list_enabled = True
        self._experiment.user_interface_controller.layout.finish_disabled = False

        super(HideButtonsMixin, self)._on_hiding_widget()


####################
# Questions with Mixins
####################

class WebTimeoutForwardPage(WebTimeoutForwardMixin, WebCompositePage):
    pass


class WebTimeoutClosePage(WebTimeoutCloseMixin, WebCompositePage):
    pass
