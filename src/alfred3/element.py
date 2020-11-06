# -*- coding:utf-8 -*-

"""
.. moduleauthor:: Paul Wiemann <paulwiemann@gmail.com>

**element** contains general baseclass :class:`.element.Element` and its' children, which can be added to
:class:`.page.CompositePage` (see table for an overview). It also contains abstract baseclasses for
different interfaces (:class:`.element.WebElementInterface`, :class:`.element.QtElementInterface`), which
must also be inherited by new child elements of :class:`.element.Element` to establish interface compatibility.

===================== ===============================================================
Name                  Description
===================== ===============================================================
TextElement           A simple text display (can contain html code)
DataElement           Element for saving Variables into Data (without display)
TextEntryElement      A singleline textedit with instruction text
TextAreaElement       A multiline textedit field with instruction text
RegEntryElement       An element which compares input with a regular expression
NumberEntryElement    An entry element for numbers
PasswordElement       An element which compares input with a predefined password
LikertMatrix          A matrix with multiple items and a predefined number of levels
LikertElement         A likert scale with n levels and different labels
SingleChoiceElement   A list of items, one of which can be selected
MultipleChoiceElement A list of items from which multiple can be selected
ImageElement          Display an image file
TripleBarChartElement Display a chart with three different bars (temporary)
===================== ===============================================================

"""
from __future__ import absolute_import, division

import json
import random
import re
import string
import logging
import copy
from abc import ABCMeta, abstractproperty
from builtins import object, range, str
from functools import reduce
from uuid import uuid4
from pathlib import Path
from typing import Tuple, List, Union

from future import standard_library
from future.utils import with_metaclass
from jinja2 import Environment, PackageLoader, Template
from past.utils import old_div

import cmarkgfm

from . import alfredlog, settings, page
from ._helper import alignment_converter, fontsize_converter, is_url
from .exceptions import AlfredError

standard_library.install_aliases()

jinja_env = Environment(loader=PackageLoader(__name__, "templates/elements"))


class Element(object):
    """
    **Description:** Baseclass for every element with basic arguments.

    :param str name: Name of Element.
    :param str alignment: Alignment of element in widget container ('left' as standard, 'center', 'right').
    :param str/int font_size: Font size used in element ('normal' as standard, 'big', 'huge', or int value setting font size in pt).
    :param bool instance_level_logging: If *True*, will spawn a new,
        individually configurable logger for the given class instance.
        (Defaults to *False*)
    """

    def __init__(
        self,
        name: str = None,
        showif: dict = None,
        should_be_shown_filter_function=None,
        instance_level_logging: bool = False,
        element_width: List[int] = None,
        position: str = "center",
        **kwargs,
    ):
        if not isinstance(self, WebElementInterface):
            raise AlfredError("Element must implement WebElementInterface.")

        if name is not None:
            if not re.match(r"^%s$" % "[-_A-Za-z0-9]*", name):
                raise ValueError(
                    "Element names may only contain following charakters: A-Z a-z 0-9 _ -"
                )

        self._name = name

        self._page = None
        self._enabled = True
        self._show_corrective_hints = False
        self._should_be_shown = True
        self._should_be_shown_filter_function = (
            should_be_shown_filter_function
            if should_be_shown_filter_function is not None
            else lambda exp: True
        )

        self._alignment = kwargs.pop("alignment", "left")
        self._font_size = kwargs.pop("font_size", "normal")
        self._element_width = element_width
        self.position = position
        self._maximum_widget_width = None
        self.experiment = None

        self._showif = showif if showif else {}
        self._showif_js = []

        if kwargs != {}:
            raise ValueError("Parameter '%s' is not supported." % list(kwargs.keys())[0])

        if instance_level_logging and not self._name:
            raise ValueError("For instance level logging, the element must have a name.")

        self.instance_level_logging = instance_level_logging
        self.log = alfredlog.QueuedLoggingInterface(base_logger=__name__)
    def showif(self):
        if self._showif:
            conditions = []
            for page_uid, condition in self._showif.items():
                if page_uid == self.page.uid:
                    continue
                d = self.experiment.get_page_data(page_uid)
                for target, value in condition.items():
                    try:
                        conditions.append(d[target] == value)
                    except KeyError:
                        self.log.warning(f"You defined a showif '{target} == {value}' for page with uid='{page_uid}', but {target} was not found on the page. The element was shown.")
            return conditions
        else:
            return [True]
    
    @property
    def position(self):
        return self._position
    
    @position.setter
    def position(self, value):
        if value == "left":
            self._position = "start"
        elif value == "right":
            self._position = "end"
        else:
            self._position = value

    @property
    def font_size(self):
        return fontsize_converter(self._font_size)

    @property
    def element_width(self):
        width = self._format_element_width(self._element_width)
        if self.experiment.config.getboolean("layout", "responsive", fallback=True):
            return " ".join(width)
        else:
            return width[0]

    @element_width.setter
    def element_width(self, value: List[int]):
        self._element_width = self._format_element_width(element_width=value)

    def _format_element_width(self, element_width: List[int]):
        out = []

        if not element_width:
            out.append("col-12")
            return out

        for i, w in enumerate(element_width):
            if i == 0:
                out.append(f"col-{w}")
            elif i == 1:
                out.append(f"col-sm-{w}")
            elif i == 2:
                out.append(f"col-md-{w}")
            elif i == 3:
                out.append(f"col-lg-{w}")
            elif i == 4:
                out.append(f"col-xl-{w}")

        return out

    @property
    def name(self):
        """
        Property **name** marks a general identifier for element, which is also used as variable name in experimental datasets.
        Stored input data can be retrieved from dictionary returned by :meth:`.data_manager.DataManager.get_data`.
        """
        return self._name

    @name.setter
    def name(self, name):
        if not isinstance(name, str):
            raise TypeError
        self._name = name

    @property
    def maximum_widget_width(self):
        return self._maximum_widget_width

    @maximum_widget_width.setter
    def maximum_widget_width(self, maximum_widget_width):
        if not isinstance(maximum_widget_width, int):
            raise TypeError
        self._maximum_widget_width = maximum_widget_width

    def added_to_page(self, q):
        from . import page

        if not isinstance(q, page.PageCore):
            raise TypeError()

        self._page = q
        if self.name is None:
            self.name = self.page.generate_element_name(self)

        if self._page.experiment:
            self.added_to_experiment(self._page.experiment)
        
        on_current_page = self._showif.get(self.page.uid, None)
        if on_current_page:
            t = jinja_env.get_template("showif.js")
            js = t.render(showif=on_current_page, element=self.name)
            self._showif_js.append((7, js))

    def added_to_experiment(self, experiment):
        self.experiment = experiment
        queue_logger_name = self.prepare_logger_name()
        self.log.queue_logger = logging.getLogger(queue_logger_name)
        self.log.session_id = self.experiment.config.get("metadata", "session_id")
        self.log.log_queued_messages()

    @property
    def data(self):
        """
        Property **data** contains a dictionary with input data of element.
        """
        return {}

    @property
    def enabled(self):
        """
        Property **enabled** describes a general property of all (input) elements. Only if set to True, element can be edited.

        :param bool enabled: Property setter variable.
        """
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        if not isinstance(enabled, bool):
            raise TypeError

        self._enabled = enabled

    @property
    def can_display_corrective_hints_in_line(self):
        return False

    @property
    def alignment(self):
        return self._alignment

    @property
    def corrective_hints(self):
        return []

    @property
    def show_corrective_hints(self):
        return self._show_corrective_hints

    @show_corrective_hints.setter
    def show_corrective_hints(self, b):
        self._show_corrective_hints = bool(b)

    def validate_data(self):
        return True

    def set_should_be_shown_filter_function(self, f):
        """
        Sets a filter function. f must take Experiment as parameter
        :type f: function
        """
        self._should_be_shown_filter_function = f

    def remove_should_be_shown_filter_function(self):
        """
        remove the filter function
        """
        self._should_be_shown_filter_function = lambda exp: True

    @property
    def should_be_shown(self):
        """
        Returns True if should_be_shown is set to True (default) and all should_be_shown_filter_functions return True.
        Otherwise False is returned
        """
        cond1 = self._should_be_shown
        cond2 = self._should_be_shown_filter_function(self.experiment)
        cond3 = all(self.showif())
        return cond1 and cond2 and cond3

    @should_be_shown.setter
    def should_be_shown(self, b):
        """
        sets should_be_shown to b.

        :type b: bool
        """
        if not isinstance(b, bool):
            raise TypeError("should_be_shown must be an instance of bool")
        self._should_be_shown = b

    def prepare_logger_name(self) -> str:
        """Returns a logger name for use in *self.log.queue_logger*.

        The name has the following format::

            exp.exp_id.module_name.class_name.class_uid
        
        with *class_uid* only added, if 
        :attr:`~Element.instance_level_logging` is set to *True*.
        """
        # remove "alfred3" from module name
        module_name = __name__.split(".")
        module_name.pop(0)

        name = []
        name.append("exp")
        name.append(self.experiment.exp_id)
        name.append(".".join(module_name))
        name.append(type(self).__name__)

        if self.instance_level_logging and self._name:
            name.append(self._name)

        return ".".join(name)

    @property
    def page(self):
        return self._page

    @property
    def tree(self):
        return self.page.tree

    @property
    def identifier(self):
        return self.tree.replace("rootSection_", "") + "_" + self._name


class WebElementInterface(with_metaclass(ABCMeta, object)):
    """
    Abstract class **WebElementInterface** contains properties and methods allowing elements to be used and displayed
    in experiments of type 'web'.
    """

    @abstractproperty
    def web_widget(self):
        pass

    def prepare_web_widget(self):
        pass

    @property
    def web_thumbnail(self):
        return None

    def set_data(self, data):
        pass

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


class HorizontalLine(Element, WebElementInterface):
    def __init__(self, strength=1, color="black", **kwargs):
        """
        **HorizontalLine** allows display of a simple divider in pages.

        :param int strength: Set line thickness (in pixel).
        :param str color: Set line color (color argument as string).
        """
        super(HorizontalLine, self).__init__(**kwargs)

        self._strength = strength
        self._color = color

    @property
    def web_widget(self):

        widget = '<hr class="horizontal-line" style="%s %s">' % (
            "height: %spx;" % self._strength,
            "background-color: %s;" % self._color,
        )

        return widget


class ProgressBar(Element, WebElementInterface):
    def __init__(
        self,
        instruction="",
        bar_range=(0, 100),
        bar_value=50,
        bar_width=None,
        instruction_width=None,
        instruction_height=None,
        **kwargs,
    ):
        """
        **ProgressBar** allows display of a manually controlled progress bar.
        """
        super(ProgressBar, self).__init__(**kwargs)

        self._instruction = instruction
        self._instruction_width = instruction_width
        self._instruction_height = instruction_height
        self._bar_range = bar_range
        self._bar_value = float(bar_value)

        if bar_width:
            self._bar_width = bar_width
        else:
            self._bar_width = None

        self._progress_bar = None

    @property
    def bar_value(self):
        return self._bar_value

    @bar_value.setter
    def bar_value(self, value):
        self._bar_value = value
        if self._progress_bar:
            self._progress_bar.set_value(self._bar_value)
            self._progress_bar.repaint()

    @property
    def web_widget(self):
        if self._bar_range[1] - self._bar_range[0] == 0:
            raise ValueError("bar_range in web progress bar must be greater than 0")

        widget = '<div class="progress-bar"><table class="%s" style="font-size: %spt;">' % (
            alignment_converter(self._alignment, "container"),
            fontsize_converter(self._font_size),
        )

        widget = widget + '<tr><td><table class="%s"><tr><td style="%s %s">%s</td>' % (
            alignment_converter(self._alignment, "container"),
            "width: %spx;" % self._instruction_width
            if self._instruction_width is not None
            else "",
            "height: %spx;" % self._instruction_height
            if self._instruction_height is not None
            else "",
            self._instruction,
        )

        widget = (
            widget
            + '<td><meter value="%s" min="%s" max="%s" style="font-size: %spt; width: %spx; margin-left: 5px;"></meter></td>'
            % (
                self._bar_value,
                self._bar_range[0],
                self._bar_range[1],
                fontsize_converter(self._font_size) + 5,
                self._bar_width if self._bar_width is not None else "200",
            )
        )

        widget = widget + '<td style="font-size: %spt; padding-left: 5px;">%s</td>' % (
            fontsize_converter(self._font_size),
            str(int(old_div(self._bar_value, (self._bar_range[1] - self._bar_range[0]) * 100)))
            + "%",
        )

        widget = widget + "</tr></table></td></tr></table></div>"

        return widget


