#!/usr/bin/env python
# Copyright (C) 2006, Red Hat, Inc.
# Copyright (C) 2007, One Laptop Per Child
# Copyright (C) 2007 Jan Alonzo <jmalonzo@unpluggable.com>
# Copyright (C) 2008, 2009 Luke Kenneth Casson Leighton <lkcl@lkcl.net>
# Copyright (C) 2012 C Anthony Risinger <anthony@xtfx.me>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

def ll(*a):
    for y in a:
        print '\n\n%s\n\n' % y
        for x in dir(y):
            if x in ['coreObject', 'parentInstance', 'core_object', 'parent_instance']:
                print '%5s %30s   %s' % (x.find('isten')!=-1, x, x)
                continue
            try:
                attr = getattr(y, x)
                if attr.__class__ is gi.types.StructMeta:
                    continue
                print '%5s %30s   %s' % (x.find('isten')!=-1, x, str(getattr(y, x))[:100])
            except:
                print 'failed: ', x

import os
import new
import sys
import time
from traceback import print_stack, print_exc

import re

import gi
gi.require_version('WebKit', '3.0')

from gi.repository import GObject, Gtk, WebKit

gobject = GObject
gtk = Gtk
pywebkit = WebKit

from urllib import urlopen
from urlparse import urljoin


from pdb import set_trace as dbg
import inspect, traceback


def _gi_setup():

    class _property_gprops_simple(object):

        def __init__(self, attr):
            self.attr = attr

        def __get__(self, instance, owner):
            return instance.get_property(self.attr)

        def __set__(self, instance, value):
            instance.set_property(self.attr, value)

        def __delete__(self, instance):
            pass

    for cls in [WebKit.DOMDocument, WebKit.DOMHTMLElement, WebKit.DOMCSSStyleDeclaration]:

        def _closure(cls, orig):

            def __getattr__(self, name):
                #XXX need AttributeError in here somewhere ...
                f = '__getattr__'
                alt = re_caps.sub('_\\1', name).lower()
                print f, ':', id(self), self.__class__.__name__, name, alt
                traceback.print_stack(inspect.currentframe().f_back, 1)
                try:
                    altattr = getattr(cls, alt)
                    setattr(cls, name, altattr)
                    return getattr(self, name)
                except AttributeError:
                    try:
                        # trigger
                        self.get_property(alt)
                        print '    props:', alt
                        setattr(cls, name, _property_gprops_simple(alt))
                        return getattr(self, name)
                    except TypeError:
                        if f in orig:
                            return orig[f](self, name)

            def __setattr__(self, name, attr):
                print '__setattr__:', id(self), self.__class__.__name__, name, str(attr)[:50]
                traceback.print_stack(inspect.currentframe().f_back, 1)

            re_caps = re.compile('([A-Z])')
            shims = {'__getattr__': __getattr__,
                     '__setattr__': __setattr__}
            for attr in shims.keys():
                setattr(cls, attr, shims[attr])

        orig = {}
        for attr in ['__getattr__', '__setattr__']:
            try:
                #XXX only check __dict__, then later use super()?
                orig[attr] = getattr(cls, attr)
            except AttributeError:
                pass
        _closure(cls, orig)
        #dbg()
        #print cls, orig
        continue
        for attr in attrs:
            print getattr(cls, '__setattr__')


class Callback(object):
    def __init__(self, sender, cb, boolparam):
        self.sender = sender
        self.cb = cb
        self.boolparam = boolparam
    def _callback(self, event):
        #print "callback", self.sender, self.cb
        try:
            return self.cb(self.sender, event, self.boolparam)
        except:
            print_exc()
            return None


