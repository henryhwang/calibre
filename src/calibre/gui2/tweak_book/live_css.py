#!/usr/bin/env python
# vim:fileencoding=utf-8
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__ = 'GPL v3'
__copyright__ = '2014, Kovid Goyal <kovid at kovidgoyal.net>'

import json, math

from PyQt4.Qt import (
    QWidget, QTimer, QStackedLayout, QLabel, QScrollArea, QVBoxLayout,
    QPainter, Qt, QFontInfo, QPalette, QRect, QSize, QSizePolicy)

from calibre.constants import iswindows
from calibre.gui2.tweak_book import editors, actions, current_container, tprefs
from calibre.gui2.tweak_book.editor.themes import THEMES, default_theme, theme_color
from calibre.gui2.tweak_book.editor.text import default_font_family

class Heading(QWidget):

    def __init__(self, text, expanded=True, parent=None):
        QWidget.__init__(self, parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.setCursor(Qt.PointingHandCursor)
        self.text = text
        self.expanded = expanded
        self.hovering = False
        self.do_layout()

    def do_layout(self):
        try:
            f = self.parent().font()
        except AttributeError:
            return
        f.setBold(True)
        sz = QFontInfo(f).pointSize()
        f.setPointSize(int(math.ceil(1.2 * sz)))
        self.setFont(f)

    @property
    def rendered_text(self):
        return ('▾' if self.expanded else '▸') + '\xa0' + self.text

    def sizeHint(self):
        fm = self.fontMetrics()
        sz = fm.boundingRect(self.rendered_text).size()
        return sz

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setClipRect(ev.rect())
        bg = self.palette().color(QPalette.AlternateBase)
        if self.hovering:
            bg = bg.lighter(115)
        p.fillRect(ev.rect(), bg)
        try:
            p.drawText(ev.rect(), Qt.AlignLeft|Qt.AlignVCenter|Qt.TextSingleLine, self.rendered_text)
        finally:
            p.end()

    def enterEvent(self, ev):
        self.hovering = True
        self.update()
        return QWidget.enterEvent(self, ev)

    def leaveEvent(self, ev):
        self.hovering = False
        self.update()
        return QWidget.leaveEvent(self, ev)

class Cell(object):

    SIDE_MARGIN = 5
    FLAGS = Qt.AlignVCenter | Qt.TextSingleLine | Qt.TextIncludeTrailingSpaces

    def __init__(self, text, rect, right_align=False, color_role=QPalette.WindowText):
        self.rect, self.text = rect, text
        self.right_align = right_align
        self.color_role = color_role

    def draw(self, painter, width, palette):
        flags = self.FLAGS | (Qt.AlignRight if self.right_align else Qt.AlignLeft)
        rect = QRect(self.rect)
        if self.right_align:
            rect.setRight(width - self.SIDE_MARGIN)
        painter.setPen(palette.color(self.color_role))
        painter.drawText(rect, flags, self.text)

class Declaration(QWidget):

    def __init__(self, html_name, data, is_first=False, parent=None):
        QWidget.__init__(self, parent)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.data = data
        self.is_first = is_first
        self.html_name = html_name
        self.do_layout()

    def do_layout(self):
        fm = self.fontMetrics()
        bounding_rect = lambda text: fm.boundingRect(0, 0, 10000, 10000, Cell.FLAGS, text)
        line_spacing = 5
        side_margin = Cell.SIDE_MARGIN
        self.rows = []
        ypos = line_spacing + (1 if self.is_first else 0)
        if 'href' in self.data:
            name = self.data['href']
            if isinstance(name, list):
                name = self.html_name
            br1 = bounding_rect(name)
            sel = self.data['selector'] or ''
            if self.data['type'] == 'inline':
                sel = 'style=""'
            br2 = bounding_rect(sel)
            self.hyperlink_rect = QRect(side_margin, ypos, br1.width(), br1.height())
            self.rows.append([
                Cell(name, self.hyperlink_rect, color_role=QPalette.Link),
                Cell(sel, QRect(br1.right() + side_margin, ypos, br2.width(), br2.height()), right_align=True)
            ])
            ypos += max(br1.height(), br2.height()) + 2 * line_spacing

        for (name, value, important) in self.data['properties']:
            text = name + ':\xa0'
            br1 = bounding_rect(text)
            vtext = value + '\xa0' + ('!' if important else '') + important
            br2 = bounding_rect(vtext)
            self.rows.append([
                Cell(text, QRect(side_margin, ypos, br1.width(), br1.height()), color_role=QPalette.LinkVisited),
                Cell(vtext, QRect(br1.right() + side_margin, ypos, br2.width(), br2.height()))
            ])
            ypos += max(br1.height(), br2.height()) + line_spacing

        self.height_hint = ypos + line_spacing
        self.width_hint = max(row[-1].rect.right() + side_margin for row in self.rows) if self.rows else 0

    def sizeHint(self):
        return QSize(self.width_hint, self.height_hint)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setClipRect(ev.rect())
        palette = self.palette()
        p.setPen(palette.color(QPalette.WindowText))
        if not self.is_first:
            p.drawLine(0, 0, self.width(), 0)
        try:
            for row in self.rows:
                for cell in row:
                    p.save()
                    try:
                        cell.draw(p, self.width(), palette)
                    finally:
                        p.restore()

        finally:
            p.end()


class Box(QWidget):

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.l = l = QVBoxLayout(self)
        l.setAlignment(Qt.AlignTop)
        self.setLayout(l)
        self.widgets = []

    def show_data(self, data):
        for w in self.widgets:
            self.layout().removeWidget(w)
            w.deleteLater()
        self.widgets = []
        for node in data['nodes']:
            node_name = node['name']
            if node['is_ancestor']:
                title = _('Inherited from %s') % node_name
            else:
                title = _('Matched CSS rules for %s') % node_name
            h = Heading(title, parent=self)
            self.widgets.append(h), self.layout().addWidget(h)
            for i, declaration in enumerate(node['css']):
                d = Declaration(data['html_name'], declaration, is_first=i == 0, parent=self)
                self.widgets.append(d), self.layout().addWidget(d)

        h = Heading(_('Computed final style'), parent=self)
        self.widgets.append(h), self.layout().addWidget(h)
        keys = sorted(data['computed_css'])
        declaration = {'properties':[[k, data['computed_css'][k], ''] for k in keys]}
        d = Declaration(None, declaration, is_first=True, parent=self)
        self.widgets.append(d), self.layout().addWidget(d)

    def relayout(self):
        for w in self.widgets:
            w.do_layout()
            w.updateGeometry()

class LiveCSS(QWidget):

    def __init__(self, preview, parent=None):
        QWidget.__init__(self, parent)
        self.preview = preview
        preview.refreshed.connect(self.update_data)
        self.apply_theme()
        self.setAutoFillBackground(True)
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_data)
        self.update_timer.setSingleShot(True)

        self.stack = s = QStackedLayout(self)
        self.setLayout(s)

        self.clear_label = la = QLabel('<h3>' + _(
            'No style information found') + '</h3><p>' + _(
                'Move the cursor inside a HTML tag to see what styles'
                ' apply to that tag.'))
        la.setWordWrap(True)
        la.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        s.addWidget(la)

        self.box = box = Box(self)
        self.scroll = sc = QScrollArea(self)
        sc.setWidget(box)
        sc.setWidgetResizable(True)
        s.addWidget(sc)

    def apply_theme(self):
        f = self.font()
        f.setFamily(tprefs['editor_font_family'] or default_font_family())
        f.setPointSize(tprefs['editor_font_size'])
        self.setFont(f)
        theme = THEMES.get(tprefs['editor_theme'], None)
        if theme is None:
            theme = THEMES[default_theme()]
        pal = self.palette()
        pal.setColor(pal.Window, theme_color(theme, 'Normal', 'bg'))
        pal.setColor(pal.WindowText, theme_color(theme, 'Normal', 'fg'))
        pal.setColor(pal.AlternateBase, theme_color(theme, 'HighlightRegion', 'bg'))
        pal.setColor(pal.LinkVisited, theme_color(theme, 'Keyword', 'fg'))
        self.setPalette(pal)
        if hasattr(self, 'box'):
            self.box.relayout()
        self.update()

    def clear(self):
        self.stack.setCurrentIndex(0)

    def show_data(self, editor_name, sourceline, tags):
        if sourceline is None:
            self.clear()
        else:
            data = self.read_data(sourceline, tags)
            if data is None or len(data['computed_css']) < 1:
                self.clear()
                return
            data['html_name'] = editor_name
            self.box.show_data(data)
            self.stack.setCurrentIndex(1)

    def read_data(self, sourceline, tags):
        mf = self.preview.view.page().mainFrame()
        tags = [x.lower() for x in tags]
        result = unicode(mf.evaluateJavaScript(
            'window.calibre_preview_integration.live_css(%s, %s)' % (
                json.dumps(sourceline), json.dumps(tags))).toString())
        result = json.loads(result)
        if result is not None:
            for node in result['nodes']:
                for item in node['css']:
                    href = item['href']
                    if hasattr(href, 'startswith') and href.startswith('file://'):
                        href = href[len('file://'):]
                        if iswindows and href.startswith('/'):
                            href = href[1:]
                        if href:
                            item['href'] = current_container().abspath_to_name(href, root=self.preview.current_root)
        return result

    @property
    def current_name(self):
        return self.preview.current_name

    @property
    def is_visible(self):
        return self.isVisible()

    def showEvent(self, ev):
        self.update_timer.start()
        actions['auto-reload-preview'].setEnabled(True)
        return QWidget.showEvent(self, ev)

    def sync_to_editor(self, name):
        self.start_update_timer()

    def update_data(self):
        if not self.is_visible:
            return
        editor_name = self.current_name
        ed = editors.get(editor_name, None)
        if self.update_timer.isActive() or (ed is None and editor_name is not None):
            return QTimer.singleShot(100, self.update_data)
        if ed is not None:
            sourceline, tags = ed.current_tag()
            self.show_data(editor_name, sourceline, tags)

    def start_update_timer(self):
        if self.is_visible:
            self.update_timer.start(1000)

    def stop_update_timer(self):
        self.update_timer.stop()