class TextElement(Element, WebElementInterface):
    """Displays text.

        You can use GitHub-flavored Markdown syntax to format your text
        (see https://guides.github.com/features/mastering-markdown/ for
        details).
        Additionally, you can use raw html for advanced formatting.

        Text can be entered directly through the `text` parameter, or
        it can be read from a file by specifying the 'path' parameter.
        Note that you can only use one of these options, if you specify
        both, the element will raise an error.

        .. example::
            # Text element that is displayed as full-width on very 
            # small screens and as half-width on small and larger 
            # screens.
            text = TextElement('Text display', element_width=[12, 6])
        
        .. example::
        # Text element that is always displayed as full-width
            text = TextElement('Text display', element_width=[12])

        Args:
            text: Text to be displayed.
            text_width: Text width in px. **Deprecated** for responsive
                design (v1.5). Use `element_width` instead, when using
                the responsive design.
            text_height: Element height in px.
            font_size: Font size for normal text in the element. Values
                can be 'normal', 'big', 'huge', or any integer. Integers
                are used directly as font size in pt.
            path: Filepath to a textfile (relative to the experiment 
                directory).
            position: Horizontal position of the full element on the 
                page. Values can be 'left', 'center' (default), 'end',
                or any valid value for the justify-content flexbox
                utility (see https://getbootstrap.com/docs/4.0/utilities/flex/#justify-content).
            alignment: Alignment of text inside the element. Values can
                be 'left' (default), 'center', 'right', and 'justify'.
            element_width = A list of relative width definitions. The
                list can contain up to 5 width definitions, given as
                integers from 1 to 12. They refer to Bootstrap 4's
                12-column-grid system 
                (https://getbootstrap.com/docs/4.0/layout/grid/). The
                horizontal width is divided into 12 equal parts. 
                Therefore, a value of 12 indicates a full-width element, 
                a value of 6 a half-width elment, and so on. The 
                elements of the list refer to Bootstrap's breakpoints,
                i.e. [xs, sm, md, lg, xl].
                Defaults to [12, 11, 11, 10, 8], which usually provides
                a reader-friendly layout.
        """

    def __init__(
        self,
        text: str = None,
        text_width: int = None,
        text_height: int = None,
        position: str = "center",
        path: Union[Path, str] = None,
        **kwargs,
    ):

        """Constructor method."""
        super(TextElement, self).__init__(position=position, **kwargs)
        self._template = jinja_env.get_template("TextElement.html")

        self._text = text
        self._text_width = text_width
        self._text_height = text_height
        self._text_label = None
        self._path = path

        if self._text and self._path:
            raise ValueError("You can only specify one of 'text' and 'path'.")

    @property
    def text(self):
        if self._path:
            p = Path(self.experiment.path) / self._path
            return p.read_text()
        else:
            return self._text

    @property
    def rendered_text(self):
        return cmarkgfm.github_flavored_markdown_to_html(self.text)

    @text.setter
    def text(self, text):
        self._text = text
        if self._text_label:
            self._text_label.set_text(self._text)
            self._text_label.repaint()
    
    @property
    def element_width(self):
        if self.experiment.config.getboolean("layout", "responsive", fallback=True):
            width = self._element_width if self._element_width is not None else [12, 11, 11, 10, 9]
        else:
            width = self._element_width if self._element_width is not None else [9]
        return " ".join(self._format_element_width(width))

    @property
    def responsive_widget(self):
        d = {}
        d["name"] = self.name
        d["position"] = self.position
        d["element_width"] = self.element_width
        d["element_class"] = "text-element"
        d["text"] = self.rendered_text
        d["hide"] = "hide" if self._showif_js != [] else ""
        d["align"] = f"text-{self._alignment}"
        size = f"font-size: {fontsize_converter(self._font_size)};"
        width = f"width: {self._text_width};" if self._text_width is not None else ""
        height = f"height: {self._text_height};" if self._text_height is not None else ""

        d["style"] = f"{size} {width} {height}"

        return self._template.render(d)

    @property
    def css_code(self):
        styles = []
        if self._text_height:
            styles.append(f"height: {self._text_height}px;")
        if self._font_size:
            styles.append(f"font-size: {self.font_size}pt;")

        code = f"#elid-{self.name}" + "{" + " ".join(styles) + "}"
        return [(10, code)]

    @property
    def web_widget(self):
        widget = (
            '<div class="text-element"><div class="%s" style="font-size: %spt; %s %s">%s</div></div>'
            % (
                alignment_converter(self._alignment, "both"),
                fontsize_converter(self._font_size),
                "width: %spx;" % self._text_width if self._text_width is not None else "",
                "height: %spx;" % self._text_height if self._text_height is not None else "",
                self.rendered_text,
            )
        )

        return widget
    
    @property
    def js_code(self):
        return self._showif_js


class CodeElement(Element, WebElementInterface):
    def __init__(
        self,
        text=None,
        lang="nohighlight",
        style="atom-one-light",
        first=True,
        toggle_button=True,
        button_label="Show / Hide Code",
        hide_by_default=True,
        **kwargs,
    ):
        """
        **CodeElement** allows display of highlighted code blocks.

        :param str text: Text to be displayed.
        :param str/int font_size: Fontsize used in CodeElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param str lang: Programming language that is used in text. The default uses no highlighing.
        :param str style: Highlighting style to use. Styles can be found at https://highlightjs.org/static/demo/
        :param bool first: Indicates, whether the current CodeElement is the first CodeElement on the current page. If False, the highlight.js components are not imported again by the element.
        :param bool toggle_button: If True, a button is included that allows users to toggle the display of the code block.
        :param str button_label: Text to be shown on the toggle button.
        :param bool hide_by_default: If True, the default state of the code block is hidden. Only works, if toggle_button is True.
        """
        super(CodeElement, self).__init__(**kwargs)

        self._text = text
        self._lang = lang
        self._style = style
        self._first = first
        self._id = str(uuid4())
        self._toggle_button = toggle_button
        self._button_label = button_label
        if hide_by_default and toggle_button:
            self._div_class = "hidden"
        else:
            self._div_class = ""

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        self._text = text

    @property
    def web_widget(self):
        if self._toggle_button:
            button = '<a class="btn" id="button-{id}" href="#">{button_label}</a>'.format(
                id=self._id, button_label=self._button_label
            )
        else:
            button = ""

        widget = (
            button
            + '<div id={id} class="{div_class}"><pre><code style="white-space: pre;" class="{lang}"\
         style="font-size:{fontsize}">{text}</code></pre></div>'.format(
                id=self._id,
                div_class=self._div_class,
                lang=self._lang,
                text=self._text,
                fontsize=fontsize_converter(self._font_size),
            )
        )

        return widget

    @property
    def css_urls(self):

        if self._first:
            css = "//cdnjs.cloudflare.com/ajax/libs/highlight.js/9.15.9/styles/{style}.min.css".format(
                style=self._style
            )
            return [(10, css)]
        else:
            return []

    @property
    def js_urls(self):

        if self._first:
            js = "//cdnjs.cloudflare.com/ajax/libs/highlight.js/9.15.9/highlight.min.js"
            return [(10, js)]
        else:
            return []

    @property
    def js_code(self):

        if self._toggle_button:
            button_js = '$(function() {{$( "#button-{id}" ).click(function() {{$( "#{id}" ).toggle();}});}});'.format(
                id=self._id
            )
        else:
            button_js = ""

        if self._first:
            js = "hljs.initHighlightingOnLoad();"
            return [(11, js), (12, button_js)]
        else:

            return [(11, button_js)]


class DataElement(Element, WebElementInterface):
    def __init__(self, variable, description=None, **kwargs):
        """
        **DataElement** returns no widget, but can save a variable of any type into experiment data.

        :param str variable: Variable to be stored into experiment data.
        """
        super(DataElement, self).__init__(**kwargs)
        self._variable = variable
        self.description = description

    @property
    def variable(self):
        return self._variable

    @variable.setter
    def variable(self, variable):
        self._variable = variable

    @property
    def web_widget(self):
        return ""

    @property
    def data(self):
        return {self.name: self._variable}

    @property
    def encrypted_data(self):
        encrypted_variable = self.experiment.encrypt(self._variable)
        return {self.name: encrypted_variable}

    @property
    def codebook_data_flat(self):
        data = {}
        data["name"] = self.name
        data["tree"] = self.tree.replace("rootSection_", "")
        data["identifier"] = self.identifier
        data["page_title"] = self.page.title
        data["element_type"] = type(self).__name__
        data["description"] = self.description
        data["duplicate_identifier"] = False
        data["unlinked"] = True if isinstance(self.page, page.UnlinkedDataPage) else False
        return data

    @property
    def codebook_data(self):
        return {self.identifier: self.codebook_data_flat}


class InputElement(Element):
    """
    Class **InputElement** is the base class for any element allowing data input.

    :param bool force_input: Sets user input to be mandatory (False as standard or True).
    :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.

    .. todo:: Parent class :class:`.element.Element` has method *corrective_hints()*, but not sure why this is necessary, since corrective_hints only make sense in input elements, right?
    """

    def __init__(
        self,
        force_input=False,
        no_input_corrective_hint=None,
        debug_string=None,
        debug_value=None,
        default=None,
        description=None,
        **kwargs,
    ):
        super(InputElement, self).__init__(**kwargs)
        self._input = ""
        self._force_input = force_input
        self._no_input_corrective_hint = no_input_corrective_hint
        self._debug_string = debug_string
        self._debug_value = debug_value
        self.description = description
        self.default = default

        if not self._debug_value:
            if self._debug_string:
                self._debug_value = self._debug_string

        if default is not None:
            self._input = default

    def added_to_experiment(self, experiment):
        super().added_to_experiment(experiment)

        if self.experiment.config.getboolean("general", "debug"):
            if self._debug_value:
                self._input = self._debug_value
            else:
                cls_name = self.__class__.__name__
                self._input = self.experiment.config.get("debug", cls_name, fallback=cls_name)

    def validate_data(self):
        return not self._force_input or not self._should_be_shown or bool(self._input)

    @property
    def corrective_hints(self):
        if not self.show_corrective_hints:
            return []
        if self._force_input and self._input == "":
            return [self.no_input_hint]
        else:
            return super(InputElement, self).corrective_hints

    @property
    def no_input_hint(self):
        if self._no_input_corrective_hint:
            return self._no_input_corrective_hint
        return self.default_no_input_hint

    @property
    def default_no_input_hint(self):
        if self._page and self._page._experiment:
            hints = self._page._experiment.settings.hints
            name = type(self).__name__
            no_input_name = ("no_input%s" % name).lower()
            if no_input_name in hints:
                return hints[no_input_name]

        self.log.error(f"Can't access default no input hint for element {self}")
        return f"Can't access default no input hint for element {type(self).__name__}"

    @property
    def data(self):
        return {self.name: self._input}

    @property
    def encrypted_data(self):
        enrcypted_dict = {}
        for k, v in self.data.items():
            try:
                enrcypted_dict[k] = self.experiment.encrypt(v)
            except TypeError:
                if isinstance(v, list):
                    v = [self.experiment.encrypt(entry) for entry in v]
                enrcypted_dict[k] = v

        return enrcypted_dict

    def set_data(self, d):
        if self.enabled:
            self._input = d.get(self.name, "")

    @property
    def codebook_data_flat(self):
        data = {}
        data["name"] = self.name
        data["tree"] = self.tree.replace("rootSection_", "")
        data["identifier"] = self.identifier
        data["page_title"] = self.page.title
        data["element_type"] = type(self).__name__
        data["force_input"] = self._force_input
        data["default"] = self.default
        data["description"] = self.description
        data["duplicate_identifier"] = False
        data["unlinked"] = True if isinstance(self.page, page.UnlinkedDataPage) else False
        return data

    @property
    def codebook_data(self):
        return {self.identifier: self.codebook_data_flat}
    
    @property
    def js_code(self):
        return self._showif_js


