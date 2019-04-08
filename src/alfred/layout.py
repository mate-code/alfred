# -*- coding:utf-8 -*-

'''
.. moduleauthor:: Paul Wiemann <paulwiemann@gmail.com>

.. todo:: Beim Modulimport wird ein Fehler angezeigt. Gibt es wirklich eine Klasse *Template* in **jinja2**?
'''
from __future__ import absolute_import


from builtins import map
from builtins import range
from builtins import object
import os.path
from abc import ABCMeta, abstractmethod
from jinja2 import Environment, PackageLoader
from future.utils import with_metaclass

from ._core import package_path

jinja_env = Environment(loader=PackageLoader('alfred', 'templates'))


class Layout(with_metaclass(ABCMeta, object)):
    def __init__(self):
        self._experiment = None
        self._uiController = None
        self._backwardText = u"Zurück"
        self._forwardText = u"Weiter"
        self._finishText = u"Beenden"
        self._backwardEnabled = True
        self._forwardEnabled = True
        self._finishedDisabled = False
        self._jumpListEnabled = True
        self._jumpList = []

    def activate(self, experiment, ui_controller):
        self._experiment = experiment
        self._uiController = ui_controller

    def deactivate(self):
        self._experiment = None
        self._uiController = None

    @abstractmethod
    def render(self, widget):
        pass

    @property
    def backward_enabled(self):
        return self._backwardEnabled

    @backward_enabled.setter
    def backward_enabled(self, b):
        self._backwardEnabled = b

    @property
    def forward_enabled(self):
        return self._forwardEnabled

    @forward_enabled.setter
    def forward_enabled(self, b):
        self._forwardEnabled = b

    @property
    def finish_disabled(self):
        return self._finishedDisabled

    @finish_disabled.setter
    def finish_disabled(self, b):
        self._finishedDisabled = b

    @property
    def backward_text(self):
        return self._backwardText

    @backward_text.setter
    def backward_text(self, text):
        self._backwardText = text

    @property
    def forward_text(self):
        return self._forwardText

    @forward_text.setter
    def forward_text(self, text):
        self._forwardText = text

    @property
    def finish_text(self):
        return self._finishText

    @finish_text.setter
    def finish_text(self, text):
        self._finishText = text

    @property
    def jump_list_enabled(self):
        return self._jumpListEnabled

    @jump_list_enabled.setter
    def jump_list_enabled(self, b):
        self._jumpListEnabled = b


class BaseWebLayout(Layout):

    def __init__(self):
        super(BaseWebLayout, self).__init__()
        self._style_urls = []
        self._js_urls = []
        self._template = jinja_env.get_template('base_layout.html')

    def activate(self, experiment, ui_controller):
        super(BaseWebLayout, self).activate(experiment, ui_controller)
        # add css files
        self._style_urls.append((99, self._uiController.add_static_file(os.path.join(package_path(), 'static/css/base_web_layout.css'), content_type="text/css")))
        self._style_urls.append((1, self._uiController.add_static_file(os.path.join(package_path(), 'static/css/bootstrap.min.css'), content_type="text/css")))
        self._style_urls.append((2, self._uiController.add_static_file(os.path.join(package_path(), 'static/css/jquery-ui.css'), content_type="text/css")))
        # self._style_urls.append(self._uiController.add_static_file(os.path.join(package_path(), 'static/css/app.css'), content_type="text/css"))

        # add js files
        self._js_urls.append((0o1,
                              self._uiController.add_static_file(
                                  os.path.join(package_path(), 'static/js/jquery-1.8.3.min.js'),
                                  content_type="text/javascript")
                              ))
        self._js_urls.append((0o2, self._uiController.add_static_file(os.path.join(package_path(), 'static/js/bootstrap.min.js'), content_type="text/javascript")))
        self._js_urls.append((0o3, self._uiController.add_static_file(os.path.join(package_path(), 'static/js/jquery-ui.js'), content_type="text/javascript")))

        self._js_urls.append((10,
                              self._uiController.add_static_file(
                                  os.path.join(package_path(), 'static/js/baseweblayout.js'),
                                  content_type="text/javascript")
                              ))

        self._logo_url = self._uiController.add_static_file(os.path.join(package_path(), 'static/img/alfred_logo.png'), content_type="image/png")

    @property
    def css_code(self):
        return []

    @property
    def css_urls(self):
        return self._style_urls

    @property
    def javascript_code(self):
        return []

    @property
    def javascript_urls(self):
        return self._js_urls

    def render(self):

        d = {}
        d['logo_url'] = self._logo_url
        d['widget'] = self._experiment.question_controller.current_question.web_widget

        if self._experiment.question_controller.current_title:
            d['title'] = self._experiment.question_controller.current_title

        if self._experiment.question_controller.current_subtitle:
            d['subtitle'] = self._experiment.question_controller.current_subtitle

        if self._experiment.question_controller.current_status_text:
            d['statustext'] = self._experiment.question_controller.current_status_text

        if not self._experiment.question_controller.current_question.can_display_corrective_hints_in_line \
                and self._experiment.question_controller.current_question.corrective_hints:
            d['corrective_hints'] = self._experiment.question_controller.current_question.corrective_hints

        if self.backward_enabled and self._experiment.question_controller.can_move_backward:
            d['backward_text'] = self.backward_text

        if self.forward_enabled:
            if self._experiment.question_controller.can_move_forward:
                d['forward_text'] = self.forward_text
            else:
                if not self._finishedDisabled:
                    d['finish_text'] = self.finish_text

        if self.jump_list_enabled and self._experiment.question_controller.jumplist:
            jmplist = self._experiment.question_controller.jumplist
            for i in range(len(jmplist)):
                jmplist[i] = list(jmplist[i])
                jmplist[i][0] = '.'.join(map(str, jmplist[i][0]))
            d['jumpList'] = jmplist

        messages = self._experiment.message_manager.get_messages()
        if messages:
            for message in messages:
                message.level = '' if message.level == 'warning' else 'alert-' + message.level  # level to bootstrap
            d['messages'] = messages

        return self._template.render(d)

    @property
    def backward_link(self):
        return self._backwardLink

    @backward_link.setter
    def backward_link(self, link):
        self._backwardLink = link

    @property
    def forward_link(self):
        return self._forwardLink

    @forward_link.setter
    def forward_link(self, link):
        self._forwardLink = link