class Browser(object):
    def __init__(self, application, appdir=None, width=800, height=600):

        self.already_initialised = False

        self._loading = False
        self.width = width
        self.height = height
        self.application = application
        self.appdir = appdir

    def load_app(self):

        uri = self.application
        if uri.find("://") == -1:
            # assume file
            uri = 'file://'+os.path.abspath(uri)
            print uri

        self._toplevel = gtk.Window()
        self._toplevel.set_default_size(self.width, self.height)
        self._scroller = gtk.ScrolledWindow()
        self._toplevel.add(self._scroller)
        self._view = pywebkit.WebView()
        self._scroller.add(self._view)
        self._toplevel.show_all()

        # file:/// with # or ? causes error
        self._view.load_uri(uri)
        self._view.get_main_frame().connect('notify::load-status', self._loading_stop_cb)

        self._toplevel.connect('delete-event', self._toplevel_delete_event_cb)
        self._view.connect('title-changed', self._title_changed_cb)
        self._view.connect('icon-loaded', self._icon_loaded_cb)

        # Security? Allow file URIs to access the filesystem
        settings = self._view.get_property('settings')
        settings.set_property('enable-file-access-from-file-uris', True)

    def getUri(self):
        return self.application

    def init_app(self):
        # TODO: ideally, this should be done by hooking body with an "onLoad".

        from __pyjamas__ import pygwt_processMetas, set_main_frame
        from __pyjamas__ import set_gtk_module
        set_gtk_module(gtk)

        main_frame = self
        main_frame._callbacks = []
        #main_frame.gobject_wrap = pywebkit.gobject_wrap
        main_frame.platform = 'webkit'
        main_frame.getUri = self.getUri

        set_main_frame(main_frame)

        #for m in pygwt_processMetas():
        #    minst = module_load(m)
        #    minst.onModuleLoad()

    def _loading_stop_cb(self, frame, pspec):
        if frame.get_property(pspec.name) != WebKit.LoadStatus.FINISHED:
            print frame.get_property(pspec.name)
            return
        self._doc = self._view.get_dom_document()
        self._wnd = self._doc.get_default_view()
        if self.already_initialised:
            return
        self.already_initialised = True
        self.init_app()

    def _icon_loaded_cb(self, view, icon_uri):
        current = view.get_property('uri')
        dom = wv.getDomDocument()
        icon = (gtk.STOCK_DIALOG_QUESTION, None, 0)
        found = set()
        found.add(icon_uri)
        found.add(urljoin(current, '/favicon.ico'))
        scanner = {'href': dom.querySelectorAll('head link[rel~=icon][href],' +
                                                'head link[rel|=apple-touch-icon][href]'),
                   'content': dom.querySelectorAll('head meta[itemprop=image][content]')}
        for attr in scanner.keys():
            for i in xrange(scanner[attr].length):
                uri = getattr(scanner[attr].item(i), attr)
                if len(uri) == 0:
                    continue
                found.add(urljoin(current, uri))
        for uri in found:
            fp = urlopen(uri)
            if fp.code != 200:
                continue
            i = fp.info()
            if i.maintype == 'image' and 'content-length' in i:
                try:
                    ldr = gtk.gdk.PixbufLoader()
                    ldr.write(fp.read(int(i['content-length'])))
                    ldr.close()
                except:
                    continue
                pb = ldr.get_pixbuf()
                pbpx = pb.get_height() * pb.get_width()
                if pbpx > icon[2]:
                    icon = (uri, pb, pbpx)
        if icon[1] is None:
            self._toplevel.set_icon_name(icon[0])
        else:
            self._toplevel.set_icon(icon[1])
        print '_icon_loaded_cb <%s>' % icon[0]

    def _selection_changed_cb(self):
        print "selection changed"

    def _set_scroll_adjustments_cb(self, view, hadjustment, vadjustment):
        self._scrolled_window.props.hadjustment = hadjustment
        self._scrolled_window.props.vadjustment = vadjustment

    def _javascript_console_message_cb(self, view, message, line, sourceid):
        #self._statusbar.show_javascript_info()
        pass

    def _javascript_script_alert_cb(self, view, frame, message):

        print "alert", message

        def close(w):
            dialog.destroy()
        dialog = gtk.Dialog("Alert", None, gtk.DIALOG_DESTROY_WITH_PARENT)
        #dialog.Modal = True;
        label = gtk.Label(message)
        dialog.vbox.add(label)
        label.show()
        button = gtk.Button("OK")
        dialog.action_area.pack_start (button, True, True, 0)
        button.connect("clicked", close)
        button.show()
        #dialog.Response += new ResponseHandler (on_dialog_response)
        dialog.run ()

    def mash_attrib(self, name, joiner='-'):
        return name

    def _alert(self, msg):
        self._javascript_script_alert_cb(None, None, msg)

    def _javascript_script_confirm_cb(self, view, frame, message, isConfirmed):
        pass

    def _view_event_cb(self, view, event, message, fromwindow):
        #print "event! wha-hey!", event, view, message
        #print event.get_event_type()
        #event.stop_propagation()
        return True

    def _javascript_script_prompt_cb(self, view, frame, message, default, text):
        pass

    def _populate_popup(self, view, menu):
        aboutitem = gtk.MenuItem(label="About PyWebKit")
        menu.append(aboutitem)
        aboutitem.connect('activate', self._about_pywebkitgtk_cb)
        menu.show_all()

    def _about_pywebkitgtk_cb(self, widget):
        self._view.open("http://live.gnome.org/PyWebKitGtk")

    def getDomWindow(self):
        return self._wnd

    def getDomDocument(self):
        return self._doc

    def getXmlHttpRequest(self):
        return self._view.GetXMLHttpRequest()

    def _addWindowEventListener(self, event_name, cb):
        cb = Callback(self, cb, True)
        self._wnd.add_event_listener(event_name, cb._callback, False, None)

    def _addXMLHttpRequestEventListener(self, element, event_name, cb):
        #print "add XMLHttpRequest", element, event_name, cb
        cb = Callback(element, cb, True)
        setattr(element, "on%s" % event_name, cb._callback)
        #return element.addEventListener(event_name, cb._callback, True)

    def _addEventListener(self, element, event_name, cb):
        #    element._callbacks.append(cb)
        cb = Callback(element, cb, True)
        #print "addEventListener", element, event_name, cb
        element.add_event_listener(event_name, cb._callback, False, None)

    def _toplevel_delete_event_cb(self, window, event):
        while gtk.events_pending():
            gtk.main_iteration_do(False)
        window.unrealize()

    def _title_changed_cb(self, view, frame, title):
        self._toplevel.set_title(title)


def setup(application, appdir=None, width=800, height=600):

    gobject.threads_init()

    _gi_setup()

    global wv

    wv = Browser(application, appdir, width, height)
    wv.load_app()

    while 1:
        if is_loaded():
            return
        run(one_event=True)

def is_loaded():
    return wv.already_initialised

def run(one_event=False, block=True):
    if one_event:
        if block or gtk.events_pending():
            gtk.main_iteration()
            sys.stdout.flush()
        return gtk.events_pending()
    else:
        while wv._toplevel.get_realized():
            gtk.main_iteration()
            sys.stdout.flush()