class TextEntryElement(InputElement, WebElementInterface):
    """Provides a text entry field.

    Args:
        instruction: Instruction to be displayed with the field. Can
            contain GitHub flavored Markdown and html.
        no_input_corrective_hint: Hint to be displayed if force_input 
            set to True and no user input registered. Defaults to the
            experiment-wide value specified in config.conf.
        instruction_width: Horizontal width of instructions. 
            **Deprecated** for responsive design (v1.5+). Use 
            `instruction_col_width` instead, when using the responsive 
            design.
        instruction_height: Minimum vertical size of instruction label.
        prefix: Prefix for the input field.
        suffix: Suffix for the input field.
        placeholder: Placeholder text, displayed inside the input field.
        default: Default value.
        position: Horizontal position of the full element on the 
                page. Values can be 'left', 'center' (default), 'end',
                or any valid value for the justify-content flexbox
                utility (see https://getbootstrap.com/docs/4.0/utilities/flex/#justify-content).
        alignment: Alignment of instruction text. Values can
            be 'left' (default), 'center', 'right', and 'justify'.
        force_input: If `True`, users can only progress to the next page
            if they enter data into this field. **Note** that this works
            only in HeadOpenSections and SegmentedSections, not in plain
            Sections.
        description: An additional description of the element. This will
            show up in the additional alfred-generated codebook. It has
            no effect on the display of the experiment.
        debug_value: A value that will be inserted for the element 
            automatically, when the experiment is started in debug mode.
        debug_string: A deprecated version of debug_value. Please use
            debug_value.
    """

    def __init__(
        self,
        instruction="",
        no_input_corrective_hint: str = None,
        instruction_width: int = None,
        instruction_height: int = None,
        prefix: str = None,
        suffix: str = None,
        placeholder: str = "",
        instruction_col_width: int = 12,
        input_col_width: int = None,
        position: str = "center",
        **kwargs,
    ):
        """Constructor method."""
        super(TextEntryElement, self).__init__(
            no_input_corrective_hint=no_input_corrective_hint, **kwargs
        )

        self._instruction_width = instruction_width
        self._instruction_height = instruction_height
        self._instruction = cmarkgfm.github_flavored_markdown_to_html(instruction)
        self._prefix = prefix
        self._suffix = suffix
        self._placeholder = placeholder

        self._instruction_col_width = instruction_col_width
        if input_col_width:
            self._input_col_width = input_col_width
        else:
            self._input_col_width = 12 - self._instruction_col_width

        self.position = position
        self._responsive_template = jinja_env.get_template("TextEntryElement.html")

        self._template = Template(
            """
        <div class="text-entry-element"><table class="{{ alignment }}" style="font-size: {{ fontsize }}pt";>
        <tr><td valign="bottom"><table class="{{ alignment }}"><tr><td style="padding-right: 5px;{% if width %}width:{{width}}px;{% endif %}{% if height %}width:{{height}}px;{% endif %}">{{ instruction }}</td>
        <td valign="bottom">
        {% if prefix or suffix %}
            <div class="{% if prefix %}input-prepend {% endif %}{% if suffix %}input-append {% endif %}" style="margin-bottom: 0px;">
        {% endif %}
        {% if prefix %}
            <span class="add-on">{{prefix}}</span>
        {% endif %}
        <input class="text-input" type="text" style="font-size: {{ fontsize }}pt; margin-bottom: 0px;" name="{{ name }}" value="{{ input }}" {% if disabled %}disabled="disabled"{% endif %} />
        {% if suffix %}
            <span class="add-on">{{suffix}}</span>
        {% endif %}
        {% if prefix or suffix %}
            </div>
        {% endif %}

        </td></tr></table></td></tr>
        {% if corrective_hint %}
            <tr><td><table class="corrective-hint containerpagination-right"><tr><td style="font-size: {{fontsize}}pt;">{{ corrective_hint }}</td></tr></table></td></tr>
        {% endif %}
        </table></div>

        """
        )

    @property
    def responsive_widget(self):

        d = {}
        d["id"] = self.name
        d["hide"] = "hide" if self._showif_js != [] else ""
        d["element_width"] = self.element_width
        d["responsive"] = self.experiment.config.getboolean("layout", "responsive")
        if self._input:  # using input here to cover default and debug_value simultaneously
            d["default"] = self._input
        d["instruction_width"] = self._instruction_col_width
        d["instruction_height"] = self._instruction_height
        d["input_width"] = self._input_col_width
        if self.corrective_hints:
            d["corrective_hint"] = self.corrective_hints[0]

        d["placeholder"] = self._placeholder
        d["instruction"] = self._instruction
        d["align"] = f"text-{self._alignment}"
        d["position"] = self.position
        d["prefix"] = self._prefix
        d["suffix"] = self._suffix

        return self._responsive_template.render(d)

    @property
    def web_widget(self):

        d = {}
        d["alignment"] = alignment_converter(self._alignment, "container")
        d["fontsize"] = fontsize_converter(self._font_size)
        d["width"] = self._instruction_width
        d["height"] = self._instruction_height
        d["instruction"] = self._instruction
        d["name"] = self.name
        d["input"] = self._input
        d["disabled"] = not self.enabled
        d["prefix"] = self._prefix
        d["suffix"] = self._suffix
        if self.corrective_hints:
            d["corrective_hint"] = self.corrective_hints[0]
        return self._template.render(d)

    @property
    def can_display_corrective_hints_in_line(self):
        return True

    def validate_data(self):
        super(TextEntryElement, self).validate_data()

        if self._force_input and self._should_be_shown and self._input == "":
            return False

        return True

    def set_data(self, d):
        """
        .. todo:: No data can be set when using qt interface (compare web interface functionality). Is this a problem?
        .. update (20.02.2019) removed qt depencies
        """
        if self.enabled:
            super(TextEntryElement, self).set_data(d)

    @property
    def codebook_data_flat(self):
        data = super().codebook_data_flat
        data["instruction"] = self._instruction
        data["prefix"] = self._prefix
        data["suffix"] = self._suffix
        data["placeholder"] = self._placeholder

        return data


class TextAreaElement(TextEntryElement):
    def __init__(
        self,
        instruction="",
        x_size=300,
        y_size=150,
        no_input_corrective_hint=None,
        instruction_width=None,
        instruction_height=None,
        **kwargs,
    ):
        """
        **TextAreaElement** returns a multiline text edit with an instruction on top.

        :param str name: Name of TextAreaElement and stored input variable.
        :param str instruction: Instruction to be displayed above multiline edit field (can contain html commands).
        :param int instruction_width: Minimum horizontal size of instruction label (can be used for layouting purposes).
        :param int instruction_height: Minimum vertical size of instruction label (can be used for layouting purposes).
        :param int x_size: Horizontal size for visible text edit field in pixels.
        :param int y_size: Vertical size for visible text edit field in pixels.
        :param str alignment: Alignment of TextAreaElement in widget container ('left' as standard, 'center', 'right').
        :param str/int font: Fontsize used in TextAreaElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as standard or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        """
        super(TextAreaElement, self).__init__(
            instruction,
            no_input_corrective_hint=no_input_corrective_hint,
            instruction_width=instruction_width,
            instruction_height=instruction_height,
            **kwargs,
        )

        self._x_size = x_size
        self._y_size = y_size

    @property
    def web_widget(self):

        widget = '<div class="text-area-element"><table class="%s" style="font-size: %spt;">' % (
            alignment_converter(self._alignment, "container"),
            fontsize_converter(self._font_size),
        )

        widget = (
            widget
            + '<tr><td class="itempagination-left" style="padding-bottom: 10px;">%s</td></tr>'
            % (self._instruction)
        )

        widget = (
            widget
            + '<tr><td class="%s"><textarea class="text-input pagination-left" style="font-size: %spt; height: %spx; width: %spx;" name="%s" %s>%s</textarea></td></tr>'
            % (
                alignment_converter(self._alignment),
                fontsize_converter(self._font_size),
                self._y_size,
                self._x_size,
                self.name,
                "" if self.enabled else ' disabled="disabled"',
                self._input,
            )
        )

        if self.corrective_hints:
            widget = (
                widget
                + '<tr><td class="corrective-hint %s" style="font-size: %spt;">%s</td></tr>'
                % (
                    alignment_converter(self._alignment, "both"),
                    fontsize_converter(self._font_size) - 1,
                    self.corrective_hints[0],
                )
            )

        widget = widget + "</table></div>"

        return widget

    @property
    def css_code(self):
        return [(99, ".TextareaElement { resize: none; }")]

    def set_data(self, d):
        if self.enabled:
            super(TextAreaElement, self).set_data(d)


class RegEntryElement(TextEntryElement):
    def __init__(
        self,
        instruction="",
        reg_ex=".*",
        no_input_corrective_hint=None,
        match_hint=None,
        instruction_width=None,
        instruction_height=None,
        **kwargs,
    ):
        """
        **RegEntryElement*** displays a line edit, which only accepts Patterns that mach a predefined regular expression. Instruction is shown
        on the left side of the line edit field.

        :param str name: Name of TextAreaElement and stored input variable.
        :param str instruction: Instruction to be displayed above multiline edit field (can contain html commands).
        :param str reg_ex: Regular expression to match with user input.
        :param str alignment: Alignment of TextAreaElement in widget container ('left' as standard, 'center', 'right').
        :param str/int font: Fontsize used in TextAreaElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as standard or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        """

        super(RegEntryElement, self).__init__(
            instruction,
            no_input_corrective_hint=no_input_corrective_hint,
            instruction_width=instruction_width,
            instruction_height=instruction_height,
            **kwargs,
        )

        self._reg_ex = reg_ex
        self._match_hint = match_hint

    def validate_data(self):
        super(RegEntryElement, self).validate_data()

        if not self._should_be_shown:
            return True

        if not self._force_input and self._input == "":
            return True

        if re.match(r"^%s$" % self._reg_ex, str(self._input)):
            return True

        return False

    @property
    def match_hint(self):
        if self._match_hint is not None:
            return self._match_hint
        if (
            self._page
            and self._page._experiment
            and "corrective_regentry" in self._page._experiment.settings.hints
        ):
            return self._page._experiment.settings.hints["corrective_regentry"]

        msg = f"Can't access match_hint for  {type(self).__name__}"
        self.log.error(msg)
        return msg

    @property
    def corrective_hints(self):
        if not self.show_corrective_hints:
            return []
        elif re.match(r"^%s$" % self._reg_ex, self._input):
            return []
        elif self._input == "" and not self._force_input:
            return []
        elif self._input == "" and self._force_input:
            return [self.no_input_hint]
        else:
            return [self.match_hint]

    @property
    def codebook_data_flat(self):
        data = super().codebook_data_flat
        data["reg_ex_pattern"] = self._reg_ex
        return data


class NumberEntryElement(RegEntryElement):
    def __init__(
        self,
        instruction="",
        decimals=0,
        min=None,
        max=None,
        no_input_corrective_hint=None,
        instruction_width=None,
        instruction_height=None,
        match_hint=None,
        **kwargs,
    ):
        """
        **NumberEntryElement*** displays a line edit, which only accepts numerical input. Instruction is shown
        on the left side of the line edit field.

        :param str name: Name of NumberEntryElement and stored input variable.
        :param str instruction: Instruction to be displayed above multiline edit field (can contain html commands).
        :param int decimals: Accepted number of decimals (0 as standard).
        :param float min: Minimum accepted entry value.
        :param float max: Maximum accepted entry value.
        :param int spacing: Minimum horizontal size of instruction label (can be used for layouting purposes).
        :param str alignment: Alignment of NumberEntryElement in widget container ('left' as standard, 'center', 'right').
        :param str/int font: Fontsize used in NumberEntryElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as standard or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.

        """
        super(NumberEntryElement, self).__init__(
            instruction,
            no_input_corrective_hint=no_input_corrective_hint,
            instruction_width=instruction_width,
            instruction_height=instruction_height,
            match_hint=match_hint,
            **kwargs,
        )

        self._validator = None
        self._decimals = decimals
        self._min = min
        self._max = max

        self._template = Template(
            """
        <div class="text-entry-element"><table class="{{ alignment }}" style="font-size: {{ fontsize }}pt";>
        <tr><td valign="bottom"><table class="{{ alignment }}"><tr><td style="padding-right: 5px;{% if width %}width:{{width}}px;{% endif %}{% if height %}width:{{height}}px;{% endif %}">{{ instruction }}</td>
        <td valign="bottom">
        {% if prefix or suffix %}
            <div class="{% if prefix %}input-prepend {% endif %}{% if suffix %}input-append {% endif %}" style="margin-bottom: 0px;">
        {% endif %}
        {% if prefix %}
            <span class="add-on">{{prefix}}</span>
        {% endif %}
        <input class="text-input" type="number" style="font-size: {{ fontsize }}pt; margin-bottom: 0px;" name="{{ name }}" value="{{ input }}" {% if disabled %}disabled="disabled"{% endif %} {% if max is defined %}max={{ max }}{% endif %} {% if min is defined %}min={{ min }}{% endif %} {% if step %}step={{ step }}{% endif %} />
        {% if suffix %}
            <span class="add-on">{{suffix}}</span>
        {% endif %}
        {% if prefix or suffix %}
            </div>
        {% endif %}

        </td></tr></table></td></tr>
        {% if corrective_hint %}
            <tr><td><table class="corrective-hint containerpagination-right"><tr><td style="font-size: {{fontsize}}pt;">{{ corrective_hint }}</td></tr></table></td></tr>
        {% endif %}
        </table></div>

        """
        )

    @property
    def web_widget(self):

        d = {}
        d["alignment"] = alignment_converter(self._alignment, "container")
        d["fontsize"] = fontsize_converter(self._font_size)
        d["width"] = self._instruction_width
        d["height"] = self._instruction_height
        d["instruction"] = self._instruction
        d["name"] = self.name
        d["input"] = self._input
        d["disabled"] = not self.enabled
        d["prefix"] = self._prefix
        d["suffix"] = self._suffix
        d["step"] = (
            None
            if self._decimals == 0
            else "0." + "".join("0" for i in range(1, self._decimals)) + "1"
        )
        d["min"] = self._min
        d["max"] = self._max
        if self.corrective_hints:
            d["corrective_hint"] = self.corrective_hints[0]
        return self._template.render(d)

    def validate_data(self):
        """
        """
        super(NumberEntryElement, self).validate_data()

        if not self._should_be_shown:
            return True

        if not self._force_input and self._input == "":
            return True

        try:
            f = float(self._input)
        except Exception:
            return False

        if self._min is not None:
            if not self._min <= f:
                return False

        if self._max is not None:
            if not f <= self._max:
                return False

        re_str = (
            r"^[+-]?\d+$"
            if self._decimals == 0
            else r"^[+-]?(\d*[.,]\d{1,%s}|\d+)$" % self._decimals
        )
        if re.match(re_str, str(self._input)):
            return True

        return False

    @property
    def data(self):
        if 0 < self._decimals:
            try:
                temp_input = float(self._input)
            except Exception:
                temp_input = ""
        else:
            try:
                temp_input = int(self._input)
            except Exception:
                temp_input = ""

        if self.validate_data() and temp_input != "":
            return {self.name: temp_input}
        else:
            return {self.name: ""}

    def set_data(self, d):

        if self.enabled:
            val = d.get(self.name, "")
            if not isinstance(val, str):
                val = str(val)
            val = val.replace(",", ".")
            super(NumberEntryElement, self).set_data({self.name: val})

    @property
    def match_hint(self):
        if self._match_hint is not None:
            return self._match_hint

        if (
            self._page
            and self._page._experiment
            and "corrective_numberentry" in self._page._experiment.settings.hints
        ):
            return self._page._experiment.settings.hints["corrective_numberentry"]
        self.log.error(f"Can't access match_hint for {type(self).__name__}")
        return f"Can't access match_hint for {type(self).__name__}"

    @property
    def corrective_hints(self):
        if not self.show_corrective_hints:
            return []

        elif self._input == "" and not self._force_input:
            return []

        elif self._force_input and self._input == "":
            return [self.no_input_hint]
        else:
            re_str = (
                r"^[+-]?\d+$"
                if self._decimals == 0
                else r"^[+-]?(\d*[.,]\d{1,%s}|\d+)$" % self._decimals
            )
            if (
                not re.match(re_str, str(self._input))
                or (self._min is not None and not self._min <= float(self._input))
                or (self._max is not None and not float(self._input) <= self._max)
            ):

                hint = self.match_hint

                if 0 < self._decimals:
                    hint = hint + " (Bis zu %s Nachkommastellen" % (self._decimals)
                else:
                    hint = hint + " (Keine Nachkommastellen"

                if self._min is not None and self._max is not None:
                    hint = hint + ", Min = %s, Max = %s)" % (self._min, self._max)
                elif self._min is not None:
                    hint = hint + ", Min = %s)" % self._min
                elif self._max is not None:
                    hint = hint + ", Max = %s)" % self._max
                else:
                    hint = hint + ")"
                return [hint]

            return []

    @property
    def codebook_data_flat(self):
        data = super().codebook_data_flat

        data["decimals"] = self._decimals
        data["min"] = self._min
        data["max"] = self._max

        return data