class GoeWebLayout(Layout):
    def __init__(self):
        super(GoeWebLayout, self).__init__()
        self._style_urls = []
        self._js_urls = []
        self._template = jinja_env.get_template('goe_layout.html')

    def activate(self, experiment, ui_controller):
        super(GoeWebLayout, self).activate(experiment, ui_controller)
        # add css files
        self._style_urls.append((99, self._uiController.add_static_file(os.path.join(package_path(), 'static/css/goe_web_layout.css'), content_type="text/css")))
        self._style_urls.append((1, self._uiController.add_static_file(os.path.join(package_path(), 'static/css/bootstrap.min.css'), content_type="text/css")))
        self._style_urls.append((2, self._uiController.add_static_file(os.path.join(package_path(), 'static/css/jquery-ui.css'), content_type="text/css")))
        # self._style_urls.append(self._uiController.add_static_file(os.path.join(package_path(), 'static/css/app.css'), content_type="text/css"))

        # add js files
        self._js_urls.append((0o1,
                              self._uiController.add_static_file(
                                  os.path.join(package_path(), 'static/js/jquery-1.8.3.min.js'),
                                  content_type="text/javascript")
                              ))
        self._js_urls.append((0o2, self._uiController.add_static_file(os.path.join(package_path(), 'static/js/bootstrap.min.js'), content_type="text/javascript")))
        self._js_urls.append((0o3, self._uiController.add_static_file(os.path.join(package_path(), 'static/js/jquery-ui.js'), content_type="text/javascript")))

        self._js_urls.append((10,
                              self._uiController.add_static_file(
                                  os.path.join(package_path(), 'static/js/baseweblayout.js'),
                                  content_type="text/javascript")
                              ))

        self._logo_url = self._uiController.add_static_file(os.path.join(package_path(), 'static/img/uni_goe_logo.png'), content_type="image/png")

    @property
    def css_code(self):
        return []

    @property
    def css_urls(self):
        return self._style_urls

    @property
    def javascript_code(self):
        return []

    @property
    def javascript_urls(self):
        return self._js_urls

    def render(self):

        d = {}
        d['logo_url'] = self._logo_url
        d['widget'] = self._experiment.question_controller.current_question.web_widget

        if self._experiment.question_controller.current_title:
            d['title'] = self._experiment.question_controller.current_title

        if self._experiment.question_controller.current_subtitle:
            d['subtitle'] = self._experiment.question_controller.current_subtitle

        if self._experiment.question_controller.current_status_text:
            d['statustext'] = self._experiment.question_controller.current_status_text

        if not self._experiment.question_controller.current_question.can_display_corrective_hints_in_line \
                and self._experiment.question_controller.current_question.corrective_hints:
            d['corrective_hints'] = self._experiment.question_controller.current_question.corrective_hints

        if self.backward_enabled and self._experiment.question_controller.can_move_backward:
            d['backward_text'] = self.backward_text

        if self.forward_enabled:
            if self._experiment.question_controller.can_move_forward:
                d['forward_text'] = self.forward_text
            else:
                if not self._finishedDisabled:
                    d['finish_text'] = self.finish_text

        if self.jump_list_enabled and self._experiment.question_controller.jumplist:
            jmplist = self._experiment.question_controller.jumplist
            for i in range(len(jmplist)):
                jmplist[i] = list(jmplist[i])
                jmplist[i][0] = '.'.join(map(str, jmplist[i][0]))
            d['jumpList'] = jmplist

        messages = self._experiment.message_manager.get_messages()
        if messages:
            for message in messages:
                message.level = '' if message.level == 'warning' else 'alert-' + message.level  # level to bootstrap
            d['messages'] = messages

        return self._template.render(d)

    @property
    def backward_link(self):
        return self._backwardLink

    @backward_link.setter
    def backward_link(self, link):
        self._backwardLink = link

    @property
    def forward_link(self):
        return self._forwardLink

    @forward_link.setter
    def forward_link(self, link):
        self._forwardLink = link