class PasswordElement(TextEntryElement):
    def __init__(
        self,
        instruction="",
        password="",
        force_input=True,
        no_input_corrective_hint=None,
        instruction_width=None,
        instruction_height=None,
        wrong_password_hint=None,
        **kwargs,
    ):
        """
        **PasswordElement*** desplays a single line text edit for entering a password (input is not visible) with an instruction text on its' left.

        :param str name: Name of PasswordElement and stored input variable.
        :param str instruction: Instruction to be displayed with line edit field (can contain html commands).
        :param str password: Password to be matched against user input.
        :param int spacing: Minimum horizontal size of instruction label (can be used for layouting purposes).
        :param str alignment: Alignment of PasswordElement in widget container ('left' as standard, 'center', 'right').
        :param str/int font: Fontsize used in PasswordElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (True as standard or False).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        :param str wrong_password_hint: Hint to be displayed if user input does not equal password.

        .. caution:: If force_input is set to false, any input will be accepted, but still validated against correct password.
        """
        super(PasswordElement, self).__init__(
            instruction,
            no_input_corrective_hint=no_input_corrective_hint,
            force_input=force_input,
            instruction_width=instruction_width,
            instruction_height=instruction_height,
            **kwargs,
        )

        self._password = password
        self.wrong_password_hint_user = wrong_password_hint

    @property
    def web_widget(self):

        widget = '<div class="text-entry-element"><table class="%s" style="font-size: %spt;">' % (
            alignment_converter(self._alignment, "container"),
            fontsize_converter(self._font_size),
        )

        widget = widget + '<tr><td valign="bottom"><table class="%s"><tr><td %s>%s</td>' % (
            alignment_converter(self._alignment, "container"),
            'style="width: %spx;"' % self._instruction_width
            if self._instruction_width is not None
            else "",
            self._instruction,
        )

        widget = (
            widget
            + '<td valign="bottom"><input class="text-input" type="password" style="font-size: %spt; margin-bottom: 0px; margin-left: 5px;" name="%s" value="%s" %s /></td></tr></table></td></tr>'
            % (
                fontsize_converter(self._font_size),
                self.name,
                self._input,
                "" if self.enabled else 'disabled="disabled"',
            )
        )

        if self.corrective_hints:
            widget = (
                widget
                + '<tr><td><table class="corrective-hint containerpagination-right"><tr><td style="font-size: %spt;">%s</td></tr></table></td></tr>'
                % (fontsize_converter(self._font_size), self.corrective_hints[0])
            )

        widget = widget + "</table></div>"

        return widget

    def validate_data(self):
        super(PasswordElement, self).validate_data()

        if not self._force_input or not self._should_be_shown:
            return True

        return self._input == self._password

    @property
    def wrong_password_hint(self):
        if self.wrong_password_hint_user is not None:
            return self.wrong_password_hint_user
        elif (
            self._page
            and self._page._experiment
            and "corrective_password" in self._page._experiment.settings.hints
        ):
            return self._page._experiment.settings.hints["corrective_password"]
        self.log.error(f"Can't access wrong_password_hint for {type(self).__name__}")
        return f"Can't access wrong_password_hint for {type(self).__name__}"

    @property
    def corrective_hints(self):
        if not self.show_corrective_hints:
            return []
        if self._force_input and self._input == "" and self._password != "":
            return [self.no_input_hint]

        if self._password != self._input:
            return [self.wrong_password_hint]
        else:
            return []

    @property
    def data(self):
        return {}

    @property
    def codebook_data_flat(self):
        data = super().codebook_data_flat
        data["password"] = self._password
        return data


class LikertMatrix(InputElement, WebElementInterface):
    def __init__(
        self,
        instruction="",
        levels=7,
        items=4,
        top_scale_labels=None,
        bottom_scale_labels=None,
        item_labels=None,
        item_label_width=None,
        spacing=30,
        transpose=False,
        no_input_corrective_hint=None,
        table_striped=False,
        shuffle=False,
        instruction_width=None,
        instruction_height=None,
        use_short_labels=False,
        **kwargs,
    ):
        """
        **LikertMatrix** displays a matrix of multiple likert items with adjustable scale levels per item.
        Instruction is shown above element.

        :param str name: Name of LikertMatrix and stored input variable.
        :param str instruction: Instruction to be displayed above likert matrix (can contain html commands).
        :param int levels: Number of scale levels.
        :param int items: Number of items in matrix (rows or columns if transpose = True).
        :param list top_scale_labels: Labels for each scale level on top of the Matrix.
        :param list bottom_scale_labels: Labels for each scale level under the Matrix.
        :param list item_labels: Labels for each item on both sides of the scale.
        :param int spacing: Sets column width or row height (if transpose set to True) in likert matrix, can be used to ensure symmetric layout.
        :param bool transpose: If set to True matrix is layouted vertically instead of horizontally.
        :param str alignment: Alignment of LikertMatrix in widget container ('left' as standard, 'center', 'right').
        :param str/int font: Fontsize used in LikertMatrix ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as standard or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        """

        super(LikertMatrix, self).__init__(
            no_input_corrective_hint=no_input_corrective_hint, **kwargs
        )

        if spacing < 30:
            raise ValueError("Spacing must be greater or equal than 30!")

        self._instruction = instruction
        self._instruction_width = instruction_width
        self._instruction_height = instruction_height
        self._levels = levels
        self._items = items
        self._item_label_width = item_label_width
        self._spacing = spacing
        self._table_striped = table_striped
        self._transpose = transpose
        self._use_short_labels = use_short_labels

        self._default_set = False

        self._permutation = list(range(items))
        self._shuffle = shuffle
        if shuffle:
            random.shuffle(self._permutation)

        if top_scale_labels is not None and not len(top_scale_labels) == self._levels:
            raise ValueError(
                "Es mussen keine oder %s OBERE (bei Transpose LINKE) Skalenlabels ubergeben werden."
                % self._levels
            )
        self._top_scale_labels = top_scale_labels

        if bottom_scale_labels is not None and not len(bottom_scale_labels) == self._levels:
            raise ValueError(
                "Es mussen keine oder %s UNTERE (bei Transpose RECHTE) Skalenlabels ubergeben werden."
                % self._levels
            )
        self._bottom_scale_labels = bottom_scale_labels

        if item_labels is not None and not len(item_labels) == (2 * self._items):
            raise ValueError(
                "Es mussen keine oder %s Itemlabels ubergeben werden." % (2 * self._items)
            )
        self._item_labels = item_labels

        if settings.debugmode and settings.debug.default_values:
            self._input = [str(int(self._input) - 1) for i in range(self._items)]
        elif not self._input == "":
            self._input = [str(int(self._input) - 1) for i in range(self._items)]
            self._default_set = True
        else:
            self._input = ["-1" for i in range(self._items)]

    @property
    def can_display_corrective_hints_in_line(self):
        return True

    @property
    def data(self):
        lm_data = {}
        for i in range(self._items):
            label = self.name + "_item" + str(i + 1)
            if self._use_short_labels:
                short_labels = self._short_labels()
                label += "_" + short_labels[i]
            lm_data.update(
                {label: None if int(self._input[i]) + 1 == 0 else int(self._input[i]) + 1}
            )
        lm_data[self.name + "_permutation"] = [i + 1 for i in self._permutation]
        return lm_data

    def _short_labels(self):
        L = 6
        rv = []
        for i in range(self._items):
            label = self._item_labels[2 * i]
            if label != "":
                label = label.replace(".", "")
                words = label.split()
                num = int(round((old_div(L, len(words))) + 0.5))
                sl = ""
                for w in words:
                    sl = sl + w[:num]
                rv.append(sl[:L])
            else:
                rv.append("")
        return rv

    @property
    def web_widget(self):

        widget = (
            '<div class="likert-matrix"><table class="%s" style="clear: both; font-size: %spt; margin-bottom: 10px;"><tr><td %s>%s</td></tr></table>'
            % (
                alignment_converter(self._alignment, "container"),
                fontsize_converter(self._font_size),
                'style="width: %spx;"' % self._instruction_width
                if self._instruction_width is not None
                else "",
                self._instruction,
            )
        )  # Extra Table for instruction

        widget = (
            widget
            + '<table class="%s %s table" style="width: auto; clear: both; font-size: %spt; margin-bottom: 10px;">'
            % (
                alignment_converter(self._alignment, "container"),
                "table-striped" if self._table_striped else "",
                fontsize_converter(self._font_size),
            )
        )  # Beginning Table

        if not self._transpose:
            if self._top_scale_labels:
                widget = (
                    widget + "<thead><tr><th></th>"
                )  # Beginning row for top scalelabels, adding 1 column for left item_labels
                for label in self._top_scale_labels:
                    widget = (
                        widget
                        + '<th class="pagination-centered containerpagination-centered" style="text-align:center;width: %spx; vertical-align: bottom;">%s</th>'
                        % (self._spacing, label)
                    )  # Adding top Scalelabels

                widget = (
                    widget + "<th></th></tr></thead>"
                )  # adding 1 Column for right Itemlabels, ending Row for top Scalelabels

            widget = widget + "<tbody>"
            for i in self._permutation:
                widget = widget + "<tr>"  # Beginning new row for item
                if self._item_labels:
                    widget = (
                        widget
                        + '<td style="text-align:right; vertical-align: middle;">%s</td>'
                        % self._item_labels[i * 2]
                    )  # Adding left itemlabel
                else:
                    widget = widget + "<td></td>"  # Placeholder if no item_labels set

                for j in range(self._levels):  # Adding Radiobuttons for each level
                    widget = (
                        widget
                        + '<td style="text-align:center; vertical-align: middle; margin: auto auto;"><input type="radio" style="margin: 4px 4px 4px 4px;" name="%s" value="%s" %s %s /></td>'
                        % (
                            self.name + "_" + str(i),
                            j,
                            ' checked="checked"' if self._input[i] == str(j) else "",
                            "" if self.enabled else ' disabled="disabled"',
                        )
                    )

                if self._item_labels:
                    widget = (
                        widget
                        + '<td style="text-align:left;vertical-align: middle;">%s</td>'
                        % self._item_labels[(i + 1) * 2 - 1]
                    )  # Adding right itemlabel
                else:
                    widget = widget + "<td></td>"  # Placeholder if no item_labels set

                widget = widget + "</tr>"  # Closing row for item
            widget = widget + "</tbody>"

            if self._bottom_scale_labels:
                widget = (
                    widget + "<tfoot><tr><th></th>"
                )  # Beginning row for bottom scalelabels, adding 1 column for left item_labels
                for label in self._bottom_scale_labels:
                    widget = (
                        widget
                        + '<th class="pagination-centered containerpagination-centered" style="text-align:center;width: %spx; vertical-align: top;">%s</th>'
                        % (self._spacing, label)
                    )  # Adding bottom Scalelabels

                widget = (
                    widget + "<th></th></tr></tfoot>"
                )  # adding 1 Column for right Itemlabels, ending Row for bottom Scalelabels

            widget = widget + "</table>"  # Closing table for LikertMatrix

        else:  # If transposed is set to True
            if self._item_labels:
                widget = (
                    widget + "<tr><td></td>"
                )  # Beginning row for top (left without transpose) item_labels, adding 1 column for left (top without transpose) scalelabels
                for i in range(old_div(len(self._item_labels), 2)):
                    widget = (
                        widget
                        + '<td class="pagination-centered containerpagination-centered" style="text-align:center; vertical-align: bottom;">%s</td>'
                        % self._item_labels[i * 2]
                    )  # Adding top item_labels

                widget = (
                    widget + "<td></td></tr>"
                )  # adding 1 Column for right scalelabels, ending Row for top item_labels

            for i in range(self._levels):
                widget = (
                    widget + '<tr style="height: %spx;">' % self._spacing
                )  # Beginning new row for level
                if self._top_scale_labels:
                    widget = (
                        widget
                        + '<td class="pagination-right" style="vertical-align: middle;">%s</td>'
                        % self._top_scale_labels[i]
                    )  # Adding left scalelabel
                else:
                    widget = widget + "<td></td>"  # Placeholder if no scalelabels set

                for j in range(self._items):  # Adding Radiobuttons for each item
                    widget = (
                        widget
                        + '<td class="pagination-centered" style="text-align:center; vertical-align: middle; margin: auto auto;"><input type="radio" style="margin: 4px 4px 4px 4px;" name="%s" value="%s"%s%s /></td>'
                        % (
                            self.name + "_" + str(j),
                            i,
                            ' checked="checked"' if self._input[j] == str(i) else "",
                            "" if self.enabled else ' disabled="disabled"',
                        )
                    )

                if self._bottom_scale_labels:
                    widget = (
                        widget
                        + '<td class="pagination-left" style="vertical-align: middle;">%s</td>'
                        % self._bottom_scale_labels[i]
                    )  # Adding right scalelabel
                else:
                    widget = widget + "<td></td>"  # Placeholder if no scalelabels set

                widget = widget + "</tr>"  # Closing row for level

            if self._item_labels:
                widget = (
                    widget + "<tr><td></td>"
                )  # Beginning row for bottom (right without transpose) item_labels, adding 1 column for left (top without transpose) scalelabels
                for i in range(old_div(len(self._item_labels), 2)):
                    widget = (
                        widget
                        + '<td class="pagination-centered containerpagination-centered" style="text-align:center; vertical-align: top;">%s</td>'
                        % self._item_labels[(i + 1) * 2 - 1]
                    )  # Adding bottom item_labels

                widget = (
                    widget + "<td></td></tr>"
                )  # adding 1 Column for right scalelabels, ending Row for bottom item_labels

            widget = widget + "</table>"  # Closing table for LikertMatrix

        if self.corrective_hints:

            widget = (
                widget
                + '<table class="%s" style="clear: both; font-size: %spt;"><tr><td class="corrective-hint" >%s</td></tr></table>'
                % (
                    alignment_converter(self._alignment, "container"),
                    fontsize_converter(self._font_size) - 1,
                    self.corrective_hints[0],
                )
            )

        widget = widget + "</div>"

        return widget

    def validate_data(self):
        super(LikertMatrix, self).validate_data()
        try:
            if not self._force_input or not self._should_be_shown:
                return True

            ret = True
            for i in range(self._items):
                value = int(self._input[i])
                ret = ret and 0 <= value <= self._levels
            return ret
        except Exception:
            return False

    def set_data(self, d):
        if self.enabled:
            for i in range(self._items):
                self._input[i] = d.get(self.name + "_" + str(i), "-1")

    @property
    def corrective_hints(self):
        if not self.show_corrective_hints:
            return []
        if self._force_input and reduce(lambda b, val: b or val == "-1", self._input, False):
            return [self.no_input_hint]
        else:
            return super(InputElement, self).corrective_hints

    @property
    def codebook_data_flat(self):
        raise NotImplementedError("Property not implemented for LikertMatrix.")

    def _likert_name(self, item: int) -> str:
        suffix = f"_item{item}" if self.__class__.__name__ == "LikertMatrix" else ""
        return self.identifier + suffix

    @property
    def codebook_data(self):
        data = {}

        labels = []
        for i in range(len(self._item_labels)):
            if i % 2 == 0:
                labels.append(self._item_labels[i : i + 2])

        for item in range(self._items):
            element = super().codebook_data_flat
            label_left, label_right = labels[item]
            element["identifier"] = self._likert_name(item + 1)
            element["item"] = item + 1
            element["instruction"] = self._instruction
            element["n_levels"] = self._levels
            element["top_labels"] = (
                ", ".join(self._top_scale_labels) if self._top_scale_labels else None
            )
            element["bottom_labels"] = (
                ", ".join(self._bottom_scale_labels) if self._bottom_scale_labels else None
            )
            element["item_label_left"] = label_left
            element["item_label_right"] = label_right
            element["transposed"] = self._transpose
            element["shuffle"] = self._shuffle
            element["duplicate_identifier"] = False
            data[element["identifier"]] = element

        return data


class LikertElement(LikertMatrix):
    def __init__(
        self,
        instruction="",
        levels=7,
        top_scale_labels=None,
        bottom_scale_labels=None,
        item_labels=None,
        item_label_width=None,
        spacing=30,
        no_input_corrective_hint=None,
        instruction_width=None,
        instruction_height=None,
        transpose=False,
        **kwargs,
    ):
        """
        **LikertElement** returns a single likert item with n scale levels and an instruction shown above the element.

        :param str name: Name of LikertElement and stored input variable.
        :param str instruction: Instruction to be displayed above likert matrix (can contain html commands).
        :param int levels: Number of scale levels.
        :param list topscalelabels: Labels for each scale level on top of the Item.
        :param list bottomscalelabels: Labels for each scale level under the Item.
        :param list itemlabels: Labels on both sides of the scale.
        :param int spacing: Sets column width or row height (if transpose set to True) in LikertElement, can be used to ensure symmetric layout.
        :param bool transpose: If True item is layouted vertically instead of horizontally.
        :param str alignment: Alignment of LikertElement in widget container ('left' as standard, 'center', 'right').
        :param str/int font: Fontsize used in LikertElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as standard or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        """
        super(LikertElement, self).__init__(
            instruction=instruction,
            items=1,
            levels=levels,
            top_scale_labels=top_scale_labels,
            bottom_scale_labels=bottom_scale_labels,
            item_labels=item_labels,
            item_label_width=item_label_width,
            spacing=spacing,
            no_input_corrective_hint=no_input_corrective_hint,
            table_striped=False,
            transpose=transpose,
            shuffle=False,
            instruction_width=instruction_width,
            instruction_height=instruction_height,
            **kwargs,
        )

    @property
    def data(self):
        lm_data = {}
        lm_data.update(
            {self.name: None if int(self._input[0]) + 1 == 0 else int(self._input[0]) + 1}
        )
        return lm_data


class SingleChoiceElement(LikertElement):
    def __init__(
        self,
        instruction="",
        item_labels=None,
        item_label_width=None,
        item_label_height=None,
        no_input_corrective_hint=None,
        instruction_width=None,
        instruction_height=None,
        shuffle=False,
        table_striped=False,
        **kwargs,
    ):
        """
        **SingleChoiceElement** returns a vertically layouted item with adjustable choice alternatives (comparable to levels of likert scale),
        from which only one can be selected.

        :param str name: Name of SingleChoiceElement and stored input variable.
        :param str instruction: Instruction to be displayed above SingleChoiceElement (can contain html commands).
        :param int levels: Number of choice alternatives.
        :param list labels: Labels for each choice alternative on the right side of the scale.
        :param int spacing: Sets row height in SingleChoiceElement, can be used to ensure symmetric layout.
        :param str alignment: Alignment of SingleChoiceElement in widget container ('left' as standard, 'center', 'right').
        :param str/int font: Fontsize used in SingleChoiceElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as standard or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        """

        kwargs.pop(
            "transpose", None
        )  # Stellt sicher, dass keine ungültigen Argumente verwendet werden
        kwargs.pop(
            "items", None
        )  # Stellt sicher, dass keine ungültigen Argumente verwendet werden

        if len(item_labels) == 0:
            raise ValueError("Es müssen Itemlabels übergeben werden.")
        super(SingleChoiceElement, self).__init__(
            instruction=instruction,
            no_input_corrective_hint=no_input_corrective_hint,
            instruction_width=instruction_width,
            instruction_height=instruction_height,
            **kwargs,
        )

        self._permutation = list(range(len(item_labels)))
        if shuffle:
            random.shuffle(self._permutation)

        self._item_label_width = item_label_width
        self._item_label_height = item_label_height
        self._table_striped = table_striped
        self._items = 1
        self._levels = len(item_labels)
        self._item_labels = item_labels
        self._suffle = shuffle

        if settings.debugmode and settings.debug.default_values:
            self._input = str(int(self._input[0]))
        elif not self._input == "":
            self._input = str(int(self._input[0]))
            self._default_set = True
        else:
            self._input = "-1"

    @property
    def web_widget(self):

        widget = (
            '<div class="single-choice-element"><table class="%s" style="clear: both; font-size: %spt; margin-bottom: 10px;"><tr><td %s>%s</td></tr></table>'
            % (
                alignment_converter(self._alignment, "container"),
                fontsize_converter(self._font_size),
                'style="width: %spx;"' % self._instruction_width
                if self._instruction_width is not None
                else "",
                self._instruction,
            )
        )  # Extra Table for instruction

        widget = (
            widget
            + '<table class="%s %s table" style="width: auto; clear: both; font-size: %spt; margin-bottom: 10px;">'
            % (
                alignment_converter(self._alignment, "container"),
                "table-striped" if self._table_striped else "",
                fontsize_converter(self._font_size),
            )
        )  # Beginning Table

        for i in range(
            self._levels
        ):  # Adding Radiobuttons for each sclae level in each likert item

            widget = (
                widget
                + '<tr><td class="pagination-centered" style="vertical-align: middle; margin: auto auto;"><input type="radio" style="margin: 4px 4px 4px 4px;" name="%s" value="%s"%s%s /></td>'
                % (
                    self.name,
                    self._permutation[i],
                    ' checked="checked"' if self._input == str(self._permutation[i]) else "",
                    "" if self.enabled else ' disabled="disabled"',
                )
            )

            widget = (
                widget
                + '<td class="pagination-left" style="vertical-align: middle;" %s>%s</td></tr>'
                % (
                    "width: " + str(self._item_label_width) + "px;"
                    if self._item_label_width
                    else "",
                    self._item_labels[self._permutation[i]],
                )
            )  # Adding item label

        widget = widget + "</table>"  # Closing table for SingleChoiceElement

        if self.corrective_hints:
            widget = (
                widget
                + '<table class="%s" style="clear: both; font-size: %spt;"><tr><td class="corrective-hint" >%s</td></tr></table>'
                % (
                    alignment_converter(self._alignment, "container"),
                    fontsize_converter(self._font_size),
                    self.corrective_hints[0],
                )
            )

        widget = widget + "</div>"

        return widget

    def set_data(self, d):
        if self.enabled:
            self._input = d.get(self.name, "-1")

    @property
    def data(self):
        d = {self.name: None if int(self._input) + 1 == 0 else int(self._input) + 1}
        if self._suffle:
            d[self.name + "_permutation"] = [i + 1 for i in self._permutation]
        return d

    def validate_data(self):
        super(SingleChoiceElement, self).validate_data()
        try:
            if not self._force_input or not self._should_be_shown:
                return True

            ret = True
            value = int(self._input)
            ret = ret and 0 <= value <= self._levels
            return ret
        except Exception:
            return False

    @property
    def corrective_hints(self):
        if not self.show_corrective_hints:
            return []
        if self._force_input and self._input == "-1":
            return [self.no_input_hint]
        else:
            return super(InputElement, self).corrective_hints


class MultipleChoiceElement(LikertElement):
    def __init__(
        self,
        instruction="",
        item_labels=[],
        min_select=None,
        max_select=None,
        select_hint=None,
        item_label_width=None,
        item_label_height=None,
        no_input_corrective_hint=None,
        instruction_width=None,
        instruction_height=None,
        shuffle=False,
        table_striped=False,
        **kwargs,
    ):
        """
        **SingleChoiceElement** returns a vertically layouted item with adjustable choice alternatives (comparable to levels of likert scale)
        as checkboxes, from which one or more can be selected.

        :param str name: Name of MultipleChoiceElement and stored input variable.
        :param str instruction: Instruction to be displayed above MultipleChoiceElement (can contain html commands).
        :param int levels: Number of choice alternatives.
        :param list labels: Labels for each choice alternative on the right side of the scale.
        :param int spacing: Sets row height in MultipleChoiceElement, can be used to ensure symmetric layout.
        :param str alignment: Alignment of MultipleChoiceElement in widget container ('left' as standard, 'center', 'right').
        :param str/int font: Fontsize used in MultipleChoiceElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as standard or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        """

        kwargs.pop(
            "transpose", None
        )  # Stellt sicher, dass keine ungültigen Argumente verwendet werden
        kwargs.pop(
            "items", None
        )  # Stellt sicher, dass keine ungültigen Argumente verwendet werden

        default = kwargs.pop("default", None)
        debug_string = kwargs.pop("debug_string", None)

        if len(item_labels) == 0:
            raise ValueError("Es müssen Itemlabels übergeben werden.")

        super(MultipleChoiceElement, self).__init__(
            instruction=instruction,
            no_input_corrective_hint=no_input_corrective_hint,
            instruction_width=instruction_width,
            instruction_height=instruction_height,
            **kwargs,
        )

        self._permutation = list(range(len(item_labels)))
        if shuffle:
            random.shuffle(self._permutation)

        self._item_label_width = item_label_width
        self._item_label_height = item_label_height
        self._table_striped = table_striped
        self._levels = len(item_labels)
        self._items = 1

        if min_select and min_select > self._levels:
            raise ValueError("min_select must be smaller than number of items")

        if max_select and max_select < 2:
            raise ValueError("max_select must be set to 2 or higher")

        self._min_select = min_select
        self._max_select = max_select

        if select_hint:
            self._select_hint = select_hint
        else:
            if min_select and not max_select:
                self._select_hint = (
                    "Bitte wählen Sie mindestens %i Optionen aus" % self._min_select
                )
            elif max_select and not min_select:
                self._select_hint = "Bitte wählen Sie höchstens %i Optionen aus" % self._max_select
            elif max_select and min_select:
                self._select_hint = (
                    "Bitte wählen Sie mindestens %i und höchstens %i Optionen aus"
                    % (self._min_select, self._max_select)
                )

        if self._min_select:
            self._no_input_corrective_hint = self._select_hint

        self._item_labels = item_labels
        self._suffle = shuffle

        # default values and debug values have to be implemented with the following workaround resulting from deducing LikertItem

        self._input = ["0" for i in range(len(self._item_labels))]

        if settings.debugmode and settings.debug.default_values:
            if not debug_string:
                self._input = settings.debug.get(
                    self.__class__.__name__
                )  # getting default value (True or False)
            else:
                self._input = settings._config_parser.get("debug", debug_string)

            if self._input is True:
                self._input = ["1" for i in range(len(self._item_labels))]
            else:
                self._input = ["0" for i in range(len(self._item_labels))]

        if default is not None:
            self._input = default

            if not len(self._input) == len(self._item_labels):
                raise ValueError(
                    'Wrong default data! Default value must be set to a list of %s values containing either "0" or "1"!'
                    % (len(self._item_labels))
                )

    @property
    def web_widget(self):

        widget = (
            '<div class="multiple-choice-element"><table class="%s" style="clear: both; font-size: %spt; margin-bottom: 10px;"><tr><td %s>%s</td></tr></table>'
            % (
                alignment_converter(self._alignment, "container"),
                fontsize_converter(self._font_size),
                'style="width: %spx;"' % self._instruction_width
                if self._instruction_width is not None
                else "",
                self._instruction,
            )
        )  # Extra Table for instruction

        widget = (
            widget
            + '<table class="%s %s" style="clear: both; font-size: %spt; line-height: normal; margin-bottom: 10px;">'
            % (
                alignment_converter(self._alignment, "container"),
                "table-striped" if self._table_striped else "",
                fontsize_converter(self._font_size),
            )
        )  # Beginning Table

        for i in range(self._levels):
            widget = (
                widget
                + '<tr style="height: %spx;"><td class="pagination-centered" style="vertical-align: middle; margin: auto auto;"><input type="checkbox" style="vertical-align: middle; margin: 4px 4px 4px 4px;" name="%s" value="%s" %s %s /></td>'
                % (
                    self._spacing,
                    self.name + "_" + str(self._permutation[i]),
                    1,
                    ' checked="checked"' if self._input[self._permutation[i]] == "1" else "",
                    "" if self.enabled else ' disabled="disabled"',
                )
            )
            widget = (
                widget
                + '<td class="pagination-left" style="vertical-align: middle;">%s</td></tr>'
                % self._item_labels[self._permutation[i]]
            )

        widget = widget + "</table>"

        if self.corrective_hints:
            widget = (
                widget
                + '<table class="%s" style="clear: both; font-size: %spt;"><tr><td class="corrective-hint" >%s</td></tr></table>'
                % (
                    alignment_converter(self._alignment, "container"),
                    fontsize_converter(self._font_size),
                    self.corrective_hints[0],
                )
            )

        widget = widget + "</div>"

        return widget

    @property
    def data(self):
        mc_data = {}
        for i in range(self._levels):
            mc_data.update({self.name + "_" + str(i + 1): int(self._input[i])})
        if self._suffle:
            mc_data[self.name + "_permutation"] = [i + 1 for i in self._permutation]
        return mc_data

    def set_data(self, d):
        if self.enabled:
            for i in range(self._levels):
                self._input[i] = d.get(self.name + "_" + str(i), "0")

    def validate_data(self):
        if not self._force_input or not self._should_be_shown:
            return True

        if not self._min_select and not self._max_select:
            for item in self._input:
                if item == "1":
                    return True
        else:
            count = 0
            for item in self._input:
                if item == "1":
                    count += 1

            if self._min_select and count < self._min_select:
                return False
            if self._max_select and count > self._max_select:
                return False

            return True

    @property
    def corrective_hints(self):
        if not self.show_corrective_hints:
            return []
        if self._force_input and not reduce(lambda b, val: b or val == "1", self._input, False):
            return [self.no_input_hint]

        if self._min_select or self._max_select:
            hints = []
            count = 0
            for item in self._input:
                if item == "1":
                    count += 1

            if self._min_select and count < self._min_select:
                hints.append(self._select_hint)
            elif self._max_select and count > self._max_select:
                hints.append(self._select_hint)

            return hints

        return super(InputElement, self).corrective_hints

    @property
    def codebook_data_flat(self):
        data = super().codebook_data_flat
        data["min_select"] = self._min_select
        data["max_select"] = self._max_select
        data["top_labels"] = ", ".join(self._top_scale_labels) if self._top_scale_labels else None
        data["bottom_labels"] = (
            ", ".join(self._bottom_scale_labels) if self._bottom_scale_labels else None
        )
        return data


class LikertListElement(InputElement, WebElementInterface):
    def __init__(
        self,
        instruction="",
        levels=7,
        top_scale_labels=None,
        bottom_scale_labels=None,
        item_labels=[],
        item_label_height=None,
        item_label_width=None,
        item_label_alignment="left",
        table_striped=False,
        spacing=30,
        shuffle=False,
        instruction_width=None,
        instruction_height=None,
        use_short_labels=False,
        **kwargs,
    ):
        """
        **LikertListElement** displays a likert item with images as labels.
        Instruction is shown above element.

        :param str name: Name of WebLikertImageElement and stored input variable.
        :param str instruction: Instruction to be displayed above likert matrix (can contain html commands).
        :param int levels: Number of scale levels..
        :param int spacing: Sets column width between radio buttons.
        :param str alignment: Alignment of WebLikertImageElement in widget container ('left' as default, 'center', 'right').
        :param str/int font: Fontsize used in WebLikertImageElement ('normal' as default, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as default or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        """

        super(LikertListElement, self).__init__(**kwargs)

        self._instruction = instruction
        self._instruction_width = instruction_width
        self._instruction_height = instruction_height
        self._levels = levels
        self._top_scale_labels = top_scale_labels
        self._bottom_scale_labels = bottom_scale_labels
        self._item_labels = item_labels
        self._item_label_height = item_label_height
        self._item_label_width = item_label_width
        self._item_label_align = item_label_alignment
        self._table_striped = table_striped
        self._spacing = spacing
        self._default_set = False
        self._use_short_labels = use_short_labels

        if spacing < 30:
            raise ValueError("Spacing must be greater or equal than 30!")

        if top_scale_labels is not None and not len(top_scale_labels) == self._levels:
            raise ValueError(
                "Es müssen keine oder %s OBERE Skalenlabels übergeben werden." % self._levels
            )

        if bottom_scale_labels is not None and not len(bottom_scale_labels) == self._levels:
            raise ValueError(
                "Es müssen keine oder %s UNTERE Skalenlabels übergeben werden." % self._levels
            )

        self._permutation = list(range(len(item_labels)))
        if shuffle:
            random.shuffle(self._permutation)

        if settings.debugmode and settings.debug.default_values:
            self._input = [str(int(self._input) - 1) for i in item_labels]
        elif not self._input == "":
            self._input = [str(int(self._input) - 1) for i in item_labels]
            self._default_set = True
        else:
            self._input = ["-1" for i in item_labels]

        self._template = Template(
            """
            <div class="" style="font-size: {{fontsize}}pt; text-align: {{alignment}}">
                {% if instruction %}<p>{{instruction}}</p>{% endif %}
                <table class="{{contalignment}} table {{striped}}" style="width: auto;">
                    {% if topscalelabels %}
                    <thead>
                    <tr>
                        <th></th>
                        {% for topscalelabel in topscalelabels %}
                            <th style="text-align:center;">{{topscalelabel}}</th>
                        {% endfor %}
                    </tr>
                    </thead>
                    {% endif %}
                    {% if bottomscalelabels %}
                    <tfoot>
                    <tr>
                        <th></th>
                        {% for bottomscalelabel in bottomscalelabels %}
                            <th style="text-align:center;">{{bottomscalelabel}}</th>
                        {% endfor %}
                    </tr>
                    </tfoot>
                    {% endif %}
                    <tbody>
                    {% for i in permutation %}
                        <tr>
                        <td style="text-align: {{itemlabel_align}};{% if itemlabel_width%}width: {{itemlabel_width}}px;{% endif %}">{{itemlabels[i]}}</td>
                        {% for j in range(levels) %}
                            <td style="width:{{spacing}}pt;vertical-align: middle; text-align:center;"><input type="radio" style="margin: 4px 4px 4px 4px;" name={{name}}_{{i}} value="{{j}}"{% if j == values[i] %} checked="checked"{% endif %}{% if not enabled %} disabled="disabled"{% endif %} /></td>
                        {% endfor %}
                        </tr>
                    {% endfor %}
                    </tbody>
                </table>
                {% for hint in hints%}
                    <p style="color: red;">{{hint}}</p>
                {% endfor %}

            </div>
            """
        )

    @property
    def can_display_corrective_hints_in_line(self):
        return True

    def _short_labels(self):
        L = 6
        rv = []
        for label in self._item_labels:
            if label != "":
                label = label.replace(".", "")
                words = label.split()
                num = int(round((old_div(L, len(words))) + 0.5))
                sl = ""
                for w in words:
                    sl = sl + w[:num]
                rv.append(sl[:L])
            else:
                rv.append("")
        return rv

    @property
    def data(self):
        d = {}
        d[self._name + "_permutation"] = [i + 1 for i in self._permutation]
        short_labels = self._short_labels()
        for i in range(len(self._item_labels)):
            label = self.name + "_" + str(i + 1)
            if self._use_short_labels:
                label += "_" + short_labels[i]
            d[label] = int(self._input[i]) + 1
            if d[label] == 0:
                d[label] = None
        return d

    def set_data(self, d):
        if self._enabled:
            for i in range(len(self._item_labels)):
                self._input[i] = d.get(self.name + "_" + str(i), "-1")

    @property
    def web_widget(self):
        d = {}
        d["fontsize"] = fontsize_converter(self._font_size)
        d["contalignment"] = alignment_converter(self._alignment, "container")
        d["alignment"] = self._alignment
        d["instruction"] = self._instruction
        d["striped"] = "table-striped" if self._table_striped else ""
        d["spacing"] = self._spacing
        d["hints"] = self.corrective_hints
        d["name"] = self.name
        d["enabled"] = self.enabled
        d["levels"] = self._levels
        d["values"] = [int(v) for v in self._input]
        d["permutation"] = self._permutation
        d["topscalelabels"] = self._top_scale_labels
        d["bottomscalelabels"] = self._bottom_scale_labels
        d["itemlabels"] = self._item_labels
        d["itemlabel_width"] = self._item_label_width
        d["itemlabel_align"] = self._item_label_align

        return self._template.render(d)

    def validate_data(self):
        super(LikertListElement, self).validate_data()
        try:
            if not self._force_input or not self._should_be_shown:
                return True

            ret = True
            for v in self._input:
                ret = ret and 0 <= int(v) < self._levels
            return ret
        except Exception:
            return False

    @property
    def corrective_hints(self):
        if not self.show_corrective_hints:
            return []
        if self._force_input and reduce(lambda b, val: b or val == "-1", self._input, False):
            return [self.no_input_hint]
        else:
            return super(LikertListElement, self).corrective_hints

    @property
    def codebook_data_flat(self):
        data = super().codebook_data_flat
        data["labels"] = "(images)"
        data["n_levels"] = self._levels
        data["top_labels"] = ", ".join(self._top_scale_labels) if self._top_scale_labels else None
        data["bottom_labels"] = (
            ", ".join(self._bottom_scale_labels) if self._bottom_scale_labels else None
        )
        return data


class ImageElement(Element, WebElementInterface):
    def __init__(
        self, path=None, url=None, x_size=None, y_size=None, alt=None, maximizable=False, **kwargs
    ):
        super(ImageElement, self).__init__(**kwargs)

        if not path and not url:
            raise ValueError("path or url must be set in image element")

        self._path = path
        self._url = url

        self._x_size = x_size
        self._y_size = y_size
        self._alt = alt
        self._image_url = None
        self._maximizable = maximizable
        self._min_times = []
        self._max_times = []

    def prepare_web_widget(self):
        if self._image_url is None:
            if self._path:
                self._image_url = self._page._experiment.user_interface_controller.add_static_file(
                    self._path
                )
            elif self._url:
                self._image_url = self._url

    @property
    def web_widget(self):
        html = '<p class="%s">' % alignment_converter(self._alignment, "text")

        if self._maximizable:
            html = html + '<a href="#" id="link-%s">' % self.name

        html = html + '<img  src="%s" ' % self._image_url
        if self._alt is not None:
            html = html + 'alt="%s"' % self._alt

        html = html + 'style="'

        if self._x_size is not None:
            html = html + " width: %spx;" % self._x_size

        if self._y_size is not None:
            html = html + " height: %spx;" % self._y_size
        html = html + '" />'

        if self._maximizable:
            html = (
                html
                + '</a><input type="hidden" id="%s" name="%s" value="%s"></input><input type="hidden" id="%s" name="%s" value="%s"></input>'
                % (
                    self.name + "_max_times",
                    self.name + "_max_times",
                    self._min_times,
                    self.name + "_min_times",
                    self.name + "_min_times",
                    self._max_times,
                )
            )

        return html + "</p>"

    @property
    def css_code(self):
        return [
            (
                10,
                """
            #overlay-%s {position:absolute;left:0;top:0;min-width:100%%;min-height:100%%;z-index:1 !important;background-color:black;
        """
                % self.name,
            )
        ]

    @property
    def js_code(self):
        template = string.Template(
            """
         $$(document).ready(function(){
         var maxtimes = $$.parse_json($$('#${maxtimes}').val());
         var mintimes = $$.parse_json($$('#${mintimes}').val());
         $$('#${linkid}').click(function(){

          // Add time to max_times
          maxtimes.push(new Date().get_time()/1000);
          $$('#${maxtimes}').val(JSON.stringify(maxtimes));

          // Add overlay
          $$('<div id="${overlayid}" />')
           .hide()
           .append_to('body')
           .fade_in('fast');

          // Add image & center
          $$('<img id="${imageid}" class="pop" src="${imgurl}" style="max-width: none;">').append_to('#${overlayid}');
          var img = $$('#${imageid}');
          //img.css({'max-width': 'auto'});
          var img_top = Math.max(($$(window).height() - img.height())/2, 0);
          var img_lft = Math.max(($$(window).width() - img.width())/2, 0);
          img
           .hide()
           .css({ position: 'relative', top: img_top, left: img_lft })
           .fade_in('fast');

          // Add click functionality to hide everything
          $$('#${overlayid}').click(function(){
           // Add time to min_times
           mintimes.push(new Date().get_time()/1000);
           $$('#${mintimes}').val(JSON.stringify(mintimes));

           $$('#${overlayid},#${imageid}').fade_out('fast',function(){
             $$(this).remove();
             $$('#${overlayid}').remove();
           });
          });
          $$('#${imageid}').click(function(){
           $$('#${overlayid},#${imageid}').fade_out('fast',function(){
             $$(this).remove();
             $$('#${overlayid}').remove();
           });
          })
         });
        });
            """
        )
        return [
            (
                10,
                template.substitute(
                    linkid="link-" + self.name,
                    overlayid="overlay-" + self.name,
                    imageid="image-" + self.name,
                    imgurl=self._image_url,
                    maxtimes=self.name + "_max_times",
                    mintimes=self.name + "_min_times",
                ),
            )
        ]

    @property
    def data(self):
        if self._maximizable:
            return {
                self.name + "_max_times": self._max_times,
                self.name + "_min_times": self._min_times,
            }
        return {}

    def set_data(self, d):
        if self.enabled and self._maximizable:
            try:
                self._min_times = json.loads(d.get(self.name + "_min_times", "[]"))
                self._max_times = json.loads(d.get(self.name + "_max_times", "[]"))
            except Exception:
                self._min_times = []
                self._max_times = []


class TableElement(Element, WebElementInterface):
    def __init__(self, elements=[], **kwargs):
        super(TableElement, self).__init__(**kwargs)
        self._elements = elements

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        if not isinstance(name, str):
            raise TypeError
        self._name = name
        for row in range(len(self._elements)):
            for column in range(len(self._elements[row])):
                e = self._elements[row][column]
                if not e.name:
                    e.name = (
                        self.name
                        + "_"
                        + e.__class__.__name__
                        + "_r"
                        + str(row)
                        + "_c"
                        + str(column)
                    )

    @property
    def flat_elements(self):
        return [e for l in self._elements for e in l]

    def added_to_page(self, q):
        super(TableElement, self).added_to_page(q)
        for e in self.flat_elements:
            e.added_to_page(q)

    @property
    def data(self):
        d = {}
        for e in self.flat_elements:
            d.update(e.data)
        return d

    def set_data(self, data):
        for e in self.flat_elements:
            e.set_data(data)

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        self._enabled = enabled
        for e in self.flat_elements:
            e.enabled = enabled

    @property
    def can_display_corrective_hints_in_line(self):
        return reduce(
            lambda b, e: b and e.can_display_corrective_hints_in_line, self.flat_elements, True,
        )

    @property
    def corrective_hints(self):
        return [hint for e in self.flat_elements for hint in e.corrective_hints]

    @property
    def show_corrective_hints(self):
        return self._show_corrective_hints

    @show_corrective_hints.setter
    def show_corrective_hints(self, b):
        self._show_corrective_hints = b
        for e in self.flat_elements:
            e.show_corrective_hints = b

    def validate_data(self):
        return reduce(lambda b, e: b and e.validate_data(), self.flat_elements, True)

    @property
    def web_widget(self):
        html = '<table class="%s" style="text-align: center; font-size:%spt">' % (
            alignment_converter(self._alignment, "container"),
            fontsize_converter(self._font_size),
        )

        for l in self._elements:
            html = html + "<tr>"
            for e in l:
                html = html + "<td>" + e.web_widget if e.should_be_shown else "" + "</td>"
            html = html + "</tr>"
        html = html + "</table>"

        return html

    def prepare_web_widget(self):
        for e in self.flat_elements:
            e.prepare_web_widget()

    @property
    def css_code(self):
        return [code for e in self.flat_elements for code in e.css_code]

    @property
    def css_urls(self):
        return [url for e in self.flat_elements for url in e.css_urls]

    @property
    def js_code(self):
        return [code for e in self.flat_elements for code in e.js_code]

    @property
    def js_urls(self):
        return [url for e in self.flat_elements for url in e.js_urls]


class WebSliderElement(InputElement, WebElementInterface):
    def __init__(
        self,
        instruction="",
        slider_width=200,
        min=0,
        max=100,
        step=1,
        no_input_corrective_hint=None,
        instruction_width=None,
        instruction_height=None,
        item_labels=None,
        top_label=None,
        bottom_label=None,
        **kwargs,
    ):
        """
        **TextSliderElement*** returns a slider bar.

        :param str name: Name of TextEntryElement and stored input variable.
        :param str instruction: Instruction to be displayed with line edit field (can contain html commands).
        :param int instruction_width: Minimum horizontal size of instruction label (can be used for layouting purposes).
        :param int instruction_height: Minimum vertical size of instruction label (can be used for layouting purposes).
        :param str alignment: Alignment of TextEntryElement in widget container ('left' as standard, 'center', 'right').
        :param str/int font_size: Font size used in TextEntryElement ('normal' as standard, 'big', 'huge', or int value setting fontsize in pt).
        :param bool force_input: Sets user input to be mandatory (False as standard or True).
        :param str no_input_corrective_hint: Hint to be displayed if force_input set to True and no user input registered.
        """

        # TODO: Required image files from jquery-ui are missing! Widget will not be displayed correctly, but works nonetheless.
        super(WebSliderElement, self).__init__(
            no_input_corrective_hint=no_input_corrective_hint, **kwargs
        )

        self._instruction_width = instruction_width
        self._instruction_height = instruction_height
        self._instruction = instruction
        self._slider_width = slider_width
        self._min = min
        self._max = max
        self._step = step

        if item_labels is not None and not len(item_labels) == 2:
            raise ValueError("Es müssen keine oder 2 Itemlabels übergeben werden.")
        self._item_labels = item_labels
        self._top_label = top_label
        self._bottom_label = bottom_label

        self._template = Template(
            """
        <div class="web-slider-element">
            <table class="{{ alignment }}" style="font-size: {{ fontsize }}pt;">
            <tr><td valign="bottom">
                <table class="{{ alignment }}">
                <tr><td style="{% if width %}width:{{width}}px;{% endif %}{% if height %}width:{{height}}px;{% endif %}">{{ instruction }}</td></tr>
                <tr><table>
                    <tr><td align="center" colspan="3">{{ toplabel }}</td></tr>
                    <tr><td align="right">{{ l_label }}</td>
                    <td valign="bottom"><div style="width: {{ slider_width }}px; margin-left: 15px; margin-right: 15px; margin-top: 5px; margin-bottom: 5px;" name="{{ name }}" value="{{ input }}" {% if disabled %}disabled="disabled"{% endif %}></div></td>
                    <td align="left">{{ r_label }}</td></tr>
                    <tr><td align="center" colspan="3">{{ bottomlabel }}</td></tr>
                    </table></tr>
                </table></td></tr>

            {% if corrective_hint %}
            <tr><td><table class="corrective-hint containerpagination-right"><tr><td style="font-size: {{fontsize}}pt;">{{ corrective_hint }}</td></tr></table></td></tr>
            {% endif %}

            </table>
        </div>

        <input type="hidden" value="{{ input }}" name="{{ name }}" />

        <script>
        $('div[name={{ name }}]').slider({change: function( event, ui ) {
            $('input[name={{ name }}]').val(ui.value);
        }});

        $('div[name={{ name }}]').slider( "option", "max", {{ max }} );
        $('div[name={{ name }}]').slider( "option", "min", {{ min }} );
        $('div[name={{ name }}]').slider( "option", "step", {{ step }} );

        {% if input != "" %}
            $('div[name={{ name }}]').slider( "option", "value", {{ input }});
        {% endif %}



        </script>

        """
        )

    @property
    def web_widget(self):

        d = {}
        d["alignment"] = alignment_converter(self._alignment, "container")
        d["fontsize"] = fontsize_converter(self._font_size)
        d["width"] = self._instruction_width
        d["slider_width"] = self._slider_width
        d["height"] = self._instruction_height
        d["instruction"] = self._instruction
        d["l_label"] = self._item_labels[0] if self._item_labels else ""
        d["r_label"] = self._item_labels[1] if self._item_labels else ""
        d["toplabel"] = self._top_label if self._top_label else ""
        d["bottomlabel"] = self._bottom_label if self._bottom_label else ""
        d["name"] = self.name
        d["input"] = self._input
        d["min"] = self._min
        d["max"] = self._max
        d["step"] = self._step
        d["disabled"] = not self.enabled
        if self.corrective_hints:
            d["corrective_hint"] = self.corrective_hints[0]
        return self._template.render(d)

    @property
    def can_display_corrective_hints_in_line(self):
        return True

    def validate_data(self):
        super(WebSliderElement, self).validate_data()

        if not self._should_be_shown:
            return True

        if self._force_input and self._input == "":
            return False

        return True

    def set_data(self, d):
        if self.enabled:
            self._input = d.get(self.name, "")

        if self._input == "None":
            self._input = ""

    @property
    def codebook_data_flat(self):
        data = super().codebook_data_flat
        data["min"] = self._min
        data["max"] = self._max
        data["step"] = self._step

        if self._item_labels:
            data["item_label_1"] = self._item_labels[0]
            data["item_label_1"] = self._item_labels[1]

        data["top_labels"] = self._top_label
        data["bottom_labels"] = self._bottom_label
        return data


class WebAudioElement(Element, WebElementInterface):
    def __init__(
        self,
        wav_url=None,
        wav_path=None,
        ogg_url=None,
        ogg_path=None,
        mp3_url=None,
        mp3_path=None,
        controls=True,
        autoplay=False,
        loop=False,
        **kwargs,
    ):
        """
        TODO: Add docstring
        """
        super(WebAudioElement, self).__init__(**kwargs)
        # if wav_path is not None and not os.path.isabs(wav_path):
        #     wav_path = os.path.join(settings.general.external_files_dir, wav_path)
        # if ogg_path is not None and not os.path.isabs(ogg_path):
        #     ogg_path = os.path.join(settings.general.external_files_dir, ogg_path)
        # if mp3_path is not None and not os.path.isabs(mp3_path):
        #     mp3_path = os.path.join(settings.general.external_files_dir, mp3_path)

        self._wav_path = wav_path
        self._ogg_path = ogg_path
        self._mp3_path = mp3_path

        self._wav_audio_url = wav_url
        self._ogg_audio_url = ogg_url
        self._mp3_audio_url = mp3_url

        self._controls = controls
        self._autoplay = autoplay
        self._loop = loop

        if (
            self._wav_path is None
            and self._ogg_path is None
            and self._mp3_path is None
            and self._wav_audio_url is None
            and self._ogg_audio_url is None
            and self._mp3_audio_url is None
        ):
            raise AlfredError

    def prepare_web_widget(self):

        if self._wav_audio_url is None and self._wav_path is not None:
            self._wav_audio_url = self._page._experiment.user_interface_controller.add_static_file(
                self._wav_path
            )

        if self._ogg_audio_url is None and self._ogg_path is not None:
            self._ogg_audio_url = self._page._experiment.user_interface_controller.add_static_file(
                self._ogg_path
            )

        if self._mp3_audio_url is None and self._mp3_path is not None:
            self._mp3_audio_url = self._page._experiment.user_interface_controller.add_static_file(
                self._mp3_path
            )

    @property
    def web_widget(self):
        widget = (
            '<div class="audio-element"><p class="%s"><audio %s %s %s><source src="%s" type="audio/mp3"><source src="%s" type="audio/ogg"><source src="%s" type="audio/wav">Your browser does not support the audio element</audio></p></div>'
            % (
                alignment_converter(self._alignment, "both"),
                "controls" if self._controls else "",
                "autoplay" if self._autoplay else "",
                "loop" if self._loop else "",
                self._mp3_audio_url,
                self._ogg_audio_url,
                self._wav_audio_url,
            )
        )

        return widget


class WebVideoElement(Element, WebElementInterface):
    def __init__(
        self,
        source=None,
        sources_list=[],
        width=720,
        height=None,
        controls=True,
        autoplay=False,
        muted=False,
        loop=False,
        mp4_url=None,
        mp4_path=None,
        ogg_url=None,
        ogg_path=None,
        web_m_url=None,
        web_m_path=None,
        **kwargs,
    ):
        """
        TODO: Add docstring
        """
        super(WebVideoElement, self).__init__(**kwargs)

        self._template = None

        # if single source is given
        self._source = source

        # if source list is given
        self._sources_list = sources_list
        self._ordered_sources = []
        self._urls = []

        # attributes
        self._attributes = None
        self._width = width
        self._height = height
        self._controls = controls
        self._autoplay = autoplay
        self._muted = muted
        self._loop = loop

        # -------------------------------------------- #
        # catch deprecated parameters (21.03.2020)
        self._deprecated_parameters = [
            mp4_url,
            mp4_path,
            ogg_url,
            ogg_path,
            web_m_url,
            web_m_path,
        ]
        self._mp4_path = mp4_path
        self._ogg_path = ogg_path
        self._web_m_path = web_m_path
        self._mp4_video_url = mp4_url
        self._ogg_video_url = ogg_url
        self._web_m_video_url = web_m_url
        # -------------------------------------------- #

        if not any([self._source, self._sources_list, self._deprecated_parameters]):
            raise AlfredError

    def order_sources(self):
        # ensure that .mp4 files come first
        for source in self._sources_list:
            if source.endswith(".mp4"):
                self._ordered_sources.insert(0, source)
            else:
                self._ordered_sources.append(source)

    def prepare_url(self, source):
        if is_url(source):
            url = source
        else:
            url = self._page._experiment.user_interface_controller.add_static_file(source)
        return url

    def prepare_attributes(self):
        attr = []
        if self._width:
            attr.append('width="{}"'.format(self._width))
        if self._height:
            attr.append('height="{}"'.format(self._height))
        if self._controls:
            attr.append("controls")
        if self._autoplay:
            attr.append("autoplay")
        if self._muted:
            attr.append("muted")
        if self._loop:
            attr.append("loop")
        self._attributes = " ".join(attr)

    def prepare_web_widget(self):
        # load template
        self._template = jinja_env.get_template("WebVideoElement.html")

        # prepare attributes
        self.prepare_attributes()

        # prepare urls
        if self._source:
            self._sources_list.append(self._source)

        self.order_sources()
        for src in self._ordered_sources:
            url = self.prepare_url(src)
            self._urls.append(url)

        # -------------------------------------------- #
        # handle deprecated parameters (21.03.2020)
        for parameter in self._deprecated_parameters:
            if parameter:
                self.log.warning(
                    "The parameters mp4_url, mp4_path, ogg_url, ogg_path, web_m_url, and web_m_path in Element.WebVideoElement are deprecated. Please use source or sources_list instead."
                )

        if self._mp4_video_url is None and self._mp4_path is not None:
            self._mp4_video_url = self._page._experiment.user_interface_controller.add_static_file(
                self._mp4_path, content_type="video/mp4"
            )
            self._urls.insert(0, self._mp4_video_url)

        if self._ogg_video_url is None and self._ogg_path is not None:
            self._ogg_video_url = self._page._experiment.user_interface_controller.add_static_file(
                self._ogg_path, content_type="video/ogg"
            )
            self._urls.append(self._ogg_video_url)

        if self._web_m_video_url is None and self._web_m_path is not None:
            self._web_m_video_url = self._page._experiment.user_interface_controller.add_static_file(
                self._web_m_path, content_type="video/webm"
            )
            self._urls.append(self._web_m_video_url)
        # -------------------------------------------- #

    @property
    def web_widget(self):
        alignment = alignment_converter(self._alignment, type="div")
        widget = self._template.render(
            element_class="video-element",
            alignment=alignment,
            urls=self._urls,
            attributes=self._attributes,
        )
        return widget

    @property
    def js_code(self):
        # disables the right-click context menu
        code = (
            11,
            '$(document).ready(function() {$("video").bind("contextmenu",function(){return false;});} );',
        )
        return [code]  # Pages expect a list of the described tuples from each element


class ExperimenterMessages(TableElement):
    def prepare_web_widget(self):
        self._elements = []
        messages = self._page._experiment.experimenter_message_manager.get_messages()

        for message in messages:
            output = ""

            if not message.title == "":
                output = output + "<strong>" + message.title + "</strong> - "

            output = output + message.msg

            message.level = "" if message.level == "warning" else "alert-" + message.level

            message_element = TextElement(
                '<div class="alert '
                + message.level
                + '"><button type="button" class="close" data-dismiss="alert">&times;</button>'
                + output
                + " </div>"
            )

            message_element.added_to_page(self._page)

            self._elements.append([message_element])

        super(ExperimenterMessages, self).prepare_web_widget()


class WebExitEnabler(Element, WebElementInterface):
    @property
    def js_code(self):
        call = "$(document).ready(function(){glob_unbind_leaving();});"
        return [(10, call)]

    @property
    def web_widget(self):
        return ""


class Row(Element, WebElementInterface):
    """Allows you to arrange up to 12 elements in a row.

    The row will arrange your elements using Bootstrap 4's grid system
    and breakpoints, making the arrangement responsive. You can 
    customize the behavior of the row for five different screen sizes
    (Bootstrap 4's default break points).

    If you don't specify breakpoints manually, the columns will default
    to equal width and wrap on breakpoints automatically.

    .. info::
        In Bootstrap's grid, the horizontal space is divided into 12
        equally wide units. You can define the horizontal width of a
        column by assigning it a number of those units. A column of 
        width 12 will take up all available horizontal space, other 
        columns will be placed below such a full-width column.

        You can define the column width for each of five breakpoints
        separately. The definition will be valid for screens of the
        respective size up to the next breakpoint.

        See https://getbootstrap.com/docs/4.5/layout/grid/#grid-options 
        for detailed documentation of how Bootstrap's breakpoints work.
    
    .. info::
        If you specify fewer values than the number of columns, the 
        columns with undefined width will take up equal portions of
        the remaining horizontal space.
    
    .. info::
        If a breakpoint is not specified manually, the values from the
        next smaller breakpoint are inherited.
    
    Args:
        elements: The elements that you want to arrange in a row.
        xs: List of column widths on screens of size 'xs' or bigger 
            (<576px).
        sm: List of column widths on screens of size 'sm' or bigger
            (>=576px).
        md: List of column widths on screens of size 'md' or bigger
            (>=768px).
        lg: List of column widths on screens of size 'lg' or bigger
            (>=992px).
        xl: List of column widths on screens of size 'xl' or bigger
            (>=1200px).
        height: Custom row height (with unit, e.g. '100px').
        col_position: List of column positions. Valid values are 'auto'
            (default), 'top', 'center', and 'bottom'.
    """

    def __init__(
        self,
        *elements,
        xs: List[int] = None,
        sm: List[int] = None,
        md: List[int] = None,
        lg: List[int] = None,
        xl: List[int] = None,
        height: str = "auto",
        col_position: List[str] = None,
    ):
        """Constructor method."""
        super().__init__()
        self.elements = elements

        self.height = height
        self.col_position = self.format_col_position(col_position)

        self._breaks_xs = self.format_breaks(xs, "xs")
        self._breaks_sm = self.format_breaks(sm, "sm")
        self._breaks_md = self.format_breaks(md, "md")
        self._breaks_lg = self.format_breaks(lg, "lg")
        self._breaks_xl = self.format_breaks(xl, "xl")

    def added_to_page(self, page):
        super().added_to_page(page)

        for element in self.elements:
            if element is None:
                continue
            element.should_be_shown = False
            page += element

    def format_col_position(self, col_position: List[str]):
        try:
            if len(col_position) > len(self.elements):
                raise ValueError(
                    "Col position list must be of the same or smaller length as number of elements."
                )
        except TypeError:
            pass

        out = []
        for i, _ in enumerate(self.elements):
            try:
                n = col_position[i]
            except IndexError:
                out.append("")
                continue
            except TypeError:
                out.append("")
                continue

            if not isinstance(n, str):
                raise TypeError("Col position must be of type str.")

            if n == "auto":
                out.append("")
            elif n == "top":
                out.append("align-self-start")
            elif n == "center":
                out.append("align-self-center")
            elif n == "bottom":
                out.append("align-self-end")
            else:
                raise ValueError(
                    "Col position allowed values are 'auto', 'top', 'center', and 'bottom'."
                )

        return out

    @property
    def cols(self) -> list:
        """Returns a list of html code for all columns."""
        out = []
        for i, element in enumerate(self.elements):
            breaks = self.col_breaks(i)
            pos = self.col_position[i]
            html = element.responsive_widget if element is not None else ""
            t = Template("<div class='{{ breaks }} {{ position }} col-element'>{{ html }}</div>")
            out.append(t.render(breaks=breaks, position=pos, html=html))
        return out

    @property
    def responsive_widget(self):
        t = Template(
            "<div class='row row-element' style='height: {{ height}};'>{{ cols | safe }}</div>"
        )
        columns_html = "".join(self.cols)
        return t.render(cols=columns_html, height=self.height)

    @property
    def web_widget(self):
        return self.responsive_widget

    def col_breaks(self, i: int) -> str:
        xs = self.breaks_xs[i]
        sm = self.breaks_sm[i]
        md = self.breaks_md[i]
        lg = self.breaks_lg[i]
        xl = self.breaks_xl[i]

        if self.experiment.config.getboolean("layout", "responsive", fallback=True):
            breaks = [xs, sm, md, lg, xl]
            if breaks == ["", "", "", "", ""]:
                return "col-sm"
            else:
                return " ".join(breaks)
        else:
            out = xs if xs != "" else "col"
            return out

    @property
    def breaks_xs(self):
        return self._breaks_xs

    @breaks_xs.setter
    def breaks_xs(self, breaks: List[int]):
        self._breaks_xs = self.format_breaks(breaks, "xs")

    @property
    def breaks_sm(self):
        return self._breaks_sm

    @breaks_sm.setter
    def breaks_sm(self, breaks: List[int]):
        self._breaks_sm = self.format_breaks(breaks, "sm")

    @property
    def breaks_md(self):
        return self._breaks_md

    @breaks_md.setter
    def breaks_md(self, breaks: List[int]):
        self._breaks_md = self.format_breaks(breaks, "md")

    @property
    def breaks_lg(self):
        return self._breaks_lg

    @breaks_lg.setter
    def breaks_lg(self, breaks: List[int]):
        self._breaks_lg = self.format_breaks(breaks, "lg")

    @property
    def breaks_xl(self):
        return self._breaks_xl

    @breaks_xl.setter
    def breaks_xl(self, breaks: List[int]):
        self._breaks_xl = self.format_breaks(breaks, "xl")

    def format_breaks(self, breaks: List[int], bp: str) -> List[str]:
        """Takes a tuple of column sizes (in integers from 1 to 12) and
        returns a corresponding list of formatted Bootstrap column 
        classes.

        Args:
            breaks: List of integers, indicating the breakpoints.
            bp: Specifies the relevant bootstrap breakpoint. (xs, sm,
                md, lg, or xl).
        """
        try:
            if len(breaks) > len(self.elements):
                raise ValueError(
                    "Break list must be of the same or smaller length as number of elements."
                )
        except TypeError:
            pass

        out = []
        for i, _ in enumerate(self.elements):
            try:
                n = breaks[i]
            except IndexError:
                out.append("")
                continue
            except TypeError:
                out.append("")
                continue

            if not isinstance(n, int):
                raise TypeError("Break values must be of type integer.")
            if not n >= 1 and n <= 12:
                raise ValueError("Break values must be between 1 and 12.")

            if bp == "xs":
                out.append(f"col-{n}")
            else:
                out.append(f"col-{bp}-{n}")

        return out


class VerticalSpace(Element, WebElementInterface):
    """The easiest way to add vertical space to a page.
    
    Args:
        space: Desired space in any unit that is understood by a CSS
            margin (e.g. em, px, cm). Include the unit (e.g. '1em').
    """

    def __init__(self, space: str = "1em"):
        """Constructor method."""
        super().__init__()
        self.space = space

    @property
    def responsive_widget(self):
        return f"<div style='margin-bottom: {self.space};'></div>"

    @property
    def web_widget(self):
        return self.responsive_widget


# class Html:

#     def __init__(self, classes: list = None):
#         self.classes = classes if classes is not None else []

#     @property
#     def class_html(self):
#         return " ".join(self.classes)


# class Row(Html):

#     template = """<div class='row'>
#     {% for col in cols %}

#     </div>"""

#     def __init__(self):
#         self.cols = []

#     def row_html(self):
#         return

